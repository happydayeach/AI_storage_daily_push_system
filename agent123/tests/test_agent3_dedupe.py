"""
被测目标：src/agent3_dedupe.py
依赖：src/models.py（ExtractedEvent、StoryRecord、DedupResult）
覆盖场景：新增、更新与重复事件分类
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import mock_open

import pytest
import yaml

from conftest import make_event
from src.models import DedupResult, ExtractedEvent, RawArticle, StoryRecord

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
