import logging

import pytest

from src.models import DedupResult, ExtractedEvent, RawArticle, StoryRecord


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


def test_models_can_be_constructed_with_extracted_event_text_defaults():
    article = RawArticle("https://example.com", "Title", "Snippet", "2026-09-06", "example.com")
    event = make_event("摘要")
    story = StoryRecord("story-1", "theme", "2026-09-01", "2026-09-06", ["摘要"], [1.0, 0.0], [article.url], "产业热点")
    result = DedupResult([event], [{"story_id": story.story_id}], 0)

    assert article.title == "Title"
    assert event.title == ""
    assert event.snippet == ""
    assert story.story_id == "story-1"
    assert result.new == [event]


def test_mock_search_tool_returns_raw_articles_without_network():
    from src.search_tool import MockSearchTool

    articles = MockSearchTool().search("storage")

    assert articles
    assert all(isinstance(article, RawArticle) for article in articles)


def test_discover_articles_uses_mock_search_and_filters_blacklisted_domain():
    from src.agent1_discovery import discover_articles
    from src.search_tool import MockSearchTool

    discovered = discover_articles({"keywords_matrix": [["storage"]]}, MockSearchTool())
    filtered = discover_articles(
        {
            "keywords_matrix": [["storage"]],
            "source_blacklist": ["cloud.example.net"],
        },
        MockSearchTool(),
    )

    assert discovered
    assert all(isinstance(article, RawArticle) for article in discovered)
    assert all(article.domain != "cloud.example.net" for article in filtered)
    assert len(filtered) == len(discovered) - 1


def test_discover_articles_logs_warning_and_keeps_article_for_unparseable_timestamp(caplog):
    from src.agent1_discovery import discover_articles
    from src.search_tool import SearchTool

    class InvalidTimestampSearchTool(SearchTool):
        def search(self, keyword, hours_back=48):
            return [RawArticle("https://example.com/a", "Title", "Snippet", "not-a-date", "example.com")]

    with caplog.at_level(logging.WARNING, logger="src.agent1_discovery"):
        articles = discover_articles({"keywords_matrix": [["storage"]]}, InvalidTimestampSearchTool())

    assert [article.url for article in articles] == ["https://example.com/a"]
    assert "Could not parse publication time" in caplog.text


def test_deduplicator_classifies_new_update_and_duplicate_without_model_download():
    from src.agent3_dedupe import Deduplicator

    class FakeEmbedder:
        vectors = {
            "duplicate": [1.0, 0.0],
            "update": [0.8, 0.6],
            "new": [0.0, 1.0],
        }

        def encode(self, texts):
            return [self.vectors[text] for text in texts]

    historical = StoryRecord("story-1", "theme", "2026-09-01", "2026-09-06", ["duplicate"], [1.0, 0.0], ["https://old.example"], "产业热点")
    duplicate, update, new = (make_event(summary) for summary in ("duplicate", "update", "new"))

    result = Deduplicator(FakeEmbedder(), threshold_a=0.88, threshold_b=0.75).dedupe(
        [duplicate, update, new], [historical]
    )

    assert result.duplicate_dropped_count == 1
    assert result.update == [{"event": update, "story_id": "story-1", "history_summary": "duplicate"}]
    assert result.new == [new]


def test_google_search_tool_without_credentials_raises_clear_error(monkeypatch):
    from src.search_tool import GoogleSearchTool

    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_ID", raising=False)

    with pytest.raises(ValueError, match="GOOGLE_API_KEY.*GOOGLE_CSE_ID"):
        GoogleSearchTool()


def test_extract_event_parses_fixed_json_from_mocked_client():
    from src.agent2_extraction import extract_event

    class FakeDeepSeekClient:
        def chat(self, **kwargs):
            assert kwargs["max_tokens"] == 800
            return '{"event_type":"产品发布","entities":["Acme"],"key_numbers":["10%"],"summary_zh":"Acme 发布了新存储产品。","category":"产品与技术"}'

    article = RawArticle("https://example.com/product", "New product", "Details", "2026-09-06T01:00:00", "example.com")
    event = extract_event(article, FakeDeepSeekClient())

    assert event == ExtractedEvent("产品发布", ["Acme"], ["10%"], "Acme 发布了新存储产品。", "产品与技术", article.url, article.published_at, article.domain, article.title, article.snippet)
