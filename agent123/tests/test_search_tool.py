"""
被测目标：src/search_tool.py
依赖：src/models.py（RawArticle）
覆盖场景：mock 搜索、Tavily 映射、凭据校验与请求失败容错
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import mock_open

import pytest
import yaml

from conftest import make_event
from src.models import DedupResult, ExtractedEvent, RawArticle, StoryRecord

def test_mock_search_tool_returns_raw_articles_without_network():
    from src.search_tool import MockSearchTool

    articles = MockSearchTool().search("storage")

    assert articles
    assert all(isinstance(article, RawArticle) for article in articles)


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
