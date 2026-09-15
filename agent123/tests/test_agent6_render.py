"""
被测目标：src/agent6_render.py
依赖：src/models.py（DeepReport、ExtractedEvent）
覆盖场景：模板复用、配置驱动的标题/标签（含 general）/分类/段名/模板/filter-bar、中文标题与一段话总结、更新历史、空段跳过、空态、HTML 转义与推送消息
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

    html = render_html([], {})

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


def test_render_html_places_structured_summary_between_header_and_collapsed_body():
    from src.agent6_render import render_html
    from src.models import DeepReport

    event = make_event("摘要")
    event.title = "Original English title"
    event.title_zh = "中文标题"
    event.structured_summary = "时间：今日；地点：北京；起因：扩容；经过：发布新品；结果：将带动存储升级。"
    report = DeepReport(event, {"背景": "背景内容"}, False)

    html = render_html([report], {"categories": ["产业热点"], "analysis_template_sections": ["背景"]})

    assert ">中文标题</a>" in html
    assert "Original English title" not in html
    assert "📋 一段话总结" in html
    assert event.structured_summary in html
    header_start = html.index('<div class="card__header"')
    summary_start = html.index('<div class="structured-summary">')
    body_start = html.index('<div class="card__body">')
    assert header_start < summary_start < body_start


def test_render_html_includes_visible_structured_summary_styles():
    from src.agent6_render import render_html

    html = render_html([], {})

    assert ".structured-summary {" in html
    assert "padding: var(--space-md) var(--space-lg) var(--space-sm);" in html
    assert "border-top: 1px solid var(--border-color);" in html
    assert ".structured-summary .detail-label" in html
    assert ".structured-summary p" in html


def test_render_html_falls_back_to_original_title_and_skips_empty_structured_summary():
    from src.agent6_render import render_html
    from src.models import DeepReport

    event = make_event("摘要")
    event.title = "Original English title"
    report = DeepReport(event, {"背景": "背景内容"}, False)

    html = render_html([report], {"categories": ["产业热点"], "analysis_template_sections": ["背景"]})

    assert ">Original English title</a>" in html
    assert "📋 一段话总结" not in html


def test_render_push_message_renders_escaped_complete_briefing_body_without_frontend_link():
    from src.agent6_render import render_push_message
    from src.models import DeepReport

    event = make_event("推送摘要")
    event.event_type = "合作"
    event.title = 'Acme <Storage> & "Contoso" 合作'
    event.category = "产业 & 市场"
    event.summary_zh = "摘要含 <标签> & \"引号\""
    event.source_url = 'https://source.example/article?filter="one"&sort=desc'
    event.industry = "flash"
    event.vertical = "finance"
    event.structured_summary = '结构化 <摘要> & "引号"'
    report = DeepReport(
        event,
        {
            "背景": '背景 <内容> & "引号"',
            "技术分析": "技术内容",
            "市场影响": "市场内容",
            "竞对信号": "竞对内容",
        },
        False,
    )

    message = render_push_message(
        [report],
        {
            "frontend_url": 'https://brief.example/daily?theme="storage"&lang=zh',
            "icon_map": {"合作": "🤝"},
            "industries": {"flash": {"icon": "💾", "label": '闪<存> & "硬件"'}},
            "verticals": {"finance": {"icon": "💰", "label": "金融"}},
        },
    )

    assert message.startswith('<div><b>🤝 Acme &lt;Storage&gt; &amp; &quot;Contoso&quot; 合作</b><br>')
    assert '💾 闪&lt;存&gt; &amp; &quot;硬件&quot; · 💰 金融 · 🆕 新事件<br>' in message
    assert '📋 一段话总结<br>结构化 &lt;摘要&gt; &amp; &quot;引号&quot;<br>' in message
    assert '<b>背景</b><br>背景 &lt;内容&gt; &amp; &quot;引号&quot;<br>' in message
    assert '<b>技术分析</b><br>技术内容<br>' in message
    assert '<b>市场影响</b><br>市场内容<br>' in message
    assert '<b>竞对信号</b><br>竞对内容<br>' in message
    assert '<a href="https://source.example/article?filter=&quot;one&quot;&amp;sort=desc">📄 原文</a></div>' in message
    assert "查看完整简报" not in message
    assert "brief.example" not in message
    assert "<font" not in message


def test_render_push_message_renders_complete_body_when_frontend_config_is_missing():
    from src.agent6_render import render_push_message
    from src.models import DeepReport

    event = make_event("推送摘要")
    event.source_url = "https://source.example/article"

    message = render_push_message([DeepReport(event, {"背景": "背景内容"}, False)], {})

    assert "查看完整简报" not in message
    assert "📋 一段话总结" in message
    assert "推送摘要" in message
    assert "<b>背景</b><br>背景内容" in message
    assert '<a href="https://source.example/article">📄 原文</a>' in message


def test_render_push_message_falls_back_to_summary_and_handles_empty_sections():
    from src.agent6_render import render_push_message
    from src.models import DeepReport

    event = make_event("推送摘要")
    event.source_url = "https://source.example/article"

    event.structured_summary = ""
    message = render_push_message([DeepReport(event, {}, False)], {"frontend_url": None})

    assert "📋 一段话总结<br>推送摘要" in message
    assert "<b>背景</b>" not in message
    assert "查看完整简报" not in message
    assert '<a href="https://source.example/article">📄 原文</a>' in message


def test_render_push_message_prefers_chinese_title_and_falls_back_to_original_title():
    from src.agent6_render import render_push_message
    from src.models import DeepReport

    chinese_title_event = make_event("中文标题推送摘要")
    chinese_title_event.title = "Original English title"
    chinese_title_event.title_zh = "中文推送标题"
    fallback_event = make_event("英文标题推送摘要")
    fallback_event.title = "Fallback English title"

    message = render_push_message(
        [DeepReport(chinese_title_event, {}, False), DeepReport(fallback_event, {}, False)],
        {"icon_map": {}},
    )

    assert '<div><b> 中文推送标题</b><br>' in message
    assert "Original English title" not in message
    assert '<div><b> Fallback English title</b><br>' in message
    assert message.count("<br><br>") == 1


def test_render_push_message_renders_tags_and_update_status_from_config():
    from src.agent6_render import render_push_message
    from src.models import DeepReport

    event = make_event("摘要")
    event.industry = "education"
    event.vertical = "schools"
    report = DeepReport(
        event,
        {"新进展": "新进展内容"},
        True,
        "此前进展",
    )

    message = render_push_message(
        [report],
        {
            "industries": {"education": {"icon": "🎓", "label": "教育"}},
            "verticals": {"schools": {"icon": "🏫", "label": "学校"}},
        },
    )

    assert "🎓 教育 · 🏫 学校 · 🔄 持续追踪" in message
    assert "<b>新进展</b><br>新进展内容" in message
    assert "📎 历史回溯：此前进展" in message


def test_render_push_message_skips_summary_label_when_all_summary_fields_are_empty():
    from src.agent6_render import render_push_message
    from src.models import DeepReport

    event = make_event("摘要")
    event.structured_summary = ""
    event.summary_zh = ""

    message = render_push_message([DeepReport(event, {}, False)], {})

    assert "📋 一段话总结" not in message


def test_render_push_message_skips_empty_analysis_sections():
    from src.agent6_render import render_push_message
    from src.models import DeepReport

    report = DeepReport(
        make_event("摘要"),
        {"背景": "背景内容", "技术分析": "", "市场影响": "市场内容", "竞对信号": ""},
        False,
    )

    message = render_push_message([report], {})

    assert "<b>背景</b><br>背景内容" in message
    assert "<b>市场影响</b><br>市场内容" in message
    assert "<b>技术分析</b>" not in message
    assert "<b>竞对信号</b>" not in message


def test_render_push_message_limits_reports_by_default_and_explicit_override():
    from src.agent6_render import render_push_message
    from src.models import DeepReport

    reports = [DeepReport(make_event(f"推送摘要 {index}"), {}, False) for index in range(12)]

    default_message = render_push_message(reports, {})
    explicit_message = render_push_message(reports, {}, max_reports=3)

    assert all(f"推送摘要 {index}" in default_message for index in range(10))
    assert "推送摘要 10" not in default_message
    assert default_message.count("<br><br>") == 9
    assert all(f"推送摘要 {index}" in explicit_message for index in range(3))
    assert "推送摘要 3" not in explicit_message


def test_render_push_message_uses_configured_limit_and_returns_empty_for_zero_limit():
    from src.agent6_render import render_push_message
    from src.models import DeepReport

    reports = [DeepReport(make_event(f"推送摘要 {index}"), {}, False) for index in range(10)]

    configured_message = render_push_message(reports, {"push_max_reports": 2})

    assert all(f"推送摘要 {index}" in configured_message for index in range(2))
    assert "推送摘要 2" not in configured_message
    assert render_push_message(reports, {}, max_reports=0) == ""


def test_render_html_uses_custom_tag_and_layout_configuration():
    from src.agent6_render import render_html
    from src.models import DeepReport

    event = make_event("教育摘要")
    event.category = "教育动态"
    event.industry = "education"
    event.vertical = "schools"
    report = DeepReport(event, {"概览": "自定义概览"}, False)
    theme_config = {
        "categories": [{"id": "sec-education", "label": "教育动态", "icon": "🎓"}],
        "industries": {"education": {"icon": "🎓", "label": "教育", "desc": "教育产业"}},
        "verticals": {"schools": {"icon": "🏫", "label": "学校", "desc": "学校行业"}},
        "analysis_template_sections": ["概览"],
    }

    html = render_html([report], theme_config)

    assert 'id="sec-education"' in html
    assert "🎓 教育动态（1）" in html
    assert "🎓 教育" in html
    assert "🏫 学校" in html
    assert 'data-filter="industry:education"' in html
    assert 'data-filter="vertical:schools"' in html
    assert 'data-filter="industry:flash"' not in html
    assert "自定义概览" in html


def test_render_html_uses_default_tag_metadata_when_legacy_config_omits_tags():
    from src.agent6_render import render_html
    from src.models import DeepReport

    event = make_event("默认标签摘要")
    event.industry = "flash"
    event.vertical = "finance"
    report = DeepReport(event, {"背景": "背景内容"}, False)

    html = render_html([report], {"categories": ["产业热点"]})

    assert "💾 闪存" in html
    assert "💰 金融" in html


def test_render_html_renders_default_general_industry_tag():
    from src.agent6_render import render_html
    from src.models import DeepReport

    event = make_event("通用存储摘要")
    event.industry = "general"
    report = DeepReport(event, {"背景": "企业存储管理软件更新。"}, False)

    html = render_html([report], {"categories": ["产业热点"]})

    assert 'data-industry="general"' in html
    assert "📦 通用" in html


def test_render_html_renders_nordic_general_industry_label_and_summary():
    from src.agent6_render import render_html
    from src.config_loader import load_theme_config
    from src.models import DeepReport

    event = make_event("通用存储摘要")
    event.industry = "general"
    report = DeepReport(event, {"背景": "企业存储管理软件更新。"}, False)

    html = render_html([report], load_theme_config("nordic_education"))

    assert "📦 通用" in html
    assert "覆盖产业：通用" in html


def test_render_html_generates_filter_bar_from_config_and_includes_filter_script():
    from src.agent6_render import render_html

    html = render_html([], {})

    assert 'data-filter="all"' in html
    assert 'filter-bar__btn--active' in html
    assert 'data-filter="industry:general"' in html
    assert "📦 通用" in html
    assert all(
        f'data-filter="industry:{industry}"' in html
        for industry in ("flash", "distributed", "data-protection", "general")
    )
    assert all(
        f'data-filter="vertical:{vertical}"' in html
        for vertical in ("finance", "healthcare", "manufacturing", "retail", "government", "telco")
    )
    assert "💰 金融" in html
    assert "function filterCards" in html


def test_render_html_uses_configured_page_title_in_all_template_heading_locations():
    from src.agent6_render import render_html

    html = render_html([], {"page_title": "自定义存储专题"})

    assert "<title>自定义存储专题 · 每日情报（四大分类 + 双标签）</title>" in html
    assert '<h1 class="brief-header__title">📊 自定义存储专题 · 每日情报</h1>' in html
    assert "© 2026 自定义存储专题 · 每日情报" in html
    assert "欧洲存储市场" not in html


def test_render_html_skips_empty_analysis_section_without_hiding_populated_sections():
    from src.agent6_render import render_html
    from src.models import DeepReport

    report = DeepReport(
        make_event("摘要"),
        {"背景": "背景内容", "技术分析": "技术内容", "市场影响": "市场内容", "竞对信号": ""},
        False,
    )

    html = render_html([report], {})

    assert "<div class=\"detail-label\">背景</div><p>背景内容</p>" in html
    assert "<div class=\"detail-label\">技术分析</div><p>技术内容</p>" in html
    assert "<div class=\"detail-label\">市场影响</div><p>市场内容</p>" in html
    assert '<div class="detail-label">竞对信号</div>' not in html
