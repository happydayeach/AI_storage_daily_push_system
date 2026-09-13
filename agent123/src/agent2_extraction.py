# src/agent2_extraction.py
import json
import logging
from typing import List, Optional
from src import config_loader
from src.models import RawArticle, ExtractedEvent
from src.llm_client import LLMClient

logger = logging.getLogger(__name__)

def extract_event(article: RawArticle, llm_client: LLMClient, theme_config: dict) -> Optional[ExtractedEvent]:
    """
    使用 DeepSeek（关闭联网）根据标题和片段进行结构化提取。
    """
    event_types = config_loader.get_event_types(theme_config)
    categories = [category["label"] for category in config_loader.get_categories(theme_config)]
    relevance_theme = config_loader.resolve(theme_config)["relevance_theme"]
    industries = "; ".join(
        f"{key}={metadata['label']}（{metadata['desc']}）"
        for key, metadata in config_loader.get_industries(theme_config).items()
    )
    verticals = "; ".join(
        f"{key}={metadata['label']}（{metadata['desc']}）"
        for key, metadata in config_loader.get_verticals(theme_config).items()
    )
    prompt = f"""
请根据以下新闻信息，提取关键字段并以 JSON 格式返回。

新闻标题：{article.title}
新闻摘要（Snippet）：{article.snippet}
发布时间：{article.published_at}
来源域名：{article.domain}

请输出 JSON，包含以下字段：
- "event_type": 事件类型，从 {json.dumps(event_types, ensure_ascii=False)} 中选择。
- "entities": 关键实体列表（公司名、产品名、法规名等）。
- "key_numbers": 关键数字或日期列表（如金额、百分比、发布日期）。
- "summary_zh": 用中文转述摘要，严禁逐句引用原文，必须用自己的话重新组织，控制在 100-150 字。
- "title_zh": 新闻标题的中文翻译。
- "structured_summary": 一段话总结，不超过 200 字，按“时间、地点、起因、经过、结果”归纳；结果部分须用一句话分析该新闻对存储行业的影响。
- "category": 分类，从 {json.dumps(categories, ensure_ascii=False)} 中选择一个最合适的。
- "relevant": 布尔值。判断这篇新闻是否与“{relevance_theme}”直接相关；与该主题无关时填 false。
- "industry": 产业标签，从 [{", ".join(json.dumps(key, ensure_ascii=False) for key in config_loader.get_industries(theme_config))}] 选一个，不属于任何产业填 ""。判断标准：{industries}。
- "vertical": 行业标签，从 [{", ".join(json.dumps(key, ensure_ascii=False) for key in config_loader.get_verticals(theme_config))}] 选一个，不涉及特定垂直行业填 ""。对应：{verticals}。

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
        industry = data.get("industry", "")
        if not isinstance(industry, str):
            industry = ""
        vertical = data.get("vertical", "")
        if not isinstance(vertical, str):
            vertical = ""
        title_zh = data.get("title_zh", "")
        if not isinstance(title_zh, str):
            title_zh = ""
        structured_summary = data.get("structured_summary", "")
        if not isinstance(structured_summary, str):
            structured_summary = ""
        
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
            snippet=article.snippet,
            industry=industry,
            vertical=vertical,
            title_zh=title_zh,
            structured_summary=structured_summary,
        )
        return event
    except Exception as e:
        logger.error(f"Extraction failed for {article.url}: {e}")
        return None

def process_articles(articles: List[RawArticle], llm_client: LLMClient, theme_config: dict) -> List[ExtractedEvent]:
    events = []
    for art in articles:
        logger.info(f"Extracting from: {art.title[:50]}...")
        ev = extract_event(art, llm_client, theme_config)
        if ev:
            events.append(ev)
    return events
