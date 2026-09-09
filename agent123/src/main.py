# src/main.py
import yaml
import json
import logging
import os
from uuid import uuid4
from datetime import datetime, timedelta

from dotenv import load_dotenv

from src.models import StoryRecord
from src.agent1_discovery import discover_articles
from src.agent2_extraction import process_articles
from src.agent3_dedupe import Deduplicator
from src.llm_client import LLMClient
from src.embedding_client import EmbeddingClient
from src.search_tool import MockSearchTool, TavilySearchTool

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_story_store(theme_id: str, store_path: str = "story_store/stories.json") -> list:
    try:
        with open(store_path, "r", encoding="utf-8") as f:
            all_stories = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    
    cutoff = datetime.now() - timedelta(days=14)
    records = []
    for s in all_stories:
        if s.get("theme_id") != theme_id:
            continue
        last_updated = datetime.fromisoformat(s["last_updated_date"])
        if last_updated < cutoff:
            continue
        records.append(StoryRecord(
            story_id=s["story_id"],
            theme_id=s["theme_id"],
            first_seen_date=s["first_seen_date"],
            last_updated_date=s["last_updated_date"],
            summary_history=s["summary_history"],
            embedding=s["embedding"],
            source_urls=s["source_urls"],
            category=s.get("category", "产业热点")
        ))
    return records

def save_story_store(theme_id: str, new_events: list, update_events: list, embedder, store_path: str = "story_store/stories.json"):
    try:
        with open(store_path, "r", encoding="utf-8") as f:
            all_stories = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        all_stories = []

    for event in new_events:
        now = datetime.now().isoformat()
        embedding = embedder.encode(event.summary_zh)[0]
        all_stories.append({
            "story_id": uuid4().hex,
            "theme_id": theme_id,
            "first_seen_date": now,
            "last_updated_date": now,
            "summary_history": [event.summary_zh],
            "embedding": list(embedding),
            "source_urls": [event.source_url],
            "category": event.category,
        })

    stories_by_id = {story["story_id"]: story for story in all_stories}
    for update in update_events:
        story = stories_by_id.get(update["story_id"])
        if story is None:
            continue

        event = update["event"]
        if event.summary_zh not in story["summary_history"]:
            story["summary_history"].append(event.summary_zh)
        if event.source_url not in story["source_urls"]:
            story["source_urls"].append(event.source_url)
        story["embedding"] = list(embedder.encode(event.summary_zh)[0])
        story["last_updated_date"] = datetime.now().isoformat()

    os.makedirs(os.path.dirname(store_path) or ".", exist_ok=True)
    with open(store_path, "w", encoding="utf-8") as f:
        json.dump(all_stories, f, indent=2, ensure_ascii=False)

def main():
    load_dotenv()
    # 1. 加载配置
    with open("config/theme_europe_storage.yaml", "r", encoding="utf-8") as f:
        theme_config = yaml.safe_load(f)
    theme_id = theme_config["theme_id"]

    # 2. 初始化搜索工具和客户端
    if os.getenv("TAVILY_API_KEY"):
        searcher = TavilySearchTool()
    else:
        logger.warning("TAVILY_API_KEY is missing; using MockSearchTool for Agent 1.")
        searcher = MockSearchTool()
    # 3. Agent 1: 发现. This remains runnable with MockSearchTool even when
    # the optional DeepSeek credentials used by later stages are absent.
    logger.info("=== Agent 1: Discovery ===")
    articles = discover_articles(theme_config, searcher)
    logger.info(f"Found {len(articles)} raw articles.")

    deepseek = LLMClient()
    embedder = EmbeddingClient()

    # 4. Agent 2: 提炼（DeepSeek 非联网）
    logger.info("=== Agent 2: Extraction ===")
    events = process_articles(articles, deepseek)
    logger.info(f"Extracted {len(events)} events.")

    # 5. 加载历史 story 库
    story_records = load_story_store(theme_id)

    # 6. Agent 3: 去重
    logger.info("=== Agent 3: Deduplication ===")
    deduper = Deduplicator(embedder, threshold_a=0.88, threshold_b=0.75)
    result = deduper.dedupe(events, story_records)

    logger.info(f"New: {len(result.new)}, Update: {len(result.update)}, Duplicates dropped: {result.duplicate_dropped_count}")

    save_story_store(theme_id, result.new, result.update, embedder)

    # 7. 输出结果
    output_data = {
        "new": [vars(e) for e in result.new],
        "update": [
            {
                "event": vars(u["event"]),
                "story_id": u["story_id"],
                "history_summary": u["history_summary"]
            }
            for u in result.update
        ],
        "duplicate_dropped_count": result.duplicate_dropped_count
    }
    os.makedirs("output", exist_ok=True)
    with open("output/agent123_result.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    logger.info("Results saved to output/agent123_result.json")

if __name__ == "__main__":
    main()
