"""
被测目标：src/agent5_qa.py
依赖：src/models.py（DeepReport、ExtractedEvent）
覆盖场景：报告有效性统计、定位问题与空列表拒绝
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import mock_open

import pytest
import yaml

from conftest import make_event
from src.models import DedupResult, ExtractedEvent, RawArticle, StoryRecord

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
