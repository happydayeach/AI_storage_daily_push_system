"""
被测目标：src/agent4_analysis.py
依赖：src/models.py（DedupResult、ExtractedEvent）
覆盖场景：新事件双检索、更新历史分析与无效 JSON 容错
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
