import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import mock_open

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
        def search(self, keyword):
            return [RawArticle("https://example.com/a", "Title", "Snippet", "not-a-date", "example.com")]

    with caplog.at_level(logging.WARNING, logger="src.agent1_discovery"):
        articles = discover_articles({"keywords_matrix": [["storage"]]}, InvalidTimestampSearchTool())

    assert [article.url for article in articles] == ["https://example.com/a"]
    assert "Could not parse publication time" in caplog.text


def test_discover_articles_discards_old_aware_timestamp():
    from src.agent1_discovery import discover_articles
    from src.search_tool import SearchTool

    class TimestampSearchTool(SearchTool):
        def search(self, keyword):
            return [
                RawArticle(
                    "https://example.com/old",
                    "Old",
                    "Snippet",
                    (datetime.now(timezone.utc) - timedelta(hours=60)).isoformat(),
                    "example.com",
                ),
                RawArticle(
                    "https://example.com/fresh",
                    "Fresh",
                    "Snippet",
                    datetime.now(timezone.utc).isoformat(),
                    "example.com",
                ),
            ]

    articles = discover_articles({"keywords_matrix": [["storage"]]}, TimestampSearchTool())

    assert [article.url for article in articles] == ["https://example.com/fresh"]


def test_discover_articles_discards_old_naive_timestamp():
    from src.agent1_discovery import discover_articles
    from src.search_tool import SearchTool

    class NaiveTimestampSearchTool(SearchTool):
        def search(self, keyword):
            return [
                RawArticle(
                    "https://example.com/old",
                    "Old",
                    "Snippet",
                    (datetime.now() - timedelta(hours=60)).isoformat(),
                    "example.com",
                )
            ]

    articles = discover_articles({"keywords_matrix": [["storage"]]}, NaiveTimestampSearchTool())

    assert articles == []


def test_discover_articles_continues_after_one_keyword_search_fails(caplog):
    from src.agent1_discovery import discover_articles
    from src.search_tool import SearchTool

    class PartiallyFailingSearchTool(SearchTool):
        def search(self, keyword):
            if keyword == "broken":
                raise RuntimeError("temporary search failure")
            return [RawArticle("https://example.com/good", "Good", "Snippet", "", "example.com")]

    with caplog.at_level(logging.ERROR, logger="src.agent1_discovery"):
        articles = discover_articles(
            {"keywords_matrix": [["broken", "working"]]},
            PartiallyFailingSearchTool(),
        )

    assert [article.url for article in articles] == ["https://example.com/good"]
    assert "Search failed for keyword 'broken'" in caplog.text


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


def test_tavily_search_tool_maps_results_to_raw_articles(monkeypatch):
    from src.search_tool import TavilySearchTool

    class Response:
        def read(self):
            return b'{"results":[{"title":"Storage update","url":"https://www.example.com/news","content":"European storage news","published_date":"Fri, 05 Sep 2026 12:30:00 +0000"}]}'

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr("src.search_tool.urlopen", lambda *args, **kwargs: Response())

    articles = TavilySearchTool(api_key="key").search("storage")

    assert articles == [
        RawArticle(
            "https://www.example.com/news",
            "Storage update",
            "European storage news",
            "2026-09-05T12:30:00+00:00",
            "example.com",
        )
    ]


def test_tavily_search_tool_without_credentials_raises_clear_error(monkeypatch):
    from src.search_tool import TavilySearchTool

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    with pytest.raises(ValueError, match="TAVILY_API_KEY"):
        TavilySearchTool()


def test_tavily_search_tool_returns_empty_list_when_request_fails(monkeypatch, caplog):
    from src.search_tool import TavilySearchTool

    def failing_urlopen(*args, **kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr("src.search_tool.urlopen", failing_urlopen)

    with caplog.at_level(logging.ERROR, logger="src.search_tool"):
        articles = TavilySearchTool(api_key="key").search("storage")

    assert articles == []
    assert "Tavily Search failed" in caplog.text


def test_extract_event_parses_fixed_json_from_mocked_client():
    from src.agent2_extraction import extract_event

    class FakeDeepSeekClient:
        def chat(self, **kwargs):
            assert kwargs["max_tokens"] == 800
            return '{"event_type":"产品发布","entities":["Acme"],"key_numbers":["10%"],"summary_zh":"Acme 发布了新存储产品。","category":"产品与技术"}'

    article = RawArticle("https://example.com/product", "New product", "Details", "2026-09-06T01:00:00", "example.com")
    event = extract_event(article, FakeDeepSeekClient())

    assert event == ExtractedEvent("产品发布", ["Acme"], ["10%"], "Acme 发布了新存储产品。", "产品与技术", article.url, article.published_at, article.domain, article.title, article.snippet)


@pytest.mark.parametrize(
    ("provider", "expected_model", "expected_api_key", "expected_base_url"),
    [
        ("deepseek", "deepseek-v4-pro", "deepseek-key", "https://api.deepseek.com/v1"),
        ("codex", "gpt-5.6-terra", "codex-token", "https://chatgpt.com/backend-api/codex"),
    ],
)
def test_llm_client_selects_provider_and_uses_its_api(monkeypatch, provider, expected_model, expected_api_key, expected_base_url):
    from src.llm_client import LLMClient

    created_clients = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.chat = type("Chat", (), {"completions": type("Completions", (), {"create": self.create_chat})()})()
            self.responses = type("Responses", (), {"create": self.create_response})()
            created_clients.append(self)

        def create_chat(self, **kwargs):
            self.chat_kwargs = kwargs
            return type("Response", (), {"choices": [type("Choice", (), {"message": type("Message", (), {"content": "deepseek reply"})()})()]})()

        def create_response(self, **kwargs):
            self.response_kwargs = kwargs
            return type("Response", (), {"output_text": "codex reply"})()

    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setattr("src.llm_client.OpenAI", FakeOpenAI)
    monkeypatch.setattr("builtins.open", mock_open(read_data='{"tokens":{"access_token":"codex-token","account_id":"account-1"}}'))

    result = LLMClient().chat("prompt", system_prompt="system", max_tokens=123)

    client = created_clients[0]
    assert client.kwargs["api_key"] == expected_api_key
    assert client.kwargs["base_url"] == expected_base_url
    assert result == f"{provider} reply"
    if provider == "deepseek":
        assert client.chat_kwargs == {
            "model": expected_model,
            "messages": [{"role": "system", "content": "system"}, {"role": "user", "content": "prompt"}],
            "max_tokens": 123,
            "temperature": 0.1,
            "stream": False,
            "extra_body": {"thinking": {"type": "disabled"}},
        }
    else:
        assert client.kwargs["default_headers"] == {"ChatGPT-Account-Id": "account-1"}
        assert client.response_kwargs == {
            "model": expected_model,
            "instructions": "system",
            "input": [{"role": "user", "content": "prompt"}],
            "reasoning": {"effort": "low"},
            "store": False,
            "stream": True,
        }
