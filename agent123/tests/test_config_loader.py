"""
被测目标：src/config_loader.py
依赖：yaml
覆盖场景：默认值兜底（含通用产业标签）+ categories 双格式兼容。
"""

from pathlib import Path

import pytest

from src.config_loader import (
    get_categories,
    get_event_types,
    get_industries,
    get_sections,
    get_verticals,
    load_theme_config,
    resolve,
)


def test_load_theme_config_reads_existing_yaml():
    config = load_theme_config()

    assert config["theme_id"] == "europe_storage"
    assert config["categories"] == ["产业热点", "垂直行业热点", "监管与合规", "产品与技术"]


def test_load_theme_config_reports_missing_theme_file():
    with pytest.raises(FileNotFoundError, match="Theme configuration not found: .*theme_missing_theme.yaml"):
        load_theme_config("missing_theme")


def test_resolve_supplies_defaults_without_overwriting_explicit_values():
    explicit_industries = {"custom": {"icon": "X", "label": "自定义", "desc": "自定义行业"}}
    config = resolve({"theme_id": "custom", "region": "APAC", "industries": explicit_industries})

    assert config["theme_name"] == "custom"
    assert config["region"] == "APAC"
    assert config["industries"] == explicit_industries
    assert config["verticals"]["finance"] == {"icon": "💰", "label": "金融", "desc": "金融行业"}
    assert config["event_types"] == ["财报", "漏洞", "产品发布", "监管", "合作", "并购", "其他"]
    assert config["update_section_name"] == "新进展"
    assert config["template_glob"] == "eu-storage-daily*.html"


def test_get_industries_includes_default_general_storage_tag():
    assert get_industries({})["general"] == {
        "icon": "📦",
        "label": "通用",
        "desc": "存储相关但不属于闪存/分布式/数据保护",
    }


def test_load_nordic_education_config_includes_explicit_general_industry():
    industries = get_industries(load_theme_config("nordic_education"))

    assert industries["general"] == {
        "icon": "📦",
        "label": "通用",
        "desc": "存储相关但不属于闪存/分布式/数据保护",
    }


def test_get_categories_normalizes_legacy_string_list():
    categories = get_categories({"categories": ["产业热点", "垂直行业热点", "监管与合规", "产品与技术"]})

    assert categories == [
        {"id": "sec-industry", "label": "产业热点", "icon": "🏭"},
        {"id": "sec-vertical", "label": "垂直行业热点", "icon": "📊"},
        {"id": "sec-regulation", "label": "监管与合规", "icon": "⚖️"},
        {"id": "sec-product", "label": "产品与技术", "icon": "🚀"},
    ]


def test_get_categories_preserves_dict_format():
    categories = [{"id": "custom", "label": "自定义", "icon": "✨"}]

    assert get_categories({"categories": categories}) == categories


def test_resolve_supplies_default_analysis_template_sections():
    assert resolve({})["analysis_template_sections"] == ["背景", "技术分析", "市场影响", "竞对信号"]


def test_get_sections_falls_back_to_default_when_sections_are_missing():
    assert get_sections({"theme_id": "custom"}) == ["背景", "技术分析", "市场影响", "竞对信号"]


def test_accessors_return_resolved_metadata_and_sections():
    config = {"analysis_template_sections": ["背景", "技术分析", "市场影响", "竞对信号"]}

    assert get_industries(config)["flash"] == {
        "icon": "💾",
        "label": "闪存",
        "desc": "闪存存储硬件（NAND/SSD/存储芯片/DRAM）",
    }
    assert get_verticals(config)["government"] == {
        "icon": "🏛️",
        "label": "政府",
        "desc": "政府/公共部门",
    }
    assert get_sections(config) == ["背景", "技术分析", "市场影响", "竞对信号"]
    assert get_event_types(config) == ["财报", "漏洞", "产品发布", "监管", "合作", "并购", "其他"]
