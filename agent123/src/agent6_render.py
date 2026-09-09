"""Render deep-analysis reports as an HTML briefing or push notification."""

from html import escape
from typing import List

from .models import DeepReport


_SECTION_NAMES = ("背景", "技术分析", "市场影响", "竞对信号")


def _icon_for(report: DeepReport, theme_config: dict) -> str:
    return theme_config.get("icon_map", {}).get(report.event.event_type, "")


def _card_html(report: DeepReport, theme_config: dict) -> str:
    event = report.event
    icon = escape(_icon_for(report, theme_config))
    title = escape(event.title or event.summary_zh)
    category = escape(event.category)
    source_url = escape(event.source_url, quote=True)
    sections = "".join(
        f'<div class="detail-label">{escape(section_name)}</div>'
        f'<p>{escape(report.sections.get(section_name, ""))}</p>'
        for section_name in _SECTION_NAMES
    )
    return f'''<article class="card">
  <div class="card__header">
    <span class="card__icon">{icon}</span>
    <div class="card__info">
      <h2 class="card__title">{title}</h2>
      <span class="tag">{category}</span>
    </div>
  </div>
  <div class="card__body">
    {sections}
    <div class="source-link"><a href="{source_url}">来源链接</a></div>
  </div>
</article>'''


def render_html(reports: List[DeepReport], theme_config: dict) -> str:
    """Return a self-contained HTML page containing one card per report."""
    colors = theme_config.get("theme_colors", {})
    primary = escape(colors.get("primary", ""), quote=True)
    accent = escape(colors.get("accent", ""), quote=True)
    categories = " · ".join(escape(category) for category in theme_config.get("categories", []))
    cards = "\n".join(_card_html(report, theme_config) for report in reports)
    return f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>每日情报</title>
<style>
:root {{ --color-primary: {primary}; --color-accent: {accent}; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f8f9fa; color: #1e293b; line-height: 1.6; padding: 1.5rem; }}
.container {{ max-width: 1024px; margin: 0 auto; }}
.card {{ background: #fff; border: 1px solid #e9ecef; border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,.05); margin-bottom: 1rem; overflow: hidden; }}
.card__header {{ display: flex; gap: 1rem; padding: 1rem 1.5rem; border-left: 4px solid var(--color-accent); }}
.card__icon {{ font-size: 1.25rem; }}
.card__info {{ flex: 1; }}
.card__title {{ font-size: 1rem; margin: 0 0 .25rem; }}
.tag {{ display: inline-block; padding: 1px 10px; border-radius: 12px; color: var(--color-primary); background: color-mix(in srgb, var(--color-primary) 14%, transparent); }}
.card__body {{ border-top: 1px solid #e9ecef; padding: 1rem 1.5rem; }}
.detail-label {{ color: var(--color-primary); font-weight: 600; font-size: .875rem; margin-top: .5rem; }}
.card__body p {{ margin: .15rem 0 .5rem; }}
.source-link a {{ color: var(--color-primary); word-break: break-all; }}
</style>
</head>
<body>
<main class="container">
<header><h1>每日情报</h1><p>{categories}</p></header>
{cards}
</main>
</body>
</html>'''


def render_push_message(reports: List[DeepReport], theme_config: dict) -> str:
    """Return one concise plain-text push block for each report."""
    blocks = []
    for report in reports:
        event = report.event
        icon = _icon_for(report, theme_config)
        title = event.title or event.summary_zh
        blocks.append(f"{icon} {title}｜{event.category}\n{event.summary_zh}\n{event.source_url}")
    return "\n\n".join(blocks)

