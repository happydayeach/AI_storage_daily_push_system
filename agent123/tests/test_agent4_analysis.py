"""
被测目标：src/agent4_analysis.py
依赖：src/models.py（DedupResult、ExtractedEvent）
覆盖场景：新事件双检索、更新历史分析、主题配置驱动的 prompt（含竞对约束）与无效 JSON 容错
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import mock_open

import pytest
import yaml

from conftest import make_event
from src.models import DedupResult, ExtractedEvent, RawArticle, StoryRecord

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


def test_analyze_uses_custom_theme_and_update_section_names_in_prompts():
    from src.agent4_analysis import analyze

    class SearchTool:
        def search(self, keyword):
            return []

    class FakeLLM:
        def __init__(self):
            self.calls = []

        def chat(self, **kwargs):
            self.calls.append(kwargs)
            if "新动态" in kwargs["prompt"]:
                return '{"新动态":"项目已进入部署阶段"}'
            return '{"背景":"背景内容"}'

    theme_config = {
        "theme_name": "北欧存储·教育行业",
        "update_section_name": "新动态",
        "analysis_template_sections": ["背景"],
    }
    llm = FakeLLM()
    reports = analyze(
        DedupResult(
            new=[make_event("新事件")],
            update=[{"event": make_event("更新事件"), "history_summary": "此前进展"}],
            duplicate_dropped_count=0,
        ),
        SearchTool(),
        llm,
        theme_config,
    )

    assert [call["system_prompt"] for call in llm.calls] == [
        "你是专业的北欧存储·教育行业新闻分析师。仅依据提供的信息进行分析。",
        "你是专业的北欧存储·教育行业新闻分析师。说明相对历史信息的新增进展。",
    ]
    assert '格式为 {"新动态":"段落正文"}' in llm.calls[1]["prompt"]
    assert reports[1].sections == {"新动态": "项目已进入部署阶段"}


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


def test_resolve_supplies_default_storage_competitors():
    from src.config_loader import resolve

    assert resolve({})["competitors"] == [
        "Dell DataDomain",
        "HPE",
        "Rubrik",
        "Cohesity",
        "Hitachi",
        "Commvault",
        "Pure Storage",
    ]


def test_analyze_new_event_prompt_limits_competitor_signals_to_configured_storage_vendors():
    from src.agent4_analysis import analyze

    class SearchTool:
        def search(self, keyword):
            return []

    class FakeLLM:
        def __init__(self):
            self.calls = []

        def chat(self, **kwargs):
            self.calls.append(kwargs)
            return '{"背景":"背景内容","竞对信号":""}'

    llm = FakeLLM()
    analyze(
        DedupResult(new=[make_event("新事件")], update=[], duplicate_dropped_count=0),
        SearchTool(),
        llm,
        {
            "analysis_template_sections": ["背景", "竞对信号"],
            "competitors": ["Rubrik", "Cohesity"],
        },
    )

    prompt = llm.calls[0]["prompt"]
    assert "竞对信号" in prompt
    assert "Rubrik、Cohesity" in prompt
    assert "布局、响应或竞争动作" in prompt
    assert "输出空字符串" in prompt
