import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import mock_open

import pytest
import yaml

from src.models import DedupResult, ExtractedEvent, RawArticle, StoryRecord


def make_event(summary: str) -> ExtractedEvent:
    return ExtractedEvent(
        event_type="其他",
        entities=[],
        key_numbers=[],
        summary_zh=summary,
        category="产业热点",
        source_url="https://source.example/article",
        published_at="2026-09-06T01:00:00",
        domain="source.example",
    )


def test_models_can_be_constructed_with_extracted_event_text_defaults():
    article = RawArticle("https://example.com", "Title", "Snippet", "2026-09-06", "example.com")
    event = make_event("摘要")
    story = StoryRecord("story-1", "theme", "2026-09-01", "2026-09-06", ["摘要"], [1.0, 0.0], [article.url], "产业热点")
    result = DedupResult([event], [{"story_id": story.story_id}], 0)

    assert article.title == "Title"
    assert event.title == ""
    assert event.snippet == ""
    assert story.story_id == "story-1"
    assert result.new == [event]


def test_deep_report_preserves_event_sections_and_update_history():
    from src.models import DeepReport

    event = make_event("摘要")
    report = DeepReport(event, {"新进展": "部署启动"}, True, "此前项目立项")

    assert report.event is event
    assert report.sections == {"新进展": "部署启动"}
    assert report.is_update is True
    assert report.history_summary == "此前项目立项"


def test_save_story_store_adds_new_event_with_serializable_embedding(tmp_path):
    from src.main import save_story_store

    class FakeEmbedder:
        def __init__(self):
            self.calls = []

        def encode(self, text):
            self.calls.append(text)
            return [[0.25, 0.75]]

    store_path = tmp_path / "stories.json"
    event = make_event("新增摘要")
    embedder = FakeEmbedder()

    save_story_store("theme-a", [event], [], embedder, str(store_path))

    import json

    stored = json.loads(store_path.read_text(encoding="utf-8"))
    assert len(stored) == 1
    record = stored[0]
    assert len(record["story_id"]) == 32
    assert record["theme_id"] == "theme-a"
    assert record["summary_history"] == ["新增摘要"]
    assert record["embedding"] == [0.25, 0.75]
    assert record["source_urls"] == [event.source_url]
    assert record["category"] == event.category
    assert record["first_seen_date"] == record["last_updated_date"]
    assert embedder.calls == ["新增摘要"]


def test_save_story_store_updates_matching_story_without_duplicate_history_or_urls(tmp_path):
    import json

    from src.main import save_story_store

    class FakeEmbedder:
        def encode(self, text):
            assert text == "更新摘要"
            return [[0.9, 0.1]]

    store_path = tmp_path / "stories.json"
    store_path.write_text(
        json.dumps([
            {
                "story_id": "target-story",
                "theme_id": "theme-a",
                "first_seen_date": "2026-01-01T00:00:00",
                "last_updated_date": "2026-01-02T00:00:00",
                "summary_history": ["旧摘要"],
                "embedding": [1.0, 0.0],
                "source_urls": ["https://source.example/article"],
                "category": "产业热点",
            },
            {
                "story_id": "other-story",
                "theme_id": "theme-b",
                "first_seen_date": "2026-01-01T00:00:00",
                "last_updated_date": "2026-01-02T00:00:00",
                "summary_history": ["其他"],
                "embedding": [0.0, 1.0],
                "source_urls": ["https://other.example/article"],
                "category": "市场动态",
            },
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    event = make_event("更新摘要")
    update = {"event": event, "story_id": "target-story", "history_summary": "旧摘要"}

    save_story_store("theme-a", [], [update, update], FakeEmbedder(), str(store_path))

    stored = json.loads(store_path.read_text(encoding="utf-8"))
    target = next(record for record in stored if record["story_id"] == "target-story")
    assert target["summary_history"] == ["旧摘要", "更新摘要"]
    assert target["source_urls"] == ["https://source.example/article"]
    assert target["embedding"] == [0.9, 0.1]
    assert target["last_updated_date"] != "2026-01-02T00:00:00"
    assert next(record for record in stored if record["story_id"] == "other-story")["embedding"] == [0.0, 1.0]


def test_mock_search_tool_returns_raw_articles_without_network():
    from src.search_tool import MockSearchTool

    articles = MockSearchTool().search("storage")

    assert articles
    assert all(isinstance(article, RawArticle) for article in articles)


def test_discover_articles_uses_mock_search_and_filters_blacklisted_domain():
    from src.agent1_discovery import discover_articles
    from src.search_tool import MockSearchTool

    discovered = discover_articles({"keywords_matrix": [["storage"]]}, MockSearchTool())
    filtered = discover_articles(
        {
            "keywords_matrix": [["storage"]],
            "source_blacklist": ["cloud.example.net"],
        },
        MockSearchTool(),
    )

    assert discovered
    assert all(isinstance(article, RawArticle) for article in discovered)
    assert all(article.domain != "cloud.example.net" for article in filtered)
    assert len(filtered) == len(discovered) - 1


def test_discover_articles_logs_warning_and_keeps_article_for_unparseable_timestamp(caplog):
    from src.agent1_discovery import discover_articles
    from src.search_tool import SearchTool

    class InvalidTimestampSearchTool(SearchTool):
        def search(self, keyword):
            return [RawArticle("https://example.com/a", "Title", "Snippet", "not-a-date", "example.com")]

    with caplog.at_level(logging.WARNING, logger="src.agent1_discovery"):
        articles = discover_articles({"keywords_matrix": [["storage"]]}, InvalidTimestampSearchTool())

    assert [article.url for article in articles] == ["https://example.com/a"]
    assert "Could not parse publication time" in caplog.text


def test_discover_articles_discards_old_aware_timestamp():
    from src.agent1_discovery import discover_articles
    from src.search_tool import SearchTool

    class TimestampSearchTool(SearchTool):
        def search(self, keyword):
            return [
                RawArticle(
                    "https://example.com/old",
                    "Old",
                    "Snippet",
                    (datetime.now(timezone.utc) - timedelta(hours=60)).isoformat(),
                    "example.com",
                ),
                RawArticle(
                    "https://example.com/fresh",
                    "Fresh",
                    "Snippet",
                    datetime.now(timezone.utc).isoformat(),
                    "example.com",
                ),
            ]

    articles = discover_articles({"keywords_matrix": [["storage"]]}, TimestampSearchTool())

    assert [article.url for article in articles] == ["https://example.com/fresh"]


def test_discover_articles_discards_old_naive_timestamp():
    from src.agent1_discovery import discover_articles
    from src.search_tool import SearchTool

    class NaiveTimestampSearchTool(SearchTool):
        def search(self, keyword):
            return [
                RawArticle(
                    "https://example.com/old",
                    "Old",
                    "Snippet",
                    (datetime.now() - timedelta(hours=60)).isoformat(),
                    "example.com",
                )
            ]

    articles = discover_articles({"keywords_matrix": [["storage"]]}, NaiveTimestampSearchTool())

    assert articles == []


def test_discover_articles_continues_after_one_keyword_search_fails(caplog):
    from src.agent1_discovery import discover_articles
    from src.search_tool import SearchTool

    class PartiallyFailingSearchTool(SearchTool):
        def search(self, keyword):
            if keyword == "broken":
                raise RuntimeError("temporary search failure")
            return [RawArticle("https://example.com/good", "Good", "Snippet", "", "example.com")]

    with caplog.at_level(logging.ERROR, logger="src.agent1_discovery"):
        articles = discover_articles(
            {"keywords_matrix": [["broken", "working"]]},
            PartiallyFailingSearchTool(),
        )

    assert [article.url for article in articles] == ["https://example.com/good"]
    assert "Search failed for keyword 'broken'" in caplog.text


def test_deduplicator_classifies_new_update_and_duplicate_without_model_download():
    from src.agent3_dedupe import Deduplicator

    class FakeEmbedder:
        vectors = {
            "duplicate": [1.0, 0.0],
            "update": [0.8, 0.6],
            "new": [0.0, 1.0],
        }

        def encode(self, texts):
            return [self.vectors[text] for text in texts]

    historical = StoryRecord("story-1", "theme", "2026-09-01", "2026-09-06", ["duplicate"], [1.0, 0.0], ["https://old.example"], "产业热点")
    duplicate, update, new = (make_event(summary) for summary in ("duplicate", "update", "new"))

    result = Deduplicator(FakeEmbedder(), threshold_a=0.88, threshold_b=0.75).dedupe(
        [duplicate, update, new], [historical]
    )

    assert result.duplicate_dropped_count == 1
    assert result.update == [{"event": update, "story_id": "story-1", "history_summary": "duplicate"}]
    assert result.new == [new]


def test_tavily_search_tool_maps_results_to_raw_articles(monkeypatch):
    from src.search_tool import TavilySearchTool

    class Response:
        def read(self):
            return b'{"results":[{"title":"Storage update","url":"https://www.example.com/news","content":"European storage news","published_date":"Fri, 05 Sep 2026 12:30:00 +0000"}]}'

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr("src.search_tool.urlopen", lambda *args, **kwargs: Response())

    articles = TavilySearchTool(api_key="key").search("storage")

    assert articles == [
        RawArticle(
            "https://www.example.com/news",
            "Storage update",
            "European storage news",
            "2026-09-05T12:30:00+00:00",
            "example.com",
        )
    ]


def test_tavily_search_tool_without_credentials_raises_clear_error(monkeypatch):
    from src.search_tool import TavilySearchTool

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    with pytest.raises(ValueError, match="TAVILY_API_KEY"):
        TavilySearchTool()


def test_tavily_search_tool_returns_empty_list_when_request_fails(monkeypatch, caplog):
    from src.search_tool import TavilySearchTool

    def failing_urlopen(*args, **kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr("src.search_tool.urlopen", failing_urlopen)

    with caplog.at_level(logging.ERROR, logger="src.search_tool"):
        articles = TavilySearchTool(api_key="key").search("storage")

    assert articles == []
    assert "Tavily Search failed" in caplog.text


def test_extract_event_parses_fixed_json_from_mocked_client():
    from src.agent2_extraction import extract_event

    class FakeDeepSeekClient:
        def chat(self, **kwargs):
            assert kwargs["max_tokens"] == 800
            return '{"event_type":"产品发布","entities":["Acme"],"key_numbers":["10%"],"summary_zh":"Acme 发布了新存储产品。","category":"产品与技术"}'

    article = RawArticle("https://example.com/product", "New product", "Details", "2026-09-06T01:00:00", "example.com")
    event = extract_event(article, FakeDeepSeekClient())

    assert event == ExtractedEvent("产品发布", ["Acme"], ["10%"], "Acme 发布了新存储产品。", "产品与技术", article.url, article.published_at, article.domain, article.title, article.snippet)


@pytest.mark.parametrize(
    ("provider", "expected_model", "expected_api_key", "expected_base_url"),
    [
        ("deepseek", "deepseek-v4-flash", "deepseek-key", "https://api.deepseek.com/v1"),
        ("codex", "gpt-5.6-terra", "codex-token", "https://chatgpt.com/backend-api/codex"),
    ],
)
def test_llm_client_selects_provider_and_uses_its_api(monkeypatch, provider, expected_model, expected_api_key, expected_base_url):
    from src.llm_client import LLMClient

    created_clients = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.chat = type("Chat", (), {"completions": type("Completions", (), {"create": self.create_chat})()})()
            self.responses = type("Responses", (), {"create": self.create_response})()
            created_clients.append(self)

        def create_chat(self, **kwargs):
            self.chat_kwargs = kwargs
            return type("Response", (), {"choices": [type("Choice", (), {"message": type("Message", (), {"content": "deepseek reply"})()})()]})()

        def create_response(self, **kwargs):
            self.response_kwargs = kwargs
            return type("Response", (), {"output_text": "codex reply"})()

    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setattr("src.llm_client.OpenAI", FakeOpenAI)
    monkeypatch.setattr("builtins.open", mock_open(read_data='{"tokens":{"access_token":"codex-token","account_id":"account-1"}}'))

    result = LLMClient().chat("prompt", system_prompt="system", max_tokens=123)

    client = created_clients[0]
    assert client.kwargs["api_key"] == expected_api_key
    assert client.kwargs["base_url"] == expected_base_url
    assert result == f"{provider} reply"
    if provider == "deepseek":
        assert client.chat_kwargs == {
            "model": expected_model,
            "messages": [{"role": "system", "content": "system"}, {"role": "user", "content": "prompt"}],
            "max_tokens": 123,
            "temperature": 0.1,
            "stream": False,
            "extra_body": {"thinking": {"type": "disabled"}},
        }
    else:
        assert client.kwargs["default_headers"] == {"ChatGPT-Account-Id": "account-1"}
        assert client.response_kwargs == {
            "model": expected_model,
            "instructions": "system",
            "input": [{"role": "user", "content": "prompt"}],
            "reasoning": {"effort": "low"},
            "store": False,
            "stream": True,
        }


def test_analyze_new_event_searches_twice_and_returns_configured_sections():
    from src.agent4_analysis import analyze

    class RecordingSearchTool:
        def __init__(self):
            self.keywords = []

        def search(self, keyword):
            self.keywords.append(keyword)
            return [RawArticle("https://evidence.example/a", "Evidence title", "Evidence snippet", "", "evidence.example")]

    class FakeLLM:
        def __init__(self):
            self.calls = []

        def chat(self, **kwargs):
            self.calls.append(kwargs)
            return '```json\n{"背景":"背景内容","技术分析":"技术内容","市场影响":"市场内容","竞对信号":"竞对内容"}\n```'

    event = make_event("Acme 发布新产品")
    event.entities = ["Acme"]
    event.title = "Acme launches storage"
    search_tool = RecordingSearchTool()
    llm = FakeLLM()

    reports = analyze(
        DedupResult(new=[event], update=[], duplicate_dropped_count=0),
        search_tool,
        llm,
        {"analysis_template_sections": ["背景", "技术分析", "市场影响", "竞对信号"]},
    )

    assert search_tool.keywords == ["Acme", "Acme"]
    assert len(llm.calls) == 1
    assert "Evidence title" in llm.calls[0]["prompt"]
    assert reports[0].event is event
    assert reports[0].sections == {"背景": "背景内容", "技术分析": "技术内容", "市场影响": "市场内容", "竞对信号": "竞对内容"}
    assert reports[0].is_update is False
    assert reports[0].history_summary == ""


def test_analyze_update_skips_search_and_generates_progress_from_history():
    from src.agent4_analysis import analyze

    class FailingSearchTool:
        def search(self, keyword):
            raise AssertionError("update events must not trigger a second search")

    class FakeLLM:
        def __init__(self):
            self.calls = []

        def chat(self, **kwargs):
            self.calls.append(kwargs)
            return '{"新进展":"项目已进入部署阶段"}'

    event = make_event("项目有进一步消息")
    llm = FakeLLM()

    reports = analyze(
        DedupResult(
            new=[],
            update=[{"event": event, "story_id": "story-1", "history_summary": "此前已宣布项目立项"}],
            duplicate_dropped_count=0,
        ),
        FailingSearchTool(),
        llm,
        {"analysis_template_sections": ["背景", "技术分析", "市场影响", "竞对信号"]},
    )

    assert len(llm.calls) == 1
    assert "此前已宣布项目立项" in llm.calls[0]["prompt"]
    assert reports[0].sections == {"新进展": "项目已进入部署阶段"}
    assert reports[0].is_update is True
    assert reports[0].history_summary == "此前已宣布项目立项"


def test_analyze_logs_error_and_skips_only_event_with_invalid_llm_json(caplog):
    from src.agent4_analysis import analyze

    class SearchTool:
        def search(self, keyword):
            return []

    class InvalidJsonLLM:
        def chat(self, **kwargs):
            return "not JSON"

    with caplog.at_level(logging.ERROR, logger="src.agent4_analysis"):
        reports = analyze(
            DedupResult(new=[make_event("无法解析的分析")], update=[], duplicate_dropped_count=0),
            SearchTool(),
            InvalidJsonLLM(),
            {"analysis_template_sections": ["背景", "技术分析", "市场影响", "竞对信号"]},
        )

    assert reports == []
    assert "Deep analysis failed for new event" in caplog.text


def test_qa_counts_valid_reports_and_records_one_located_issue_per_invalid_report(caplog):
    from src.agent5_qa import qa
    from src.models import DeepReport

    valid_event = make_event("有效摘要")
    valid_event.entities = ["Acme"]
    valid_event.title = "有效事件"
    invalid_event = make_event("无效摘要")
    invalid_event.entities = ["BrokenCo"]
    invalid_event.title = "无效事件"
    invalid_event.category = ""
    with caplog.at_level(logging.INFO, logger="src.agent5_qa"):
        result = qa(
            [
                DeepReport(valid_event, {"背景": "完整背景", "技术分析": "完整分析"}, False),
                DeepReport(invalid_event, {"背景": "", "技术分析": "完整分析"}, False),
            ],
            {"analysis_template_sections": ["背景", "技术分析"]},
        )

    assert result.passed is False
    assert result.total == 2
    assert result.valid == 1
    assert len(result.issues) == 1
    assert "无效事件" in result.issues[0]
    assert "背景" in result.issues[0]
    assert "category" in result.issues[0]
    assert "total=2" in caplog.text


def test_qa_rejects_an_empty_report_list():
    from src.agent5_qa import qa

    result = qa([], {"analysis_template_sections": ["背景"]})

    assert result.passed is False
    assert result.total == 0
    assert result.valid == 0
    assert result.issues == ["无深度报告"]


def test_render_html_builds_complete_card_with_configured_icon_and_colors():
    from src.agent6_render import render_html
    from src.models import DeepReport

    event = make_event("产品摘要")
    event.event_type = "产品发布"
    event.title = "Acme 推出存储产品"
    report = DeepReport(event, {"背景": "背景内容", "技术分析": "技术内容", "市场影响": "市场内容", "竞对信号": "竞对内容"}, False)
    theme_config = {
        "categories": ["产品与技术"],
        "icon_map": {"产品发布": "🚀"},
        "theme_colors": {"primary": "#123456", "accent": "#abcdef"},
    }

    html = render_html([report], theme_config)

    assert '<html' in html
    assert '<head>' in html
    assert '<meta charset="utf-8">' in html
    assert '<title>' in html
    assert '<body>' in html
    assert 'class="card"' in html
    assert "🚀" in html
    assert "Acme 推出存储产品" in html
    assert '<span class="tag">产业热点</span>' in html
    assert all(section in html for section in ("背景", "技术分析", "市场影响", "竞对信号"))
    assert all(content in html for content in ("背景内容", "技术内容", "市场内容", "竞对内容"))
    assert 'href="https://source.example/article"' in html
    assert "#123456" in html
    assert "#abcdef" in html


def test_render_html_renders_update_progress_and_history_without_empty_new_sections():
    from src.agent6_render import render_html
    from src.models import DeepReport

    event = make_event("更新摘要")
    report = DeepReport(
        event,
        {"新进展": "项目已完成首批部署。"},
        True,
        "此前已完成项目立项。",
    )

    html = render_html([report], {"categories": ["产业热点"]})

    assert "新进展" in html
    assert "项目已完成首批部署。" in html
    assert "此前已完成项目立项。" in html
    assert html.count("<p></p>") == 0


def test_render_push_message_includes_configured_icon_title_category_summary_and_link():
    from src.agent6_render import render_push_message
    from src.models import DeepReport

    event = make_event("推送摘要")
    event.event_type = "合作"
    event.title = "Acme 与 Contoso 合作"
    report = DeepReport(event, {}, False)

    message = render_push_message(
        [report],
        {"categories": ["产业热点"], "icon_map": {"合作": "🤝"}, "theme_colors": {"primary": "#123456", "accent": "#abcdef"}},
    )

    assert "🤝 Acme 与 Contoso 合作｜产业热点" in message
    assert "推送摘要" in message
    assert "https://source.example/article" in message


def test_pushplus_adapter_posts_expected_json_and_accepts_success_response(monkeypatch):
    from src.agent7_push import PushplusAdapter

    captured = {}

    class Response:
        status = 200

        def read(self):
            return b'{"code": 200}'

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = request.data
        captured["content_type"] = request.get_header("Content-type")
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("src.agent7_push.urlopen", fake_urlopen)

    assert PushplusAdapter("pushplus-token").push("briefing", title="Custom title") is True
    assert captured == {
        "url": "http://www.pushplus.plus/send",
        "method": "POST",
        "body": b'{"token": "pushplus-token", "title": "Custom title", "content": "briefing", "template": "txt"}',
        "content_type": "application/json",
        "timeout": 15,
    }


@pytest.mark.parametrize(
    ("adapter_name", "credential", "response_body", "expected_payload"),
    [
        (
            "WecomAdapter",
            "https://wecom.example/hook",
            b'{"errcode": 0}',
            {"msgtype": "text", "text": {"content": "briefing"}},
        ),
        (
            "FeishuAdapter",
            "https://feishu.example/hook",
            b'{"StatusCode": 0}',
            {"msg_type": "text", "content": {"text": "briefing"}},
        ),
    ],
)
def test_webhook_adapters_post_channel_specific_json(monkeypatch, adapter_name, credential, response_body, expected_payload):
    from src import agent7_push

    captured = {}

    class Response:
        status = 200

        def read(self):
            return response_body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = request.data
        return Response()

    monkeypatch.setattr(agent7_push, "urlopen", fake_urlopen)
    adapter = getattr(agent7_push, adapter_name)(credential)

    assert adapter.push("briefing") is True
    assert captured["url"] == credential
    import json

    assert json.loads(captured["body"]) == expected_payload


def test_build_adapters_resolves_placeholders_skips_missing_and_dispatches_channels(caplog):
    from src.agent7_push import FeishuAdapter, PushplusAdapter, WecomAdapter, build_adapters

    adapters = build_adapters(
        {
            "push_targets": [
                {"channel": "pushplus", "token": "your_token"},
                {"channel": "wecom", "webhook": "configured-webhook"},
                {"channel": "feishu", "webhook": "your_webhook"},
                {"channel": "wecom", "webhook": ""},
            ]
        },
        env={"PUSHPLUS_TOKEN": "environment-token", "FEISHU_WEBHOOK": "feishu-webhook"},
    )

    assert [type(adapter) for adapter in adapters] == [PushplusAdapter, WecomAdapter, FeishuAdapter]
    assert adapters[0].token == "environment-token"
    assert adapters[1].webhook == "configured-webhook"
    assert adapters[2].webhook == "feishu-webhook"
    assert "Skipping wecom push target without credentials" in caplog.text


def test_push_returns_false_for_transport_http_and_json_failures(monkeypatch):
    from src.agent7_push import PushplusAdapter

    def failing_urlopen(*args, **kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr("src.agent7_push.urlopen", failing_urlopen)
    assert PushplusAdapter("token").push("briefing") is False

    class BadStatusResponse:
        status = 500

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr("src.agent7_push.urlopen", lambda *args, **kwargs: BadStatusResponse())
    assert PushplusAdapter("token").push("briefing") is False

    class BadJsonResponse:
        status = 200

        def read(self):
            return b"not json"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr("src.agent7_push.urlopen", lambda *args, **kwargs: BadJsonResponse())
    assert PushplusAdapter("token").push("briefing") is False

    class NonObjectJsonResponse:
        status = 200

        def read(self):
            return b"[]"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr("src.agent7_push.urlopen", lambda *args, **kwargs: NonObjectJsonResponse())
    assert PushplusAdapter("token").push("briefing") is False


def test_push_all_continues_after_adapter_exception():
    from src.agent7_push import PushAdapter, push_all

    class FailingAdapter(PushAdapter):
        channel = "failing"

        def push(self, message, title="每日情报简报"):
            raise OSError("broken")

    class SuccessfulAdapter(PushAdapter):
        channel = "successful"

        def __init__(self):
            self.calls = []

        def push(self, message, title="每日情报简报"):
            self.calls.append((message, title))
            return True

    successful = SuccessfulAdapter()

    assert push_all([FailingAdapter(), successful], "briefing", "Custom title") == {
        "failing": False,
        "successful": True,
    }
    assert successful.calls == [("briefing", "Custom title")]


def test_main_continues_after_qa_failure_and_writes_rendered_outputs(monkeypatch, tmp_path):
    import json

    from src import main
    from src.agent7_push import PushplusAdapter
    from src.models import DeepReport

    event = make_event("缺字段的摘要")
    event.entities = ["Acme"]
    event.title = "Acme 动态"
    report = DeepReport(event, {"背景": ""}, False)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "theme_europe_storage.yaml").write_text(
        "theme_id: test\nanalysis_template_sections: [背景]\npush_targets:\n  - channel: pushplus\n    token: token\n",
        encoding="utf-8",
    )

    class Response:
        status = 200

        def read(self):
            return b'{"code": 200}'

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    requests = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main, "load_dotenv", lambda: None)
    monkeypatch.setattr(main, "LLMClient", lambda: object())
    monkeypatch.setattr(main, "EmbeddingClient", lambda: object())
    monkeypatch.setattr(main, "discover_articles", lambda config, searcher: [])
    monkeypatch.setattr(main, "process_articles", lambda articles, llm: [])
    monkeypatch.setattr(main, "load_story_store", lambda theme_id: [])
    monkeypatch.setattr(main, "save_story_store", lambda *args: None)
    monkeypatch.setattr(main, "analyze", lambda result, searcher, llm, config: [report])
    monkeypatch.setattr(main, "build_adapters", lambda config: [PushplusAdapter("token")])
    monkeypatch.setattr("src.agent7_push.urlopen", lambda request, timeout: requests.append(request) or Response())

    main.main()

    output = tmp_path / "output"
    repo_root = Path(main.__file__).resolve().parents[2]
    assert (repo_root / "docs" / "index.html").is_file()
    assert not (tmp_path / "docs" / "index.html").exists()
    saved = json.loads((output / "agent123_result.json").read_text(encoding="utf-8"))
    assert saved["qa"] == {"passed": False, "valid": 0, "total": 1, "issues": ["报告 Acme 动态 缺少或为空: sections.背景"]}
    assert len(requests) == 1


def test_daily_workflow_is_valid_and_configures_scheduled_secret_backed_pipeline():
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "daily.yml"

    assert workflow_path.is_file()
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    triggers = workflow.get("on", workflow.get(True))

    assert triggers["schedule"] == [{"cron": "0 6 * * *"}]
    assert triggers["workflow_dispatch"] == {}
    assert workflow["jobs"]["briefing"]["permissions"] == {"contents": "write"}
    assert "LLM_PROVIDER: deepseek" in workflow_text
    assert "git add docs/ agent123/output/" in workflow_text
    assert "git push origin HEAD:" in workflow_text
    for secret_name in (
        "DEEPSEEK_API_KEY",
        "TAVILY_API_KEY",
        "PUSHPLUS_TOKEN",
        "WECOM_WEBHOOK",
        "FEISHU_WEBHOOK",
    ):
        assert f"${{{{ secrets.{secret_name} }}}}" in workflow_text


def test_build_adapters_skips_none_credentials_and_null_targets():
    from src.agent7_push import build_adapters

    assert build_adapters({"push_targets": [{"channel": "pushplus", "token": None}]}) == []
    assert build_adapters({"push_targets": None}) == []


@pytest.mark.parametrize("response_body, expected", [
    (b'{"code": 0}', True),
    (b'{"StatusCode": 0}', True),
    (b'{"code": 1}', False),
])
def test_feishu_adapter_accepts_only_zero_code_responses(monkeypatch, response_body, expected):
    from src.agent7_push import FeishuAdapter

    class Response:
        status = 200

        def read(self):
            return response_body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr("src.agent7_push.urlopen", lambda *args, **kwargs: Response())

    assert FeishuAdapter("https://feishu.example/hook").push("briefing") is expected
