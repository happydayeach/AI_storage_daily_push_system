"""review probe 2: escaping of title/summary/source_url + whitespace-only frontend_url."""

import sys
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(repo_root / "agent123"))

from src.agent6_render import render_push_message  # noqa: E402
from src.models import DeepReport, ExtractedEvent  # noqa: E402

e = ExtractedEvent(
    event_type="合作",
    entities=[],
    key_numbers=[],
    summary_zh='摘要 <x> & "y"',
    category="产业",
    source_url="https://s.example/a?b=1&c=2",
    published_at="2026-09-13",
    domain="s.example",
    title="T",
    title_zh='中文 <标题> & "引号"',
)
cfg = {"frontend_url": "https://happydayeach.github.io/AI_storage_daily_push_system/"}
m = render_push_message([DeepReport(e, {}, False)], cfg)
print("MESSAGE:", m)
assert '中文 &lt;标题&gt; &amp; &quot;引号&quot;' in m, "title not escaped"
assert '摘要 &lt;x&gt; &amp; &quot;y&quot;' in m, "summary not escaped"
assert 'href="https://s.example/a?b=1&amp;c=2"' in m, "source url not escaped"
assert 'href="https://happydayeach.github.io/AI_storage_daily_push_system/"' in m
print("TITLE/SUMMARY/SOURCE ESCAPING OK")

ws = render_push_message([DeepReport(e, {}, False)], {"frontend_url": "   "})
print("WHITESPACE-ONLY RESULT:", ws)
