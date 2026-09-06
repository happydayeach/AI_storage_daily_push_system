# src/agent1_discovery.py
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from src.models import RawArticle
from src.search_tool import SearchTool

logger = logging.getLogger(__name__)

class NewsSearcher:
    """Compatibility wrapper around the configured news search provider."""
    def __init__(self, searcher: SearchTool):
        self.searcher = searcher

    def search_keyword(self, keyword: str) -> List[RawArticle]:
        return self.searcher.search(keyword)

def discover_articles(theme_config: Dict[str, Any], searcher: SearchTool) -> List[RawArticle]:
    """
    Agent 1 主入口：遍历关键词矩阵，去重后返回 RawArticle 列表
    """
    news_searcher = NewsSearcher(searcher)
    keywords_matrix = theme_config.get("keywords_matrix", [])
    
    # 展平并去重关键词
    all_keywords = set()
    for group in keywords_matrix:
        for kw in group:
            all_keywords.add(kw)
    all_keywords = list(all_keywords)
    
    logger.info(f"Searching with keywords: {all_keywords}")
    
    blacklist = {domain.lower() for domain in theme_config.get("source_blacklist", [])}
    whitelist = {domain.lower() for domain in theme_config.get("source_whitelist", [])}
    raw_articles = []
    seen_urls = set()
    
    for kw in all_keywords:
        logger.info(f"Searching: {kw}")
        try:
            results = news_searcher.search_keyword(kw)
        except Exception as error:
            logger.error("Search failed for keyword %r: %s", kw, error)
            continue
        for item in results:
            url = item.url
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            domain = item.domain.lower()
            if domain in blacklist or (whitelist and domain not in whitelist):
                continue
            
            # 发布时间容错
            pub_time = item.published_at
            if pub_time:
                try:
                    dt = datetime.fromisoformat(pub_time.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    # 如果超出 48 小时，丢弃（严格过滤）
                    if (datetime.now(timezone.utc) - dt) > timedelta(hours=48):
                        continue
                except Exception as e:
                    logger.warning("Could not parse publication time %r for %s: %s", pub_time, url, e)  # 保留，让后续处理
            
            raw = RawArticle(
                url=url,
                title=item.title,
                snippet=item.snippet,
                published_at=pub_time or datetime.now(timezone.utc).isoformat(),
                domain=domain
            )
            raw_articles.append(raw)
    
    logger.info(f"Discovered {len(raw_articles)} unique articles after dedup.")
    return raw_articles
