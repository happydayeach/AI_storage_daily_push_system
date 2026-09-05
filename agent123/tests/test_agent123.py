from dataclasses import fields


def test_data_models_match_the_specification():
    from src.models import DedupResult, ExtractedEvent, RawArticle, StoryRecord

    assert [field.name for field in fields(RawArticle)] == [
        "url", "title", "snippet", "published_at", "domain"
    ]
    assert [field.name for field in fields(ExtractedEvent)] == [
        "event_type", "entities", "key_numbers", "summary_zh", "category",
        "source_url", "published_at", "domain", "title", "snippet",
    ]
    assert ExtractedEvent("other", [], [], "summary", "category", "url", "date", "domain").title == ""
    assert ExtractedEvent("other", [], [], "summary", "category", "url", "date", "domain").snippet == ""
    assert [field.name for field in fields(StoryRecord)] == [
        "story_id", "theme_id", "first_seen_date", "last_updated_date",
        "summary_history", "embedding", "source_urls", "category",
    ]
    assert [field.name for field in fields(DedupResult)] == [
        "new", "update", "duplicate_dropped_count"
    ]


def test_load_story_store_returns_empty_list_for_invalid_json(tmp_path):
    from src.main import load_story_store

    store_path = tmp_path / "stories.json"
    store_path.write_text("", encoding="utf-8")

    assert load_story_store("theme", str(store_path)) == []


def test_format_iso8601_returns_second_precision_timestamp():
    from datetime import datetime

    from src.utils import format_iso8601

    assert format_iso8601(datetime(2026, 9, 6, 1, 2, 3)) == "2026-09-06T01:02:03"
