"""Tester control: what does render_push_message do with frontend_url=None in THIS tree?"""
from src.agent6_render import render_push_message
from src.models import DeepReport, ExtractedEvent

event = ExtractedEvent(
    event_type="其他",
    entities=[],
    key_numbers=[],
    summary_zh="s",
    category="产业热点",
    source_url="https://s.example/a",
    published_at="2026-09-06T01:00:00",
    domain="s.example",
)
report = DeepReport(event, {}, False)
try:
    out = render_push_message([report], {"frontend_url": None})
    print("NO ERROR ->", out)
except Exception as ex:  # noqa: BLE001
    print(f"RAISED {type(ex).__name__}: {ex}")
