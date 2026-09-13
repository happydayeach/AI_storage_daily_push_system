"""Render deep-analysis reports as the designed HTML briefing or push text."""

from collections import defaultdict
from html import escape
from pathlib import Path
import re
from typing import List

from . import config_loader
from .models import DeepReport


_CONTENT_MARKER = "        <!-- ============================================================\n        内容区：四大分类"
_FOOTER_MARKER = "        <!-- ===== 页脚 ===== -->"


def _icon_for(report: DeepReport, theme_config: dict) -> str:
    return theme_config.get("icon_map", {}).get(report.event.event_type, "")


def _template_source(theme_config: dict) -> str:
    """Return the checked-in designed frontend template without its example cards."""
    template_glob = theme_config.get("template_glob", "eu-storage-daily*.html")
    template_files = tuple(Path(__file__).resolve().parents[2].glob(template_glob))
    if len(template_files) != 1:
        raise FileNotFoundError("Designed frontend template is missing or ambiguous")
    return template_files[0].read_text(encoding="utf-8")


def _tag_html(tag_class: str, value: str, labels: dict) -> str:
    tag = labels.get(value)
    if not tag:
        return ""
    icon, label = tag
    extra_class = f" tag--{value}" if tag_class == "tag--industry" else ""
    return f'<span class="tag {tag_class}{extra_class}">{icon} {label}</span>'


def _card_html(report: DeepReport, theme_config: dict, sections: List[str], industry_tags: dict, vertical_tags: dict) -> str:
    event = report.event
    title = escape(event.title_zh or event.title or event.summary_zh)
    source_url = escape(event.source_url, quote=True)
    industry = escape(event.industry, quote=True)
    vertical = escape(event.vertical, quote=True)
    event_type = "update" if report.is_update else "new"
    card_class = "card card--update" if report.is_update else "card"
    tags = [
        _tag_html("tag--industry", event.industry, industry_tags),
        _tag_html("tag--vertical", event.vertical, vertical_tags),
        '<span class="tag tag--status">🔄 持续追踪</span>' if report.is_update else '<span class="tag tag--status tag--status-new">🆕 新事件</span>',
    ]
    if report.is_update:
        body = (
            f'<div class="detail-label">📌 {escape(theme_config.get("update_section_name", "新进展"))}</div>'
            f'<p>{escape(report.sections.get(theme_config.get("update_section_name", "新进展"), ""))}</p>'
        )
        if report.history_summary:
            body += f'<div class="history-block">📎 历史回溯：{escape(report.history_summary)}</div>'
    else:
        body = "".join(
            f'<div class="detail-label">{escape(name)}</div><p>{escape(report.sections.get(name, ""))}</p>'
            for name in sections
        )
    if event.structured_summary:
        body = (
            f'<div class="structured-summary"><div class="detail-label">📋 一段话总结</div>'
            f'<p>{escape(event.structured_summary)}</p></div>{body}'
        )
    entities = " · ".join(escape(str(entity)) for entity in event.entities)
    timestamp = escape((event.published_at or "").replace("T", " ")[:16])
    source = escape(event.domain or "来源")
    return f'''            <div class="{card_class}" data-industry="{industry}" data-vertical="{vertical}" data-type="{event_type}">
                <div class="card__header" onclick="toggleCard(this)">
                    <span class="card__icon">{escape(_icon_for(report, theme_config))}</span>
                    <div class="card__info">
                        <div class="card__title"><a href="{source_url}">{title}</a></div>
                        <div class="card__tags">{"".join(tags)}</div>
                        <div class="card__meta"><span class="source">📰 <strong>{source}</strong></span><span>🕒 {timestamp}</span></div>
                    </div>
                    <span style="color:var(--text-muted);font-size:var(--font-size-sm);">▼</span>
                </div>
                <div class="card__body">
                    {body}
                    <div class="detail-label">🔍 关键实体</div><p>{entities}</p>
                    <div class="detail-label">📎 来源</div><div class="source-link"><a href="{source_url}">来源链接</a></div>
                </div>
            </div>'''


def _section_html(category: str, section_id: str, icon: str, reports: List[DeepReport], theme_config: dict, sections: List[str], industry_tags: dict, vertical_tags: dict) -> str:
    cards = "\n".join(_card_html(report, theme_config, sections, industry_tags, vertical_tags) for report in reports)
    return f'''        <section class="section" id="{section_id}">
            <div class="section__header"><h2>{icon} {escape(category)}</h2><span class="section-count">{len(reports)} 条</span></div>
{cards}
        </section>'''


def render_html(reports: List[DeepReport], theme_config: dict) -> str:
    """Return the checked-in designed briefing page populated with report data."""
    categories = config_loader.get_categories(theme_config)
    sections = config_loader.get_sections(theme_config)
    industry_tags = {key: (value["icon"], value["label"]) for key, value in config_loader.get_industries(theme_config).items()}
    vertical_tags = {key: (value["icon"], value["label"]) for key, value in config_loader.get_verticals(theme_config).items()}
    grouped = defaultdict(list)
    for report in reports:
        grouped[report.event.category].append(report)
    total = len(reports)
    updates = sum(report.is_update for report in reports)
    new_count = total - updates
    industries = [label for key, (_, label) in industry_tags.items() if any(report.event.industry == key for report in reports)]
    industry_text = " / ".join(industries) or "无"
    summary = f"今日共 {total} 条情报，其中新事件 {new_count} 条、持续追踪 {updates} 条，覆盖产业：{industry_text}。"
    source = _template_source(theme_config)
    before_content = source[:source.index(_CONTENT_MARKER)]
    footer = source[source.index(_FOOTER_MARKER):]
    page_title = escape(str(theme_config.get("page_title", "欧洲存储市场")))
    before_content = before_content.replace("欧洲存储市场", page_title)
    footer = footer.replace("欧洲存储市场", page_title)
    colors = theme_config.get("theme_colors", {})
    before_content = before_content.replace("--color-primary: #1a5fb4;", f'--color-primary: {escape(colors.get("primary", "#1a5fb4"), quote=True)};', 1)
    before_content = before_content.replace("--color-accent: #e66100;", f'--color-accent: {escape(colors.get("accent", "#e66100"), quote=True)};', 1)
    before_content = re.sub(r"(<span class=\"brief-header__date\">📅 )[^<]+", r"\g<1>每日更新", before_content)
    before_content = re.sub(r"(<span class=\"count\">)10(?=</span> 条)", rf"\g<1>{total}", before_content)
    before_content = re.sub(r"(<span class=\"count\">)6(?=</span>)", rf"\g<1>{new_count}", before_content, count=1)
    before_content = re.sub(r"(<span class=\"count\">)4(?=</span>)", rf"\g<1>{updates}", before_content, count=1)
    before_content = re.sub(r"(<div class=\"executive-summary__text\">).*?(</div>)", rf"\g<1>{escape(summary)}\g<2>", before_content, flags=re.DOTALL)
    nav = "\n".join(
        f'            <a href="#{category["id"]}" class="category-nav__link{" category-nav__link--active" if index == 0 else ""}">{category["icon"]} {escape(category["label"])}（{len(grouped[category["label"]])}）</a>'
        for index, category in enumerate(categories)
    )
    before_content = re.sub(r"(<nav class=\"category-nav\" id=\"categoryNav\">).*?(</nav>)", rf"\g<1>\n{nav}\n        \g<2>", before_content, flags=re.DOTALL)
    sections = "\n\n".join(
        _section_html(category["label"], category["id"], category["icon"], grouped[category["label"]], theme_config, sections, industry_tags, vertical_tags)
        for category in categories
    )
    return f"{before_content}{sections}\n\n{footer}"


def render_push_message(reports: List[DeepReport], theme_config: dict) -> str:
    """Return one concise plain-text push block for each report."""
    blocks = []
    for report in reports:
        event = report.event
        icon = _icon_for(report, theme_config)
        title = event.title_zh or event.title or event.summary_zh
        blocks.append(f"{icon} {title}｜{event.category}\n{event.summary_zh}\n{event.source_url}")
    return "\n\n".join(blocks)