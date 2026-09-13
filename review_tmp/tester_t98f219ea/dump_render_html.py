"""Tester probe: sha256 of render_html output for a fixed input (frontend-line regression check)."""
from __future__ import annotations

import hashlib

from src import config_loader
from src.agent6_render import render_html
from src.models import DeepReport, ExtractedEvent


def mk(summary, section_name, is_update, history=""):
    event = ExtractedEvent(
        event_type="产品发布",
        entities=["Acme", "Bank <One>"],
        key_numbers=["10%"],
        summary_zh=summary,
        category="产业热点",
        source_url="https://source.example/article?a=1&b=2",
        published_at="2026-09-06T01:00:00",
        domain="source.example",
        title="Acme <推出> product",
        title_zh="Acme 推出存储产品",
        industry="flash",
        vertical="finance",
    )
    return DeepReport(event, {section_name: f"{section_name}内容"}, is_update, history)


reports = [
    mk("产品摘要", "背景", False),
    mk("监管摘要", "技术分析", False),
    mk("更新摘要", "新进展", True, "此前已完成项目立项。"),
]
config = config_loader.resolve({"theme_id": "europe_storage", "theme_name": "存储产业"})
html = render_html(reports, config)
digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
print(f"sha256={digest} len={len(html)}")
