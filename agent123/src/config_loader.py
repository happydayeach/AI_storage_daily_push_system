"""Load and normalize per-theme configuration files."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Dict, List

import yaml

_DEFAULT_CATEGORIES = [
    {"id": "sec-industry", "label": "产业热点", "icon": "🏭"},
    {"id": "sec-vertical", "label": "垂直行业热点", "icon": "📊"},
    {"id": "sec-regulation", "label": "监管与合规", "icon": "⚖️"},
    {"id": "sec-product", "label": "产品与技术", "icon": "🚀"},
]
_DEFAULT_INDUSTRIES = {
    "flash": {"icon": "💾", "label": "闪存", "desc": "闪存存储硬件（NAND/SSD/存储芯片/DRAM）"},
    "distributed": {"icon": "🌐", "label": "分布式", "desc": "分布式存储/边缘存储/多云/数据湖"},
    "data-protection": {"icon": "📀", "label": "数据保护", "desc": "数据保护/GDPR/数据合规/数据主权"},
}
_DEFAULT_VERTICALS = {
    "finance": {"icon": "💰", "label": "金融", "desc": "金融行业"},
    "healthcare": {"icon": "🏥", "label": "医疗", "desc": "医疗行业"},
    "manufacturing": {"icon": "🏭", "label": "制造", "desc": "制造行业"},
    "retail": {"icon": "🛒", "label": "零售", "desc": "零售行业"},
    "government": {"icon": "🏛️", "label": "政府", "desc": "政府/公共部门"},
    "telco": {"icon": "📡", "label": "运营商", "desc": "电信运营商"},
}
_DEFAULT_EVENT_TYPES = ["财报", "漏洞", "产品发布", "监管", "合作", "并购", "其他"]
_DEFAULT_RELEVANCE_THEME = "存储产业（数据存储、云存储、闪存、NAND、SSD、存储芯片、DRAM、分布式存储、边缘存储、数据湖、企业级存储、数据保护/GDPR）"


def load_theme_config(theme_id: str = "europe_storage") -> dict:
    """Read a theme YAML file without applying compatibility defaults."""
    path = Path(__file__).resolve().parents[1] / "config" / f"theme_{theme_id}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Theme configuration not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def resolve(config: dict) -> dict:
    """Return a copy of *config* with missing multi-theme fields populated."""
    resolved = deepcopy(config)
    theme_id = resolved.get("theme_id", "")
    defaults = {
        "theme_name": theme_id,
        "region": "",
        "relevance_theme": _DEFAULT_RELEVANCE_THEME,
        "categories": _DEFAULT_CATEGORIES,
        "industries": _DEFAULT_INDUSTRIES,
        "verticals": _DEFAULT_VERTICALS,
        "event_types": _DEFAULT_EVENT_TYPES,
        "update_section_name": "新进展",
        "template_glob": "eu-storage-daily*.html",
    }
    for key, value in defaults.items():
        if key not in resolved:
            resolved[key] = deepcopy(value)
    return resolved


def get_categories(config: dict) -> List[dict]:
    """Normalize legacy string categories and new object categories."""
    categories = resolve(config)["categories"]
    if all(isinstance(category, str) for category in categories):
        return [
            {
                "id": _DEFAULT_CATEGORIES[index]["id"],
                "label": label,
                "icon": _DEFAULT_CATEGORIES[index]["icon"],
            }
            for index, label in enumerate(categories)
        ]
    return categories


def get_industries(config: dict) -> Dict[str, dict]:
    """Return the configured industry metadata."""
    return resolve(config)["industries"]


def get_verticals(config: dict) -> Dict[str, dict]:
    """Return the configured vertical metadata."""
    return resolve(config)["verticals"]


def get_sections(config: dict) -> List[str]:
    """Return the analysis section names."""
    return config.get("analysis_template_sections", [])


def get_event_types(config: dict) -> List[str]:
    """Return the configured event type names."""
    return resolve(config)["event_types"]
