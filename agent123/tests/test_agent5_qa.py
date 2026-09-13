"""
被测目标：src/agent5_qa.py
依赖：src/models.py（DeepReport、ExtractedEvent）
覆盖场景：new 报告四段完整性、update 报告新进展段完整性、定位问题与空列表拒绝
"""

import logging

from conftest import make_event
from src.models import DeepReport


def test_qa_counts_valid_reports_and_records_one_located_issue_per_invalid_report(caplog):
    from src.agent5_qa import qa

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


def test_qa_accepts_new_report_with_empty_competitor_signal_section():
    from src.agent5_qa import qa

    event = make_event("竞对布局缺失")
    event.entities = ["Acme"]
    event.title = "无厂商布局事件"

    result = qa(
        [
            DeepReport(
                event,
                {
                    "背景": "完整背景",
                    "技术分析": "完整技术分析",
                    "市场影响": "完整市场影响",
                    "竞对信号": "",
                },
                False,
            )
        ],
        {
            "analysis_template_sections": ["背景", "技术分析", "市场影响", "竞对信号"],
        },
    )

    assert result.passed is True
    assert result.total == 1
    assert result.valid == 1
    assert result.issues == []


def test_qa_accepts_update_report_with_only_configured_update_section():
    from src.agent5_qa import qa

    event = make_event("更新摘要")
    event.entities = ["Acme"]
    event.title = "更新事件"

    result = qa(
        [DeepReport(event, {"新进展": "项目进入部署阶段"}, True)],
        {
            "analysis_template_sections": ["背景", "技术分析", "市场影响", "竞对信号"],
        },
    )

    assert result.passed is True
    assert result.total == 1
    assert result.valid == 1
    assert result.issues == []


def test_qa_reports_missing_configured_update_section_for_update_report():
    from src.agent5_qa import qa

    event = make_event("更新摘要")
    event.entities = ["Acme"]
    event.title = "更新事件"

    result = qa(
        [DeepReport(event, {}, True)],
        {
            "analysis_template_sections": ["背景", "技术分析", "市场影响", "竞对信号"],
        },
    )

    assert result.passed is False
    assert result.valid == 0
    assert len(result.issues) == 1
    assert "sections.新进展" in result.issues[0]
    assert "sections.背景" not in result.issues[0]


def test_qa_rejects_an_empty_report_list():
    from src.agent5_qa import qa

    result = qa([], {"analysis_template_sections": ["背景"]})

    assert result.passed is False
    assert result.total == 0
    assert result.valid == 0
    assert result.issues == ["无深度报告"]
