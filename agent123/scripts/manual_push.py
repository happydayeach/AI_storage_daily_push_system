"""手动推送测试：解析 docs/index.html 真实卡片 → 渲染推送 → pushplus 发微信。

用途：最快最便宜地验证推送效果，不重跑 LLM/搜索流水线（零额外成本、秒级）。
     docs/index.html 是上次完整流水线 render_html 的产物（30 张真实卡片），
     本脚本直接从 HTML 反解出 DeepReport，复用 render_push_message 渲染后推送。

用法（在 agent123 目录下）：
    .venv/bin/python scripts/manual_push.py                 # 默认 europe_storage + 竞对信号保持原样
    .venv/bin/python scripts/manual_push.py nordic_education # 指定主题
    .venv/bin/python scripts/manual_push.py europe_storage empty  # 竞对信号清空（测短正文多篇）
    .venv/bin/python scripts/manual_push.py europe_storage full   # 竞对信号填满（测长正文少篇）

注意：
    - 依赖 .env 里的 PUSHPLUS_TOKEN（缺失则只渲染不推送）。
    - 脚本只读 docs/index.html，不写项目数据、不动 story_store。
"""
import html as htmllib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

from src.config_loader import load_theme_config
from src.agent6_render import render_push_message
from src.agent7_push import build_adapters, push_all
from src.models import DeepReport, ExtractedEvent

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs" / "index.html"
FROZEN_CARDS = Path(__file__).resolve().parent / "real_cards.json"

_CARD_RE = re.compile(
    r'<div class="card( card--update)?" data-industry="(?P<industry>[^"]*)" '
    r'data-vertical="(?P<vertical>[^"]*)" data-type="(?P<type>\w+)">(?P<body>.*?)\n            </div>',
    re.S,
)
_LABEL_RE = re.compile(r'<div class="detail-label">(?P<label>.*?)</div><p>(?P<content>.*?)</p>', re.S)

COMPETITOR_FILLER = (
    "竞对信号：Rubrik、Cohesity、Dell、HPE 与 Pure Storage 均在争取该项目的后续阶段。"
    "各方强调不可变备份、勒索软件恢复、统一控制平面、跨云数据移动和本地服务能力；"
    "客户将依据试点结果、采购报价、迁移路径、监管审计材料与支持响应时间决定最终组合。"
)


@dataclass
class RealCard:
    index: int
    is_update: bool
    industry: str
    vertical: str
    icon: str
    title: str
    source: str = ""
    timestamp: str = ""
    structured_summary: str = ""
    sections: dict = field(default_factory=dict)
    history_summary: str = ""
    entities: list = field(default_factory=list)
    source_url: str = ""


def parse_real_cards(path: Path = DOCS) -> list:
    raw = path.read_text(encoding="utf-8")
    cards = []
    for index, match in enumerate(_CARD_RE.finditer(raw)):
        body = match.group("body")
        icon = re.search(r'<span class="card__icon">(.*?)</span>', body, re.S)
        title = re.search(r'<div class="card__title"><a href="(?P<href>[^"]*)">(?P<title>.*?)</a></div>', body, re.S)
        source = re.search(r'<span class="source">📰 <strong>(.*?)</strong></span>', body, re.S)
        timestamp = re.search(r"<span>🕒 (.*?)</span>", body, re.S)
        summary = re.search(r'<div class="structured-summary">.*?<p>(.*?)</p></div>', body, re.S)
        labeled = {htmllib.unescape(m.group("label")): htmllib.unescape(m.group("content")) for m in _LABEL_RE.finditer(body)}
        history = re.search(r'<div class="history-block">📎 历史回溯：(.*?)</div>', body, re.S)
        entities = labeled.pop("🔍 关键实体", "")
        labeled.pop("📎 来源", None)
        labeled.pop("📋 一段话总结", None)
        cards.append(
            RealCard(
                index=index,
                is_update=match.group(1) is not None,
                industry=match.group("industry"),
                vertical=match.group("vertical"),
                icon=htmllib.unescape(icon.group(1)) if icon else "",
                title=htmllib.unescape(title.group("title")) if title else "",
                source=htmllib.unescape(source.group(1)) if source else "source.example",
                timestamp=timestamp.group(1) if timestamp else "",
                structured_summary=htmllib.unescape(summary.group(1)) if summary else "",
                sections=labeled,
                history_summary=htmllib.unescape(history.group(1)) if history else "",
                entities=[e.strip() for e in entities.split("·") if e.strip()],
                source_url=(title.group("href").replace("&amp;", "&") if title else ""),
            )
        )
    return cards


def load_real_cards() -> list:
    """优先读固化的 real_cards.json，缺失时回退解析 docs/index.html。

    固化文件由 scripts/freeze_real_cards.py 生成，稳定且不依赖 docs 的 HTML 格式。
    """
    if FROZEN_CARDS.exists():
        raw = json.loads(FROZEN_CARDS.read_text(encoding="utf-8"))
        return [RealCard(**item) for item in raw]
    return parse_real_cards()


def to_reports(cards, competitor_signal: str = "keep") -> list:
    reports = []
    for card in cards:
        sections = dict(card.sections)
        if competitor_signal == "empty":
            sections.pop("竞对信号", None)
        elif competitor_signal == "full":
            sections["竞对信号"] = COMPETITOR_FILLER
        event = ExtractedEvent(
            event_type="其他",
            entities=list(card.entities),
            key_numbers=[],
            summary_zh=card.structured_summary or card.title,
            category="产业热点",
            source_url=card.source_url or "https://source.example/article",
            published_at="2026-09-15T22:00:00",
            domain=card.source or "source.example",
            title=card.title,
            industry=card.industry,
            vertical=card.vertical,
            title_zh=card.title,
            structured_summary=card.structured_summary,
        )
        reports.append(DeepReport(event, sections, card.is_update, card.history_summary))
    return reports


def main():
    load_dotenv()
    theme_id = sys.argv[1] if len(sys.argv) > 1 else "europe_storage"
    competitor_signal = sys.argv[2] if len(sys.argv) > 2 else "keep"
    if competitor_signal not in ("keep", "empty", "full"):
        print(f"竞对信号参数无效: {competitor_signal}（可选 keep/empty/full）")
        sys.exit(1)

    theme_config = load_theme_config(theme_id)
    cards = load_real_cards()
    reports = to_reports(cards, competitor_signal)
    message = render_push_message(reports, theme_config)

    print(f"主题: {theme_config['theme_id']} | 竞对信号: {competitor_signal}")
    print(f"真实卡片: {len(cards)} 张 → 实际推送 {message.count('class=card')} 篇")
    print(f"消息长度: {len(message)} 字 (预算 {theme_config.get('push_char_budget', 18000)}, 上限 20000)")

    adapters = build_adapters(theme_config)
    if not adapters:
        print("无 pushplus adapter（token 缺失），跳过推送。")
        sys.exit(0)
    results = push_all(adapters, message, title=f"{theme_config.get('page_title', '每日情报')}（手动推送演示）")
    print("推送结果:", results)


if __name__ == "__main__":
    main()
