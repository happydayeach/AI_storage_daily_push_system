# src/agent3_dedupe.py
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from typing import List, Dict, Any
from src.models import ExtractedEvent, StoryRecord, DedupResult
from src.embedding_client import EmbeddingClient
import logging

logger = logging.getLogger(__name__)

class Deduplicator:
    def __init__(self, embedding_client: EmbeddingClient, threshold_a: float = 0.88, threshold_b: float = 0.75):
        self.embedder = embedding_client
        self.threshold_a = threshold_a
        self.threshold_b = threshold_b

    def dedupe(self, events: List[ExtractedEvent], story_records: List[StoryRecord]) -> DedupResult:
        if not events:
            return DedupResult(new=[], update=[], duplicate_dropped_count=0)

        summaries = [ev.summary_zh for ev in events]
        current_embeddings = self.embedder.encode(summaries)

        hist_embeddings = [rec.embedding for rec in story_records] if story_records else []
        hist_summaries = [rec.summary_history[-1] for rec in story_records] if story_records else []

        new_events = []
        update_events = []
        duplicate_count = 0

        # 同批次内部去重
        internal_duplicates = set()
        for i in range(len(events)):
            if i in internal_duplicates:
                continue
            for j in range(i+1, len(events)):
                if j in internal_duplicates:
                    continue
                sim = cosine_similarity([current_embeddings[i]], [current_embeddings[j]])[0][0]
                if sim >= self.threshold_a:
                    internal_duplicates.add(j)

        for idx, ev in enumerate(events):
            if idx in internal_duplicates:
                duplicate_count += 1
                continue

            best_sim = 0.0
            best_story_id = None
            best_hist_summary = None
            if hist_embeddings:
                sims = cosine_similarity([current_embeddings[idx]], hist_embeddings)[0]
                best_idx = np.argmax(sims)
                best_sim = sims[best_idx]
                if best_sim >= self.threshold_b:
                    best_story_id = story_records[best_idx].story_id
                    best_hist_summary = story_records[best_idx].summary_history[-1]

            if best_sim >= self.threshold_a:
                duplicate_count += 1
            elif best_sim >= self.threshold_b:
                update_events.append({
                    "event": ev,
                    "story_id": best_story_id,
                    "history_summary": best_hist_summary
                })
            else:
                new_events.append(ev)

        return DedupResult(
            new=new_events,
            update=update_events,
            duplicate_dropped_count=duplicate_count
        )
