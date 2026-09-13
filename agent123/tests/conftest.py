"""Shared test helpers extracted from the legacy test module."""

from src.models import ExtractedEvent


def make_event(summary: str) -> ExtractedEvent:
    return ExtractedEvent(
        event_type="其他",
        entities=[],
        key_numbers=[],
        summary_zh=summary,
        category="产业热点",
        source_url="https://source.example/article",
        published_at="2026-09-06T01:00:00",
        domain="source.example",
    )
