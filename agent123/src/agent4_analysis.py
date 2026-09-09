"""Deep analysis for new and updated deduplicated events."""

import json
import logging
from typing import Dict, List

from src.llm_client import LLMClient
from src.models import DedupResult, DeepReport, ExtractedEvent, RawArticle
from src.search_tool import SearchTool

logger = logging.getLogger(__name__)


def _parse_json(response: str) -> Dict[str, str]:
    clean = response.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    elif clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    data = json.loads(clean)
    if not isinstance(data, dict):
        raise ValueError("Analysis response must be a JSON object")
    return {key: value if isinstance(value, str) else "" for key, value in data.items()}


def _event_details(event: ExtractedEvent) -> str:
    return (
        f"标题：{event.title}\n"
        f"摘要：{event.summary_zh}\n"
        f"事件类型：{event.event_type}\n"
        f"关键实体：{', '.join(event.entities)}\n"
        f"关键数字：{', '.join(event.key_numbers)}\n"
        f"来源：{event.source_url}"
    )


def _evidence_details(articles: List[RawArticle]) -> str:
    return "\n".join(f"标题：{article.title}\n摘要：{article.snippet}" for article in articles)


def _analyze_new(event: ExtractedEvent, search_tool: SearchTool, llm: LLMClient, sections: List[str]) -> DeepReport:
    keyword = event.entities[0] if event.entities else event.title
    articles = search_tool.search(keyword) + search_tool.search(keyword)
    prompt = f"""请基于事件和二次定向检索证据，生成中文深度分析报告。

事件信息：
{_event_details(event)}

检索证据：
{_evidence_details(articles)}

仅输出 JSON 对象，且必须包含以下段落：{', '.join(sections)}。每个键的值为对应段落正文。"""
    data = _parse_json(
        llm.chat(
            prompt=prompt,
            system_prompt="你是专业的存储产业新闻分析师。仅依据提供的信息进行分析。",
            max_tokens=1200,
        )
    )
    return DeepReport(event=event, sections={section: data.get(section, "") for section in sections}, is_update=False)


def _analyze_update(event: ExtractedEvent, history_summary: str, llm: LLMClient) -> DeepReport:
    prompt = f"""请根据以下历史摘要和当前事件生成中文“新进展”段落。

历史摘要：{history_summary}

当前事件：
{_event_details(event)}

仅输出 JSON 对象，格式为 {{"新进展":"段落正文"}}。"""
    data = _parse_json(
        llm.chat(
            prompt=prompt,
            system_prompt="你是专业的存储产业新闻分析师。说明相对历史信息的新增进展。",
            max_tokens=800,
        )
    )
    return DeepReport(
        event=event,
        sections={"新进展": data.get("新进展", "")},
        is_update=True,
        history_summary=history_summary,
    )


def analyze(result: DedupResult, search_tool: SearchTool, llm: LLMClient, theme_config: dict) -> List[DeepReport]:
    """Return deep reports, skipping individual events whose analysis fails."""
    reports = []
    sections = theme_config["analysis_template_sections"]

    for event in result.new:
        try:
            reports.append(_analyze_new(event, search_tool, llm, sections))
        except Exception as error:
            logger.error("Deep analysis failed for new event %r: %s", event.source_url, error)

    for update in result.update:
        event = update["event"]
        history_summary = update.get("history_summary", "")
        try:
            reports.append(_analyze_update(event, history_summary, llm))
        except Exception as error:
            logger.error("Deep analysis failed for update event %r: %s", event.source_url, error)

    return reports