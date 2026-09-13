"""
被测目标：src/agent6_render.py
依赖：src/models.py（DeepReport、ExtractedEvent）
覆盖场景：模板复用、更新历史、空态、HTML 转义与推送消息
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import mock_open

import pytest
import yaml

from conftest import make_event
from src.models import DedupResult, ExtractedEvent, RawArticle, StoryRecord

def test_render_html_reuses_designed_template_and_maps_new_report_tags_and_sections():
    from src.agent6_render import render_html
    from src.models import DeepReport

    event = make_event("产品摘要")
    event.event_type = "产品发布"
    event.title = "Acme <推出>存储产品"
    event.industry = "flash"
    event.vertical = "finance"
    event.entities = ["Acme", "Bank <One>"]
    report = DeepReport(event, {"背景": "背景内容", "技术分析": "技术内容", "市场影响": "市场内容", "竞对信号": "竞对内容"}, False)
    theme_config = {
        "categories": ["产业热点", "垂直行业热点", "监管与合规", "产品与技术"],
        "icon_map": {"产品发布": "🚀"},
        "theme_colors": {"primary": "#123456", "accent": "#abcdef"},
    }

    html = render_html([report], theme_config)

    assert "--color-primary" in html
    assert "@media (prefers-color-scheme: dark)" in html
    assert 'class="filter-bar"' in html
    assert "function toggleCard" in html
    assert 'id="sec-industry"' in html
    assert 'id="sec-vertical"' in html
    assert 'id="sec-regulation"' in html
    assert 'id="sec-product"' in html
    assert 'class="card" data-industry="flash" data-vertical="finance" data-type="new"' in html
    assert "🚀" in html
    assert "Acme &lt;推出&gt;存储产品" in html
    assert "💾 闪存" in html
    assert "💰 金融" in html
    assert "🆕 新事件" in html
    assert all(section in html for section in ("背景", "技术分析", "市场影响", "竞对信号"))
    assert all(content in html for content in ("背景内容", "技术内容", "市场内容", "竞对内容"))
    assert "Acme · Bank &lt;One&gt;" in html
    assert 'href="https://source.example/article"' in html
    assert "#123456" in html
    assert "#abcdef" in html


def test_render_html_renders_update_history_without_new_event_sections():
    from src.agent6_render import render_html
    from src.models import DeepReport

    event = make_event("更新摘要")
    event.industry = "data-protection"
    event.vertical = "government"
    report = DeepReport(
        event,
        {"新进展": "项目已完成首批部署。"},
        True,
        "此前已完成项目立项。",
    )

    html = render_html([report], {"categories": ["产业热点"]})

    assert 'data-type="update"' in html
    assert "🔄 持续追踪" in html
    assert "新进展" in html
    assert "项目已完成首批部署。" in html
    assert 'class="history-block"' in html
    assert "此前已完成项目立项。" in html
    assert "技术分析" not in html


def test_render_html_returns_complete_designed_skeleton_for_empty_reports():
    from src.agent6_render import render_html

    html = render_html([], {"categories": ["产业热点"]})

    assert html.startswith("<!DOCTYPE html>")
    assert "<header class=\"brief-header\">" in html
    assert 'class="filter-bar"' in html
    assert all(section_id in html for section_id in ("sec-industry", "sec-vertical", "sec-regulation", "sec-product"))
    assert "今日共 0 条情报，其中新事件 0 条、持续追踪 0 条" in html


def test_render_html_escapes_report_body_text():
    from src.agent6_render import render_html
    from src.models import DeepReport

    event = make_event("摘要")
    event.title = "<script>alert('title')</script>"
    event.entities = ["<img src=x onerror=alert(1)>"]
    report = DeepReport(event, {name: "<script>alert('body')</script>" for name in ("背景", "技术分析", "市场影响", "竞对信号")}, False)

    html = render_html([report], {})

    assert "<script>alert('title')</script>" not in html
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;script&gt;alert(&#x27;body&#x27;)&lt;/script&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


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
