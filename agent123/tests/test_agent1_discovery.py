"""
被测目标：src/agent1_discovery.py
依赖：src/search_tool.py（SearchTool、MockSearchTool）、src/models.py（RawArticle）
覆盖场景：黑名单过滤、时间戳容错与关键词搜索失败隔离
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import mock_open

import pytest
import yaml

from conftest import make_event
from src.models import DedupResult, ExtractedEvent, RawArticle, StoryRecord

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
