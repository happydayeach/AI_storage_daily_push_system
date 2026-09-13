"""Pre-release quality checks for deep analysis reports."""

import logging
from typing import List

from src.models import DeepReport, QAResult

logger = logging.getLogger(__name__)

OPTIONAL_EMPTY_NEW_REPORT_SECTIONS = frozenset({"竞对信号"})


def _report_issues(report: DeepReport, required_sections: List[str]) -> List[str]:
    missing = [
        f"sections.{section}"
        for section in required_sections
        if not report.sections.get(section)
    ]
    event = report.event
    if not event.event_type:
        missing.append("event.event_type")
    if not event.entities:
        missing.append("event.entities")
    if not event.summary_zh:
        missing.append("event.summary_zh")
    if not event.category:
        missing.append("event.category")
    return missing


def qa(reports: List[DeepReport], theme_config: dict) -> QAResult:
    """Check deep reports for configured sections and required event fields."""
    total = len(reports)
    issues = []
    valid = 0
    new_report_sections = theme_config["analysis_template_sections"]
    update_report_sections = [theme_config.get("update_section_name", "新进展")]

    if total == 0:
        issues.append("无深度报告")

    for report in reports:
        required_sections = (
            update_report_sections
            if report.is_update
            else [
                section
                for section in new_report_sections
                if section not in OPTIONAL_EMPTY_NEW_REPORT_SECTIONS
            ]
        )
        missing = _report_issues(report, required_sections)
        if not missing:
            valid += 1
            continue
        location = report.event.title or report.event.source_url
        issues.append(f"报告 {location} 缺少或为空: {', '.join(missing)}")

    result = QAResult(
        passed=total > 0 and not issues,
        total=total,
        valid=valid,
        issues=issues,
    )
    logger.info("QA summary: total=%d valid=%d issues=%d", result.total, result.valid, len(result.issues))
    return result
