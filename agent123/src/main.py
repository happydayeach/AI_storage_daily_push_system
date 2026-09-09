# src/main.py
import yaml
import json
import logging
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

from src.models import StoryRecord
from src.agent1_discovery import discover_articles
from src.agent2_extraction import process_articles
from src.agent3_dedupe import Deduplicator
from src.llm_client import DeepSeekClient
from src.embedding_client import EmbeddingClient
from src.search_tool import MockSearchTool, TavilySearchTool

load_dotenv()

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

def save_story_store(theme_id: str, new_events: list, update_events: list, store_path: str = "story_store/stories.json"):
    """简化版存储，实际生产需做合并"""
    # 这里仅做演示，实际需读取原文件合并
    logger.warning("save_story_store not fully implemented yet.")

def main():
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

    deepseek = DeepSeekClient()
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
