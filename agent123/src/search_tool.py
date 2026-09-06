"""Pluggable news search providers for Agent 1."""

import json
import os
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen

from src.models import RawArticle


class SearchTool(ABC):
    """Interface implemented by all Agent 1 news search providers."""

    @abstractmethod
    def search(self, keyword: str, hours_back: int = 48) -> List[RawArticle]:
        """Return articles relevant to ``keyword`` from the requested time window."""


class GoogleSearchTool(SearchTool):
    """Google Custom Search JSON API provider."""

    API_URL = "https://www.googleapis.com/customsearch/v1"

    def __init__(self, api_key: str | None = None, cse_id: str | None = None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.cse_id = cse_id or os.getenv("GOOGLE_CSE_ID")
        missing = [name for name, value in (("GOOGLE_API_KEY", self.api_key), ("GOOGLE_CSE_ID", self.cse_id)) if not value]
        if missing:
            raise ValueError(f"Google Custom Search requires {', '.join(missing)}")

    def search(self, keyword: str, hours_back: int = 48) -> List[RawArticle]:
        query = urlencode({"key": self.api_key, "cx": self.cse_id, "q": keyword})
        with urlopen(f"{self.API_URL}?{query}", timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))

        return [self._to_article(item) for item in payload.get("items", [])]

    @staticmethod
    def _to_article(item: Dict[str, Any]) -> RawArticle:
        url = item.get("link", "")
        snippet = item.get("snippet", "")
        metatags = (item.get("pagemap", {}).get("metatags") or [{}])[0]
        published_at = GoogleSearchTool._published_at(snippet, metatags)
        domain = urlparse(url).netloc.lower().removeprefix("www.")
        return RawArticle(
            title=item.get("title", ""),
            url=url,
            snippet=snippet,
            published_at=published_at,
            domain=domain,
        )

    @staticmethod
    def _published_at(snippet: str, metatags: Dict[str, Any]) -> str:
        for key in ("article:published_time", "datepublished", "date", "og:updated_time"):
            if metatags.get(key):
                return str(metatags[key])
        match = re.search(r"\b\w{3},?\s+\d{1,2},\s+\d{4}\b", snippet)
        if match:
            for date_format in ("%b %d, %Y", "%B %d, %Y"):
                try:
                    return datetime.strptime(match.group(0).replace("  ", " "), date_format).isoformat()
                except ValueError:
                    continue
        try:
            return parsedate_to_datetime(snippet).isoformat()
        except (TypeError, ValueError, IndexError):
            return datetime.now(timezone.utc).isoformat()


class MockSearchTool(SearchTool):
    """Deterministic local articles for development without API credentials."""

    def search(self, keyword: str, hours_back: int = 48) -> List[RawArticle]:
        timestamp = datetime.now(timezone.utc).isoformat()
        return [
            RawArticle("https://datacenter.example.com/europe-storage", "European storage operators expand capacity", f"{keyword}: operators announced new resilient storage capacity across Europe.", timestamp, "datacenter.example.com"),
            RawArticle("https://cloud.example.net/compliance", "Cloud providers publish compliance update", f"{keyword}: providers described new data governance and compliance controls.", timestamp, "cloud.example.net"),
            RawArticle("https://semiconductor.example.org/nand", "NAND suppliers outline next-generation roadmap", f"{keyword}: suppliers shared production and performance plans for enterprise storage.", timestamp, "semiconductor.example.org"),
        ]