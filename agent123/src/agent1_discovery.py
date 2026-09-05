# src/agent1_discovery.py
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from src.models import RawArticle
from src.llm_client import DeepSeekClient

logger = logging.getLogger(__name__)

class DeepSeekNewsSearcher:
    """使用 DeepSeek 联网搜索获取新闻"""
    def __init__(self, llm_client: DeepSeekClient):
        self.llm = llm_client

    def search_keyword(self, keyword: str, hours_back: int = 48) -> List[Dict]:
        """
        对单个关键词进行联网搜索，返回新闻列表
        """
        # 计算时间窗口
        now = datetime.now()
        start_time = (now - timedelta(hours=hours_back)).strftime("%Y-%m-%d %H:%M")
        end_time = now.strftime("%Y-%m-%d %H:%M")

        prompt = f"""
请搜索过去 {hours_back} 小时内（{start_time} 至 {end_time}）发布的、与“{keyword}”相关的最新英文新闻。

要求：
1. 返回一个 JSON 数组，每个元素包含以下字段：
   - "title": 新闻标题
   - "url": 新闻链接（必须是真实可访问的 URL）
   - "snippet": 新闻摘要（50-100个英文单词，概括核心内容）
   - "published_at": 发布时间（ISO 8601 格式，如 2026-08-28T10:30:00）
   - "domain": 来源域名（如 techcrunch.com）
2. 只返回过去 48 小时内的内容，拒绝过期新闻。
3. 优先选择权威技术媒体（如 TechCrunch, The Register, DataCenterDynamics, Blocks & Files, 路透社, 彭博等）。
4. 如果搜索结果少于 3 条，也请返回实际条数，不要虚构。
5. **只输出 JSON 数组，不要有任何额外的文字、解释或 Markdown 标记。**

搜索结果：
"""
        try:
            response = self.llm.chat(
                prompt=prompt,
                system_prompt="你是一个专业的新闻检索助手，擅长使用联网功能获取最新资讯。",
                enable_search=True,  # 关键
                max_tokens=2000
            )
            # 清理可能的 Markdown 标记
            clean = response.strip()
            if clean.startswith("```json"):
                clean = clean[7:]
            if clean.endswith("```"):
                clean = clean[:-3]
            if clean.startswith("```"):
                clean = clean[3:]
            data = json.loads(clean)
            if isinstance(data, list):
                return data
            else:
                logger.warning(f"Unexpected response format for {keyword}: {data}")
                return []
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for keyword '{keyword}': {e}\nResponse: {response[:200]}")
            return []
        except Exception as e:
            logger.error(f"Search error for '{keyword}': {e}")
            return []

def discover_articles(theme_config: Dict[str, Any], llm_client: DeepSeekClient) -> List[RawArticle]:
    """
    Agent 1 主入口：遍历关键词矩阵，去重后返回 RawArticle 列表
    """
    searcher = DeepSeekNewsSearcher(llm_client)
    keywords_matrix = theme_config.get("keywords_matrix", [])
    
    # 展平并去重关键词
    all_keywords = set()
    for group in keywords_matrix:
        for kw in group:
            all_keywords.add(kw)
    all_keywords = list(all_keywords)
    
    logger.info(f"Searching with keywords: {all_keywords}")
    
    raw_articles = []
    seen_urls = set()
    
    for kw in all_keywords:
        logger.info(f"Searching: {kw}")
        results = searcher.search_keyword(kw)
        for item in results:
            url = item.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            
            # 发布时间容错
            pub_time = item.get("published_at")
            if pub_time:
                try:
                    dt = datetime.fromisoformat(pub_time.replace("Z", "+00:00"))
                    # 如果超出 48 小时，丢弃（严格过滤）
                    if (datetime.now() - dt) > timedelta(hours=48):
                        continue
                except:
                    pass  # 如果时间格式不对，保留，让后续处理
            
            raw = RawArticle(
                url=url,
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
                published_at=pub_time or datetime.now().isoformat(),
                domain=item.get("domain", "").lower()
            )
            raw_articles.append(raw)
    
    logger.info(f"Discovered {len(raw_articles)} unique articles after dedup.")
    return raw_articles
