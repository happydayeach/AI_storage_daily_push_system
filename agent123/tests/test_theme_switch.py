"""
被测目标：多主题复用（config_loader + agent1/2/6 的 config 驱动）。
依赖：src/config_loader.py、src/models.py。
覆盖场景：北欧地域前缀 + education 行业标签驱动，以及 europe_storage 回归不变。
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
    assert theme_config["region"] == "北欧"
    assert theme_config["verticals"]["education"] == {
        "icon": "🎓",
        "label": "教育",
        "desc": "教育行业（教育信息化/智慧校园/在线教育）",
    }

    search_tool = FakeSearchTool()
    discover_articles(theme_config, search_tool)
    assert search_tool.queries
    assert all(query.startswith("北欧 ") for query in search_tool.queries)

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
