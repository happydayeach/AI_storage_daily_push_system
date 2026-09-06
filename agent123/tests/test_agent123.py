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


def test_mock_search_tool_returns_complete_raw_articles():
    from src.models import RawArticle
    from src.search_tool import MockSearchTool

    articles = MockSearchTool().search("storage")

    assert 3 <= len(articles) <= 5
    assert all(isinstance(article, RawArticle) for article in articles)
    assert all(article.url and article.title and article.snippet and article.published_at and article.domain for article in articles)


def test_google_search_tool_requires_both_google_credentials(monkeypatch):
    from src.search_tool import GoogleSearchTool

    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_ID", raising=False)

    try:
        GoogleSearchTool()
    except ValueError as error:
        assert "GOOGLE_API_KEY" in str(error)
        assert "GOOGLE_CSE_ID" in str(error)
    else:
        raise AssertionError("GoogleSearchTool must reject missing Google credentials")


def test_discover_articles_filters_blacklisted_domains_and_honors_whitelist():
    from src.agent1_discovery import discover_articles
    from src.models import RawArticle
    from src.search_tool import SearchTool

    class FixedSearchTool(SearchTool):
        def search(self, keyword, hours_back=48):
            return [
                RawArticle("https://allowed.example/a", "Allowed", "Snippet", "2026-09-06T01:00:00", "allowed.example"),
                RawArticle("https://blocked.example/b", "Blocked", "Snippet", "2026-09-06T01:00:00", "blocked.example"),
                RawArticle("https://other.example/c", "Other", "Snippet", "2026-09-06T01:00:00", "other.example"),
            ]

    articles = discover_articles(
        {
            "keywords_matrix": [["storage"]],
            "source_blacklist": ["blocked.example"],
            "source_whitelist": ["allowed.example"],
        },
        FixedSearchTool(),
    )

    assert [article.domain for article in articles] == ["allowed.example"]


def test_deepseek_client_uses_environment_selected_model_without_search_parameter(monkeypatch):
    import src.llm_client as llm_client

    class FakeCompletions:
        def create(self, **kwargs):
            self.kwargs = kwargs
            return type("Response", (), {"choices": [type("Choice", (), {"message": type("Message", (), {"content": "ok"})()})()]})()

    completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = type("Chat", (), {"completions": completions})()

    monkeypatch.setattr(llm_client, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-reasoner")

    client = llm_client.DeepSeekClient(api_key="test-key")
    assert client.chat("hello") == "ok"
    assert completions.kwargs["model"] == "deepseek-reasoner"
    assert "enable" + "_search" not in completions.kwargs


def test_main_runs_mock_discovery_before_missing_deepseek_key(monkeypatch):
    import pytest
    import src.main as main

    captured = []

    def discover(theme_config, searcher):
        captured.extend(searcher.search("storage"))
        return captured

    class MissingDeepSeekClient:
        def __init__(self):
            raise ValueError("DEEPSEEK_API_KEY is required")

    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CSE_ID", raising=False)
    monkeypatch.setattr(main, "discover_articles", discover)
    monkeypatch.setattr(main, "DeepSeekClient", MissingDeepSeekClient)

    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        main.main()

    assert len(captured) == 3
