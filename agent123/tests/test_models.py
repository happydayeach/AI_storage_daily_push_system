"""
被测目标：src/models.py
依赖：src/models.py（RawArticle、ExtractedEvent、StoryRecord、DedupResult、DeepReport）
覆盖场景：模型默认值与深度报告字段保留
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import mock_open

import pytest
import yaml

from conftest import make_event
from src.models import DedupResult, ExtractedEvent, RawArticle, StoryRecord

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
