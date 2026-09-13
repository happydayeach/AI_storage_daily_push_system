"""review probe: push message frontend/source links + render_html regression snapshot.

Usage: python probe_push_frontend_url.py <repo_root>
  repo_root = dir containing agent123/ (i.e. AI_storage_daily_push_system)
Prints one JSON blob prefixed with PROBE_JSON.
"""

import hashlib
import json
import sys
import traceback
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repo_root / "agent123"))

from src import config_loader  # noqa: E402
from src.agent6_render import render_html, render_push_message  # noqa: E402
from src.models import DeepReport, ExtractedEvent  # noqa: E402

EXPECTED = "https://happydayeach.github.io/AI_storage_daily_push_system/"
out = {"repo_root": str(repo_root)}


def rec(key, fn):
    try:
        out[key] = fn()
    except Exception as exc:  # noqa: BLE001
        out[key] = f"RAISED {type(exc).__name__}: {exc}"
        out[key + ":tb"] = traceback.format_exc().strip().splitlines()[-1]


def make_event(summary="摘要", title_zh="中文标题"):
    return ExtractedEvent(
        event_type="合作",
        entities=["Acme"],
        key_numbers=[],
        summary_zh=summary,
        category="产业 & 市场",
        source_url='https://source.example/article?filter="one"&sort=desc',
        published_at="2026-09-13T10:00:00+00:00",
        domain="source.example",
        title="Acme <Storage> & \"Contoso\" 合作",
        title_zh=title_zh,
    )


# --- 1. configs declare the public Pages URL -------------------------------
for theme in ("europe_storage", "nordic_education"):
    rec(f"config.{theme}.frontend_url", lambda t=theme: config_loader.load_theme_config(t).get("frontend_url"))
    rec(
        f"config.{theme}.resolved_frontend_url",
        lambda t=theme: config_loader.resolve(config_loader.load_theme_config(t)).get("frontend_url"),
    )
    rec(
        f"config.{theme}.exact_match",
        lambda t=theme: config_loader.load_theme_config(t).get("frontend_url") == EXPECTED,
    )
    rec(
        f"config.{theme}.no_secret_like_keys",
        lambda t=theme: sorted(
            k for k in config_loader.load_theme_config(t) if any(s in k.lower() for s in ("token", "key", "secret", "password"))
        ),
    )

# --- 2. push message with real config --------------------------------------
real_cfg = config_loader.resolve(config_loader.load_theme_config("europe_storage"))
real_cfg["frontend_url"] = EXPECTED
plain_report = DeepReport(make_event(), {}, False)
plain_msg = render_push_message([plain_report], real_cfg)
out["push.real_config_message"] = plain_msg
out["push.has_frontend_href"] = f'href="{EXPECTED}"' in plain_msg
out["push.has_frontend_label"] = "🔗 查看完整简报" in plain_msg
out["push.has_source_label"] = '📄 原文</a>' in plain_msg
out["push.frontend_before_source"] = (
    plain_msg.index("查看完整简报") < plain_msg.index("📄 原文")
    if "查看完整简报" in plain_msg and "📄 原文" in plain_msg
    else "N/A (frontend link absent)"
)
out["push.source_href_escaped"] = 'href="https://source.example/article?filter=&quot;one&quot;&amp;sort=desc"' in plain_msg
out["push.no_raw_quote_in_href"] = 'filter="one"' not in plain_msg
out["push.no_raw_amp_before_sort"] = "&sort" not in plain_msg
out["push.single_br_between_links"] = "查看完整简报</a><br><a href=\"https://source.example" in plain_msg
out["push.title_escaped"] = "Acme &lt;Storage&gt; &amp; &quot;Contoso&quot; 合作" in plain_msg

# --- 3. frontend_url missing / empty / None / whitespace -------------------
for label, cfg in (
    ("missing", {"categories": ["产业热点"]}),
    ("empty_str", {"frontend_url": ""}),
    ("none", {"frontend_url": None}),
    ("whitespace", {"frontend_url": "   "}),
):
    rec(f"degrade.{label}.message", lambda c=cfg: render_push_message([plain_report], c))
    rec(
        f"degrade.{label}.no_frontend_link",
        lambda c=cfg: "查看完整简报" not in render_push_message([plain_report], c),
    )
    rec(
        f"degrade.{label}.keeps_source_link",
        lambda c=cfg: '📄 原文</a>' in render_push_message([plain_report], c),
    )

# --- 4. injection-shaped frontend_url -------------------------------------
rec(
    "inject.frontend_url_escaped",
    lambda: render_push_message(
        [plain_report],
        {"frontend_url": 'https://x.example/?a="1"&b=<2>'},
    ),
)

# --- 5. render_html regression snapshot ------------------------------------
rec("render_html.sha256", lambda: hashlib.sha256(render_html([plain_report], real_cfg).encode("utf-8")).hexdigest())
rec("render_html.length", lambda: len(render_html([plain_report], real_cfg)))
rec("render_html.no_push_labels", lambda: ("查看完整简报" not in render_html([plain_report], real_cfg)))

print("PROBE_JSON " + json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True))
