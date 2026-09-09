from dataclasses import dataclass
from typing import Dict, List


@dataclass
class RawArticle:
    url: str
    title: str
    snippet: str
    published_at: str
    domain: str


@dataclass
class ExtractedEvent:
    event_type: str
    entities: List[str]
    key_numbers: List[str]
    summary_zh: str
    category: str
    source_url: str
    published_at: str
    domain: str
    title: str = ""
    snippet: str = ""


@dataclass
class StoryRecord:
    story_id: str
    theme_id: str
    first_seen_date: str
    last_updated_date: str
    summary_history: List[str]
    embedding: List[float]
    source_urls: List[str]
    category: str


@dataclass
class DedupResult:
    new: List[ExtractedEvent]
    update: List[Dict]
    duplicate_dropped_count: int


@dataclass
class DeepReport:
    event: ExtractedEvent
    sections: Dict[str, str]
    is_update: bool
    history_summary: str = ""
