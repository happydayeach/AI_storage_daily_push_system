"""Tester independent probe: render_push_message frontend URL (card t_98f219ea).

Does NOT import dev tests. Runs against the candidate tree via PYTHONPATH.
"""
from __future__ import annotations

import html
import re
import traceback

from src import config_loader
from src.agent6_render import render_push_message
from src.models import DeepReport, ExtractedEvent

PAGES = "https://happydayeach.github.io/AI_storage_daily_push_system/"
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))


def mk(summary: str, source_url: str, title_zh: str = "") -> DeepReport:
    event = ExtractedEvent(
        event_type="其他",
        entities=[],
        key_numbers=[],
        summary_zh=summary,
        category="产业热点",
        source_url=source_url,
        published_at="2026-09-06T01:00:00",
        domain="source.example",
        title_zh=title_zh,
    )
    return DeepReport(event, {}, False)


def hrefs(msg: str) -> list[str]:
    return re.findall(r'href="([^"]*)"', msg)


# ---------------------------------------------------------------- 3. happy path
for theme in ("europe_storage", "nordic_education"):
    cfg = config_loader.load_theme_config(theme)
    check(f"[{theme}] raw config frontend_url == Pages URL", cfg.get("frontend_url") == PAGES,
          repr(cfg.get("frontend_url")))
    resolved = config_loader.resolve(cfg)
    check(f"[{theme}] resolve() keeps frontend_url", resolved.get("frontend_url") == PAGES,
          repr(resolved.get("frontend_url")))

    src_url = "https://source.example/news/2026/acme-storage"
    msg = render_push_message([mk("摘要内容", src_url, "中文标题")], cfg)
    check(f"[{theme}] main link href present", f'href="{PAGES}"' in msg, msg[:200])
    check(f"[{theme}] 🔗 查看完整简报 present", "🔗 查看完整简报" in msg)
    check(f"[{theme}] 📄 原文 + source_url present",
          f'<a href="{src_url}">📄 原文</a>' in msg, msg)
    check(f"[{theme}] legacy 查看原文 dropped", "查看原文" not in msg)
    check(f"[{theme}] main link before source link",
          0 <= msg.index(f'href="{PAGES}"') < msg.index(f'href="{src_url}"'))
    check(f"[{theme}] exactly one main + one source link per report",
          len(hrefs(msg)) == 2 and hrefs(msg)[0] == PAGES and hrefs(msg)[1] == src_url,
          str(hrefs(msg)))
    check(f"[{theme}] frontend link separated by <br>",
          f'<a href="{PAGES}">🔗 查看完整简报</a><br><a href="{src_url}">📄 原文</a>' in msg)
    # a resolved (defaults-applied) config must behave identically
    msg_resolved = render_push_message([mk("摘要内容", src_url, "中文标题")], resolved)
    check(f"[{theme}] resolved config output identical", msg_resolved == msg)

# ------------------------------------------------- 3b. escaping / injection
src_special = 'https://source.example/a?b="x"&c=<y>&d=1'
front_special = 'https://brief.example/?q="a"&b=<c>'
cfg_special = {"frontend_url": front_special}
msg = render_push_message([mk('摘要含 <tag> & "quote"', src_special)], cfg_special)
check("escape: frontend URL escaped (&quot;/&amp;/&lt; present)",
      "&quot;" in msg and "&amp;" in msg and "&lt;" in msg, msg)
check("escape: source href rendered escaped",
      'href="https://source.example/a?b=&quot;x&quot;&amp;c=&lt;y&gt;&amp;d=1"' in msg, msg)
check("escape: frontend href rendered escaped",
      'href="https://brief.example/?q=&quot;a&quot;&amp;b=&lt;c&gt;"' in msg, msg)
got = hrefs(msg)
check("escape: raw quotes/angle brackets never break out of attribute",
      len(got) == 2 and all(('"' not in h and "<" not in h and ">" not in h) for h in got), str(got))
check("escape: href values round-trip to originals",
      got == [html.escape(front_special, quote=True), html.escape(src_special, quote=True)], str(got))
check("escape: summary text escaped",
      "摘要含 &lt;tag&gt; &amp; &quot;quote&quot;" in msg, msg)

# ------------------------------------------------- 4/6. degradation
degrade_cases = [
    ("None", {"frontend_url": None}),
    ("whitespace '   '", {"frontend_url": "   "}),
    ("tab/newline whitespace", {"frontend_url": "\t\n "}),
    ("empty string", {"frontend_url": ""}),
    ("missing key {}", {}),
]
src_url = "https://source.example/article"
for label, cfg in degrade_cases:
    try:
        msg = render_push_message([mk("摘要内容", src_url)], cfg)
    except Exception:
        check(f"degrade[{label}]: no exception", False, traceback.format_exc().splitlines()[-1])
        continue
    check(f"degrade[{label}]: no exception", True)
    check(f"degrade[{label}]: no 查看完整简报", "查看完整简报" not in msg, msg)
    check(f"degrade[{label}]: renders 📄 原文 link only",
          f'<a href="{src_url}">📄 原文</a></div>' in msg and msg.count("<a ") == 1, msg)
    check(f"degrade[{label}]: summary <br> directly precedes source link (no leftover frontend break)",
          msg.endswith(f'摘要内容<br><a href="{src_url}">📄 原文</a></div>') and "<br><br>" not in msg
          and '<a href="">' not in msg, msg)

# ------------------------------------------------- multi-report sanity
two = render_push_message([mk("A", "https://s.example/1"), mk("B", "https://s.example/2")],
                          {"frontend_url": PAGES})
check("multi: one main link per report (2)", two.count(f'href="{PAGES}"') == 2, str(hrefs(two)))
check("multi: blocks joined by <br><br>", "<br><br>" in two and len(two.split("<br><br>")) == 2)

# ------------------------------------------------- report
failed = [r for r in RESULTS if not r[1]]
for name, ok, detail in RESULTS:
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if not ok and detail:
        print(f"      detail: {detail}")
print(f"\nTOTAL {len(RESULTS)}  PASS {len(RESULTS) - len(failed)}  FAIL {len(failed)}")
raise SystemExit(1 if failed else 0)
