"""将 docs/index.html 的 30 张真实卡片固化为 scripts/real_cards.json。

一次性固化脚本：把「真实卡片数据」从渲染产物 docs/index.html 反解出来，
存成稳定的 JSON，供 manual_push.py 直接读取做推送模拟——不用重新做 LLM 分析，
也不用再依赖 docs/index.html 的 HTML 格式（它每天会被 GitHub Actions 重新生成、格式可能变）。

用法（在 agent123 目录下）：
    .venv/bin/python scripts/freeze_real_cards.py
"""
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.manual_push import parse_real_cards

OUT = Path(__file__).resolve().parent / "real_cards.json"


def main():
    cards = parse_real_cards()
    if not cards:
        print("docs/index.html 未解析出任何卡片，请先跑完整流水线生成 docs/index.html。")
        sys.exit(1)
    data = [asdict(c) for c in cards]
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with_comp = sum(1 for c in data if c["sections"].get("竞对信号"))
    print(f"已固化 {len(data)} 张真实卡片 → {OUT}")
    print(f"  is_update: {sum(1 for c in data if c['is_update'])} | 竞对信号有内容: {with_comp}")


if __name__ == "__main__":
    main()
