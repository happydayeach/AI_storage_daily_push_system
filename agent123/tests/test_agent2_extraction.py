"""
被测目标：src/agent2_extraction.py
依赖：src/models.py（RawArticle、ExtractedEvent）、src/llm_client.py（LLMClient）
覆盖场景：relevant 相关性过滤、industry/vertical 双标签、title_zh/structured_summary 兜底、JSON 清理容错、主题配置驱动的提取 prompt
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import mock_open

import pytest
import yaml

from conftest import make_event
from src.models import DedupResult, ExtractedEvent, RawArticle, StoryRecord

def test_extract_event_parses_fixed_json_from_mocked_client():
    from src.agent2_extraction import extract_event

    class FakeDeepSeekClient:
        def chat(self, **kwargs):
            assert kwargs["max_tokens"] == 800
            return '{"event_type":"产品发布","entities":["Acme"],"key_numbers":["10%"],"summary_zh":"Acme 发布了新存储产品。","category":"产品与技术"}'

    article = RawArticle("https://example.com/product", "New product", "Details", "2026-09-06T01:00:00", "example.com")
    event = extract_event(article, FakeDeepSeekClient(), {})

    assert event == ExtractedEvent("产品发布", ["Acme"], ["10%"], "Acme 发布了新存储产品。", "产品与技术", article.url, article.published_at, article.domain, article.title, article.snippet)


def test_extract_event_writes_industry_and_vertical_tags_from_llm_response():
    from src.agent2_extraction import extract_event

    class FakeLLM:
        def chat(self, **kwargs):
            return '{"event_type":"产品发布","entities":["Acme"],"key_numbers":[],"summary_zh":"Acme 发布了 SSD。","category":"产品与技术","industry":"flash","vertical":"finance"}'

    article = RawArticle("https://example.com/product", "New product", "Details", "2026-09-06T01:00:00", "example.com")

    event = extract_event(article, FakeLLM(), {})

    assert event is not None
    assert event.industry == "flash"
    assert event.vertical == "finance"


def test_extract_event_defaults_missing_industry_and_vertical_tags_to_empty_strings():
    from src.agent2_extraction import extract_event

    class FakeLLM:
        def chat(self, **kwargs):
            return '{"event_type":"产品发布","entities":[],"key_numbers":[],"summary_zh":"Acme 发布了存储产品。","category":"产品与技术"}'

    article = RawArticle("https://example.com/product", "New product", "Details", "2026-09-06T01:00:00", "example.com")

    event = extract_event(article, FakeLLM(), {})

    assert event is not None
    assert event.industry == ""
    assert event.vertical == ""


def test_extract_event_normalizes_non_string_industry_and_vertical_tags_to_empty_strings():
    from src.agent2_extraction import extract_event

    class FakeLLM:
        def chat(self, **kwargs):
            return '{"event_type":"产品发布","entities":[],"key_numbers":[],"summary_zh":"Acme 发布了存储产品。","category":"产品与技术","industry":null,"vertical":1}'

    article = RawArticle("https://example.com/product", "New product", "Details", "2026-09-06T01:00:00", "example.com")

    event = extract_event(article, FakeLLM(), {})

    assert event is not None
    assert event.industry == ""
    assert event.vertical == ""


@pytest.mark.parametrize(
    ("title_zh", "structured_summary", "expected_title_zh", "expected_structured_summary"),
    [
        ("Acme 推出新产品", "时间：2026年9月；地点：美国；起因：扩容；经过：发布新品；结果：将促进企业级存储升级。", "Acme 推出新产品", "时间：2026年9月；地点：美国；起因：扩容；经过：发布新品；结果：将促进企业级存储升级。"),
        (None, 42, "", ""),
    ],
)
def test_extract_event_parses_new_chinese_title_and_structured_summary_with_string_fallbacks(
    title_zh, structured_summary, expected_title_zh, expected_structured_summary
):
    from src.agent2_extraction import extract_event

    class FakeLLM:
        def chat(self, **kwargs):
            import json
            return json.dumps({
                "event_type": "产品发布",
                "entities": [],
                "key_numbers": [],
                "summary_zh": "Acme 发布了存储产品。",
                "category": "产品与技术",
                "title_zh": title_zh,
                "structured_summary": structured_summary,
            }, ensure_ascii=False)

    article = RawArticle("https://example.com/product", "New product", "Details", "2026-09-06T01:00:00", "example.com")

    event = extract_event(article, FakeLLM(), {})

    assert event is not None
    assert event.title_zh == expected_title_zh
    assert event.structured_summary == expected_structured_summary


def test_extract_event_discards_article_marked_irrelevant(caplog):
    from src.agent2_extraction import extract_event

    class FakeLLM:
        def chat(self, **kwargs):
            return '{"relevant":false,"event_type":"其他","entities":[],"key_numbers":[],"summary_zh":"博彩软文。","category":"产业热点"}'

    article = RawArticle("https://spam.example/article", "博彩", "SEO spam", "2026-09-06T01:00:00", "spam.example")

    with caplog.at_level(logging.INFO, logger="src.agent2_extraction"):
        event = extract_event(article, FakeLLM(), {})

    assert event is None
    assert "Skipping irrelevant article" in caplog.text


@pytest.mark.parametrize("relevant", [True, None, 0, "false"])
def test_extract_event_keeps_relevant_or_unclassified_article(relevant):
    from src.agent2_extraction import extract_event

    class FakeLLM:
        def chat(self, **kwargs):
            data = {
                "event_type": "产品发布",
                "entities": ["Acme"],
                "key_numbers": [],
                "summary_zh": "Acme 发布了新存储产品。",
                "category": "产品与技术",
            }
            if relevant is not None:
                data["relevant"] = relevant
            import json
            return json.dumps(data, ensure_ascii=False)

    article = RawArticle("https://example.com/product", "New product", "Details", "2026-09-06T01:00:00", "example.com")

    event = extract_event(article, FakeLLM(), {})

    assert event is not None
    assert event.title == article.title


def test_process_articles_keeps_only_relevant_extracted_events():
    from src.agent2_extraction import process_articles

    class FakeLLM:
        def chat(self, **kwargs):
            relevant = "spam" not in kwargs["prompt"]
            import json
            return json.dumps({
                "relevant": relevant,
                "event_type": "产品发布",
                "entities": [],
                "key_numbers": [],
                "summary_zh": "存储新闻。",
                "category": "产品与技术",
            }, ensure_ascii=False)

    articles = [
        RawArticle("https://spam.example/article", "spam", "博彩", "2026-09-06T01:00:00", "spam.example"),
        RawArticle("https://storage.example/article", "Storage", "存储", "2026-09-06T01:00:00", "storage.example"),
    ]

    events = process_articles(articles, FakeLLM(), {})

    assert [event.source_url for event in events] == ["https://storage.example/article"]


def test_extract_event_builds_prompt_from_custom_theme_config():
    from src.agent2_extraction import extract_event

    class FakeLLM:
        def __init__(self):
            self.prompt = ""

        def chat(self, **kwargs):
            self.prompt = kwargs["prompt"]
            return '{"event_type":"校园公告","entities":[],"key_numbers":[],"summary_zh":"教育新闻。","category":"教育动态","relevant":true}'

    theme_config = {
        "relevance_theme": "教育产业（学校、课程与教育技术）",
        "event_types": ["校园公告"],
        "categories": [{"id": "education", "label": "教育动态", "icon": "📚"}],
        "industries": {
            "edtech": {"label": "教育科技", "desc": "教育软件与在线课程"},
        },
        "verticals": {
            "education": {"label": "教育", "desc": "学校与高等教育"},
        },
    }
    article = RawArticle("https://example.com/education", "Campus", "Details", "2026-09-06T01:00:00", "example.com")
    llm = FakeLLM()

    event = extract_event(article, llm, theme_config)

    assert event is not None
    assert '["校园公告"]' in llm.prompt
    assert '["教育动态"]' in llm.prompt
    assert "教育产业（学校、课程与教育技术）" in llm.prompt
    assert "edtech=教育科技（教育软件与在线课程）" in llm.prompt
    assert "education=教育（学校与高等教育）" in llm.prompt
