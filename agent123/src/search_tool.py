"""Pluggable news search providers for Agent 1."""

import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from src.models import RawArticle

logger = logging.getLogger(__name__)


class SearchTool(ABC):
    """Interface implemented by all Agent 1 news search providers."""

    @abstractmethod
    def search(self, keyword: str) -> List[RawArticle]:
        """Return articles relevant to ``keyword``."""


class TavilySearchTool(SearchTool):
    """Tavily Search API provider."""

    API_URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            raise ValueError("Tavily Search requires TAVILY_API_KEY")

    def search(self, keyword: str) -> List[RawArticle]:
        payload = json.dumps(
            {
                "query": keyword,
                "max_results": 10,
                "topic": "news",
                "search_depth": "basic",
            }
        ).encode("utf-8")
        request = Request(
            self.API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except Exception as error:
            logger.error("Tavily Search failed for keyword %r: %s", keyword, error)
            return []

        return [self._to_article(item) for item in response_payload.get("results", [])]

    @staticmethod
    def _to_article(item: Dict[str, Any]) -> RawArticle:
        url = item.get("url", "")
        try:
            published_at = parsedate_to_datetime(item.get("published_date", "")).isoformat()
        except (TypeError, ValueError, IndexError):
            published_at = ""
        return RawArticle(
            url=url,
            title=item.get("title", ""),
            snippet=item.get("content", ""),
            published_at=published_at,
            domain=urlparse(url).netloc.lower().removeprefix("www."),
        )


class MockSearchTool(SearchTool):
    """Deterministic local articles for development without API credentials."""

    def search(self, keyword: str) -> List[RawArticle]:
        timestamp = datetime.now(timezone.utc).isoformat()
        return [
            RawArticle("https://datacenter.example.com/europe-storage", "European storage operators expand capacity", f"{keyword}: operators announced new resilient storage capacity across Europe.", timestamp, "datacenter.example.com"),
            RawArticle("https://cloud.example.net/compliance", "Cloud providers publish compliance update", f"{keyword}: providers described new data governance and compliance controls.", timestamp, "cloud.example.net"),
            RawArticle("https://semiconductor.example.org/nand", "NAND suppliers outline next-generation roadmap", f"{keyword}: suppliers shared production and performance plans for enterprise storage.", timestamp, "semiconductor.example.org"),
        ]
