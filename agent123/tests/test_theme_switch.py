"""
被测目标：多主题复用（config_loader + agent1/2/6 的 config 驱动）。
依赖：src/config_loader.py、src/models.py。
覆盖场景：北欧地域前缀 + education 行业标签和页面标题驱动，以及 europe_storage 回归不变。
"""

from src import config_loader
from src.agent1_discovery import discover_articles
from src.agent2_extraction import extract_event
from src.agent6_render import render_html
from src.models import DeepReport, ExtractedEvent, RawArticle


class FakeSearchTool:
    def __init__(self):
        self.queries = []

    def search(self, keyword):
        self.queries.append(keyword)
        return []


class FakeLLM:
    def __init__(self):
        self.prompt = ""

    def chat(self, **kwargs):
        self.prompt = kwargs["prompt"]
        return (
            '{"event_type":"产品发布","entities":[],"key_numbers":[],'
            '"summary_zh":"北欧教育存储新闻。","category":"产品与技术",'
            '"industry":"flash","vertical":"education","relevant":true}'
        )


def test_nordic_education_theme_drives_search_extraction_and_rendering_without_code_changes():
    theme_config = config_loader.load_theme_config("nordic_education")

    assert theme_config["theme_id"] == "nordic_education"
    assert theme_config["region"] == ["Sweden", "Finland", "Denmark", "Iceland", "Norway"]
    assert theme_config["verticals"]["education"] == {
        "icon": "🎓",
        "label": "教育",
        "desc": "教育行业（教育信息化/智慧校园/在线教育）",
    }

    search_tool = FakeSearchTool()
    discover_articles(theme_config, search_tool)
    expected_queries = [
        f"{country} {keyword}"
        for keyword_group in theme_config["keywords_matrix"]
        for keyword in keyword_group
        for country in theme_config["region"]
    ]
    assert search_tool.queries == expected_queries
    assert len(search_tool.queries) == 60

    article = RawArticle(
        "https://example.com/education",
        "Nordic campus storage",
        "Education storage deployment",
        "2026-09-13T00:00:00",
        "example.com",
    )
    llm = FakeLLM()
    event = extract_event(article, llm, theme_config)
    assert event is not None
    assert '"education"' in llm.prompt
    assert "education=教育（教育行业（教育信息化/智慧校园/在线教育））" in llm.prompt

    report = DeepReport(event, {section: "内容" for section in theme_config["analysis_template_sections"]}, False)
    html = render_html([report], theme_config)
    assert "🎓 教育" in html


def test_europe_storage_theme_keeps_existing_vertical_labels_without_education():
    europe_config = config_loader.load_theme_config("europe_storage")

    assert "education" not in config_loader.get_verticals(europe_config)


def test_theme_page_titles_render_from_each_theme_configuration():
    nordic_config = config_loader.load_theme_config("nordic_education")
    europe_config = config_loader.load_theme_config("europe_storage")

    nordic_html = render_html([], nordic_config)
    europe_html = render_html([], europe_config)

    assert nordic_config["page_title"] == "北欧存储·教育行业"
    assert "<title>北欧存储·教育行业 · 每日情报（四大分类 + 双标签）</title>" in nordic_html
    assert '<h1 class="brief-header__title">📊 北欧存储·教育行业 · 每日情报</h1>' in nordic_html
    assert "© 2026 北欧存储·教育行业 · 每日情报" in nordic_html
    assert europe_config["page_title"] == "欧洲存储市场"
    assert "<title>欧洲存储市场 · 每日情报（四大分类 + 双标签）</title>" in europe_html
    assert '<h1 class="brief-header__title">📊 欧洲存储市场 · 每日情报</h1>' in europe_html
    assert "© 2026 欧洲存储市场 · 每日情报" in europe_html
