# src/agent2_extraction.py
import json
import logging
from typing import List, Optional
from src.models import RawArticle, ExtractedEvent
from src.llm_client import LLMClient

logger = logging.getLogger(__name__)

def extract_event(article: RawArticle, llm_client: LLMClient) -> Optional[ExtractedEvent]:
    """
    使用 DeepSeek（关闭联网）根据标题和片段进行结构化提取。
    """
    prompt = f"""
请根据以下新闻信息，提取关键字段并以 JSON 格式返回。

新闻标题：{article.title}
新闻摘要（Snippet）：{article.snippet}
发布时间：{article.published_at}
来源域名：{article.domain}

请输出 JSON，包含以下字段：
- "event_type": 事件类型，从 ["财报", "漏洞", "产品发布", "监管", "合作", "并购", "其他"] 中选择。
- "entities": 关键实体列表（公司名、产品名、法规名等）。
- "key_numbers": 关键数字或日期列表（如金额、百分比、发布日期）。
- "summary_zh": 用中文转述摘要，严禁逐句引用原文，必须用自己的话重新组织，控制在 100-150 字。
- "category": 分类，从 ["产业热点", "垂直行业热点", "监管与合规", "产品与技术"] 中选择一个最合适的。
- "relevant": 布尔值。判断这篇新闻是否与“存储产业”直接相关——相关主题包括：数据存储、云存储、闪存、NAND、SSD、存储芯片、DRAM、分布式存储、边缘存储、数据湖、企业级存储、以及数据保护/GDPR（存储数据合规）。若新闻属于纯金融/证券合规、博彩、家庭教育、体育、医药、政治等与存储无关的主题，填 false。

**只输出 JSON，不要有其他任何文字。**
"""
    try:
        response = llm_client.chat(
            prompt=prompt,
            system_prompt="你是一个专业的技术新闻分析师，擅长结构化信息提取。",
            max_tokens=800
        )
        # 清理响应
        clean = response.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        data = json.loads(clean)
        if data.get("relevant") is False:
            logger.info(f"Skipping irrelevant article: {article.url}")
            return None
        entities = data.get("entities", [])
        if not isinstance(entities, list):
            entities = []
        key_numbers = data.get("key_numbers", [])
        if not isinstance(key_numbers, list):
            key_numbers = []
        
        event = ExtractedEvent(
            event_type=data.get("event_type", "其他"),
            entities=entities,
            key_numbers=key_numbers,
            summary_zh=data.get("summary_zh", ""),
            category=data.get("category", "产业热点"),  # 新增分类字段
            source_url=article.url,
            published_at=article.published_at,
            domain=article.domain,
            title=article.title,
            snippet=article.snippet
        )
        return event
    except Exception as e:
        logger.error(f"Extraction failed for {article.url}: {e}")
        return None

def process_articles(articles: List[RawArticle], llm_client: LLMClient) -> List[ExtractedEvent]:
    events = []
    for art in articles:
        logger.info(f"Extracting from: {art.title[:50]}...")
        ev = extract_event(art, llm_client)
        if ev:
            events.append(ev)
    return events
