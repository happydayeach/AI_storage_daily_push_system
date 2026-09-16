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
_FILTER_BAR_MARKER = "            <!-- FILTER_BAR -->"


def _icon_for(report: DeepReport, theme_config: dict) -> str:
    return theme_config.get("icon_map", {}).get(report.event.event_type, "")


def _template_source(theme_config: dict) -> str:
    """Return the checked-in designed frontend template without its example cards."""
    template_glob = theme_config.get("template_glob", "eu-storage-daily*.html")
    template_files = tuple(Path(__file__).resolve().parents[2].glob(template_glob))
    if len(template_files) != 1:
        raise FileNotFoundError("Designed frontend template is missing or ambiguous")
    return template_files[0].read_text(encoding="utf-8")


def _plain_tag(value: str, labels: dict) -> str:
    tag = labels.get(value)
    if not tag:
        return ""
    if isinstance(tag, dict):
        icon, label = tag["icon"], tag["label"]
    else:
        icon, label = tag
    return f"{escape(str(icon))} {escape(str(label))}"


def _tag_html(tag_class: str, value: str, labels: dict) -> str:
    tag = _plain_tag(value, labels)
    if not tag:
        return ""
    extra_class = f" tag--{value}" if tag_class == "tag--industry" else ""
    return f'<span class="tag {tag_class}{extra_class}">{tag}</span>'


def _filter_bar_html(industries: dict, verticals: dict) -> str:
    """Return config-driven filter controls for the designed template."""
    industry_buttons = "".join(
        f'<button class="filter-bar__btn" data-filter="industry:{escape(key, quote=True)}" '
        f'onclick="filterCards(this, \'industry:{escape(key, quote=True)}\')">'
        f'{escape(str(value["icon"]))} {escape(str(value["label"]))}</button>'
        for key, value in industries.items()
    )
    vertical_buttons = "".join(
        f'<button class="filter-bar__btn" data-filter="vertical:{escape(key, quote=True)}" '
        f'onclick="filterCards(this, \'vertical:{escape(key, quote=True)}\')">'
        f'{escape(str(value["icon"]))} {escape(str(value["label"]))}</button>'
        for key, value in verticals.items()
    )
    return (
        '            <div class="filter-bar__group">\n'
        '                <span class="filter-bar__group-label">🏷️ 产业</span>\n'
        '                <button class="filter-bar__btn filter-bar__btn--active" data-filter="all" '
        'onclick="filterCards(this, \'all\')">全部</button>'
        f'{industry_buttons}\n'
        '            </div>\n'
        '            <span class="filter-bar__divider">|</span>\n'
        '            <div class="filter-bar__group">\n'
        '                <span class="filter-bar__group-label">🏢 行业</span>'
        f'{vertical_buttons}\n'
        '            </div>'
    )


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
            if report.sections.get(name)
        )
    summary_block = ""
    if event.structured_summary:
        summary_block = (
            f'<div class="structured-summary"><div class="detail-label">📋 一段话总结</div>'
            f'<p>{escape(event.structured_summary)}</p></div>'
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
                {summary_block}
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
    industries = config_loader.get_industries(theme_config)
    verticals = config_loader.get_verticals(theme_config)
    industry_tags = {key: (value["icon"], value["label"]) for key, value in industries.items()}
    vertical_tags = {key: (value["icon"], value["label"]) for key, value in verticals.items()}
    grouped = defaultdict(list)
    for report in reports:
        grouped[report.event.category].append(report)
    total = len(reports)
    updates = sum(report.is_update for report in reports)
    new_count = total - updates
    industry_labels = [label for key, (_, label) in industry_tags.items() if any(report.event.industry == key for report in reports)]
    industry_text = " / ".join(industry_labels) or "无"
    summary = f"今日共 {total} 条情报，其中新事件 {new_count} 条、持续追踪 {updates} 条，覆盖产业：{industry_text}。"
    source = _template_source(theme_config)
    before_content = source[:source.index(_CONTENT_MARKER)]
    footer = source[source.index(_FOOTER_MARKER):]
    page_title = escape(str(theme_config.get("page_title", "欧洲存储市场")))
    before_content = before_content.replace("欧洲存储市场", page_title)
    footer = footer.replace("欧洲存储市场", page_title)
    before_content = before_content.replace(_FILTER_BAR_MARKER, _filter_bar_html(industries, verticals))
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


_PUSH_STYLE = """
:root{--color-primary:#1a5fb4;--color-accent:#e66100;--bg-body:#f8f9fa;--bg-card:#fff;--border-color:#e9ecef;--text-primary:#1e293b;--text-secondary:#475569;--text-muted:#94a3b8;--space-xs:.25rem;--space-sm:.5rem;--space-md:1rem;--space-lg:1.5rem;--font-size-xs:.75rem;--font-size-sm:.875rem;--font-size-base:1rem;--font-size-xl:1.25rem;--radius-sm:4px;--radius-md:8px;--shadow-sm:0 1px 2px rgba(0,0,0,.05)}
*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;background:var(--bg-body);color:var(--text-primary);padding:1rem;line-height:1.6}
.card{background:var(--bg-card);border:1px solid var(--border-color);border-radius:var(--radius-md);box-shadow:var(--shadow-sm);margin-bottom:var(--space-md);overflow:hidden}.card__header{display:grid;grid-template-columns:auto 1fr;gap:4px var(--space-md);padding:var(--space-md) var(--space-lg)}.card__icon{font-size:var(--font-size-xl);grid-row:span 3;line-height:1.4;margin-top:2px}.card__title{font-size:var(--font-size-base);font-weight:600;min-width:0}.card__title a{color:inherit;text-decoration:none}.card__tags{display:flex;flex-wrap:wrap;gap:4px 6px}.tag{align-items:center;border-radius:12px;display:inline-flex;font-size:var(--font-size-xs);font-weight:500;gap:4px;line-height:1.5;padding:1px 10px}.tag--industry{background:rgba(26,95,180,.14);border:1px solid rgba(26,95,180,.25);color:var(--color-primary)}.tag--industry.tag--data-protection{background:rgba(37,99,235,.14);border-color:rgba(37,99,235,.25);color:#2563eb}.tag--industry.tag--distributed{background:rgba(124,58,237,.14);border-color:rgba(124,58,237,.25);color:#7c3aed}.tag--industry.tag--flash{background:rgba(5,150,105,.14);border-color:rgba(5,150,105,.25);color:#059669}.tag--vertical{background:var(--bg-body);border:1px solid var(--border-color);color:var(--text-muted);font-weight:400}.tag--status{background:rgba(230,97,0,.12);border:1px solid rgba(230,97,0,.2);color:var(--color-accent)}.tag--status-new{background:rgba(22,163,74,.12);border-color:rgba(22,163,74,.2);color:#16a34a}.card__meta{color:var(--text-muted);font-size:var(--font-size-xs)}.structured-summary{border-top:1px solid var(--border-color);padding:var(--space-md) var(--space-lg) var(--space-sm)}.structured-summary p,details p{color:var(--text-secondary);font-size:var(--font-size-sm);line-height:1.7;margin-bottom:var(--space-sm)}details{border-top:1px solid var(--border-color);padding:var(--space-sm) var(--space-lg) var(--space-lg)}summary{cursor:pointer;font-weight:600;margin-bottom:var(--space-sm)}h4{color:var(--text-primary);font-size:var(--font-size-xs);font-weight:600;letter-spacing:.3px;margin:var(--space-sm) 0 2px}.history-block{background:var(--bg-body);border-left:3px solid var(--border-color);border-radius:var(--radius-sm);color:var(--text-secondary);font-size:var(--font-size-xs);margin:var(--space-sm) 0;padding:var(--space-sm) var(--space-md)}.source-link{color:var(--text-muted);font-size:var(--font-size-xs);word-break:break-all}.source-link a{color:var(--color-primary);text-decoration:none}.card--update .card__header{border-left:3px solid var(--color-accent)}
""".strip()


def _minify_push_style(style: str) -> str:
    """Inline only the single-use design tokens in the push CSS."""
    single_use_tokens = {
        "--bg-body": "#f8f9fa",
        "--bg-card": "#fff",
        "--text-primary": "#1e293b",
        "--text-secondary": "#475569",
        "--text-muted": "#94a3b8",
        "--font-size-xs": ".75rem",
        "--font-size-sm": ".875rem",
        "--font-size-base": "1rem",
        "--font-size-xl": "1.25rem",
        "--radius-sm": "4px",
        "--radius-md": "8px",
        "--shadow-sm": "0 1px 2px rgba(0,0,0,.05)",
    }
    for token, value in single_use_tokens.items():
        style = style.replace(f"{token}:{value};", "").replace(f"var({token})", value)
    for old_selector, new_selector in {
        ".card--update .card__header": ".card--update>header",
        ".card__header": ".card>header",
        ".card__icon": ".card>header>i",
        ".card__title": ".card h3",
        ".card__tags": ".card .tags",
        ".card__meta": ".card small",
    }.items():
        style = style.replace(old_selector, new_selector)

    def rgba_to_hex(match: re.Match) -> str:
        red, green, blue = (int(component) for component in match.group(1, 2, 3))
        alpha = round(float(match.group(4)) * 255)
        return f"#{red:02x}{green:02x}{blue:02x}{alpha:02x}"

    return re.sub(r"rgba\((\d+),(\d+),(\d+),([.\d]+)\)", rgba_to_hex, style)


_PUSH_STYLE = _minify_push_style(_PUSH_STYLE)


DEFAULT_PUSH_CHAR_BUDGET = 18000
DEFAULT_PUSH_MAX_REPORTS = 30


def render_push_message(
    reports: List[DeepReport],
    theme_config: dict,
    max_reports: int | None = None,
    char_budget: int | None = None,
) -> str:
    """Return an escaped, standalone HTML briefing with collapsed analysis.

    ``char_budget`` caps the final HTML's ``len()``, including the head/style
    skeleton, body, and tail. Cards are accumulated until the next card would
    exceed that budget, while retaining at least the first card. ``max_reports``
    is a hard safety-limit cap on the number of cards.
    """
    # Legacy config fallback: push_char_budget is the new setting; max_reports is now only a hard safety cap.
    max_reports = max_reports if max_reports is not None else int(theme_config.get("push_max_reports", DEFAULT_PUSH_MAX_REPORTS))
    char_budget = char_budget if char_budget is not None else int(theme_config.get("push_char_budget", DEFAULT_PUSH_CHAR_BUDGET))
    if max_reports <= 0 or char_budget <= 0:
        return ""
    sections = config_loader.get_sections(theme_config)
    industries = config_loader.get_industries(theme_config)
    verticals = config_loader.get_verticals(theme_config)
    head = f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><style>{_PUSH_STYLE}</style></head><body>'
    tail = "</body></html>"
    used = len(head) + len(tail)
    blocks = []
    for report in reports[:max_reports]:
        event = report.event
        source_url = escape(event.source_url, quote=True)
        title = escape(event.title_zh or event.title or event.summary_zh)
        summary = escape(event.structured_summary or event.summary_zh)
        card_class = "card card--update" if report.is_update else "card"
        card_open = f'<div class="{card_class}">' if report.is_update else "<div class=card>"
        tags = [
            _tag_html("tag--industry", event.industry, industries),
            _tag_html("tag--vertical", event.vertical, verticals),
            '<span class="tag tag--status">🔄 持续追踪</span>' if report.is_update else '<span class="tag tag--status tag--status-new">🆕 新事件</span>',
        ]
        names = [theme_config.get("update_section_name", "新进展")] if report.is_update else sections
        analysis = "".join(
            f'<h4>{escape(name)}</h4><p>{escape(content)}</p>'
            for name in names
            if (content := report.sections.get(name))
        )
        history = f'<div class="history-block">📎 历史回溯：{escape(report.history_summary)}</div>' if report.is_update and report.history_summary else ""
        entities = " · ".join(escape(str(entity)) for entity in (event.entities or []))
        summary_block = f'<div class="structured-summary"><h4>📋 一段话总结</h4><p>{summary}</p></div>' if summary else ""
        timestamp = escape((event.published_at or "").replace("T", " ")[:16])
        source = escape(event.domain or "来源")
        block = (
            f'{card_open}<header><i>{escape(_icon_for(report, theme_config))}</i><h3><a href="{source_url}">{title}</a></h3>'
            f'<p class=tags>{"".join(tags)}</p><small>📰 <strong>{source}</strong> · 🕒 {timestamp}</small></header>{summary_block}'
            f'<details><summary>🔍 展开深度分析</summary>{analysis}{history}<h4>🔍 关键实体</h4><p>{entities}</p>'
            f'<div class="source-link"><a href="{source_url}">📄 原文</a></div></details></div>'
        )
        if blocks and used + len(block) > char_budget:
            break
        blocks.append(block)
        used += len(block)
    return f'{head}{"".join(blocks)}{tail}'
