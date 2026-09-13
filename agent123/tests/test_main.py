"""
被测目标：src/main.py
依赖：src/models.py、src/config_loader.py、src/agent7_push.py、GitHub Actions workflow
覆盖场景：故事存储、THEME 驱动配置加载、QA 失败继续输出与定时工作流
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import mock_open

import pytest
import yaml

from conftest import make_event
from src.models import DedupResult, ExtractedEvent, RawArticle, StoryRecord

def test_save_story_store_adds_new_event_with_serializable_embedding(tmp_path):
    from src.main import save_story_store

    class FakeEmbedder:
        def __init__(self):
            self.calls = []

        def encode(self, text):
            self.calls.append(text)
            return [[0.25, 0.75]]

    store_path = tmp_path / "stories.json"
    event = make_event("新增摘要")
    embedder = FakeEmbedder()

    save_story_store("theme-a", [event], [], embedder, str(store_path))

    import json

    stored = json.loads(store_path.read_text(encoding="utf-8"))
    assert len(stored) == 1
    record = stored[0]
    assert len(record["story_id"]) == 32
    assert record["theme_id"] == "theme-a"
    assert record["summary_history"] == ["新增摘要"]
    assert record["embedding"] == [0.25, 0.75]
    assert record["source_urls"] == [event.source_url]
    assert record["category"] == event.category
    assert record["first_seen_date"] == record["last_updated_date"]
    assert embedder.calls == ["新增摘要"]


def test_save_story_store_updates_matching_story_without_duplicate_history_or_urls(tmp_path):
    import json

    from src.main import save_story_store

    class FakeEmbedder:
        def encode(self, text):
            assert text == "更新摘要"
            return [[0.9, 0.1]]

    store_path = tmp_path / "stories.json"
    store_path.write_text(
        json.dumps([
            {
                "story_id": "target-story",
                "theme_id": "theme-a",
                "first_seen_date": "2026-01-01T00:00:00",
                "last_updated_date": "2026-01-02T00:00:00",
                "summary_history": ["旧摘要"],
                "embedding": [1.0, 0.0],
                "source_urls": ["https://source.example/article"],
                "category": "产业热点",
            },
            {
                "story_id": "other-story",
                "theme_id": "theme-b",
                "first_seen_date": "2026-01-01T00:00:00",
                "last_updated_date": "2026-01-02T00:00:00",
                "summary_history": ["其他"],
                "embedding": [0.0, 1.0],
                "source_urls": ["https://other.example/article"],
                "category": "市场动态",
            },
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    event = make_event("更新摘要")
    update = {"event": event, "story_id": "target-story", "history_summary": "旧摘要"}

    save_story_store("theme-a", [], [update, update], FakeEmbedder(), str(store_path))

    stored = json.loads(store_path.read_text(encoding="utf-8"))
    target = next(record for record in stored if record["story_id"] == "target-story")
    assert target["summary_history"] == ["旧摘要", "更新摘要"]
    assert target["source_urls"] == ["https://source.example/article"]
    assert target["embedding"] == [0.9, 0.1]
    assert target["last_updated_date"] != "2026-01-02T00:00:00"
    assert next(record for record in stored if record["story_id"] == "other-story")["embedding"] == [0.0, 1.0]


def test_main_continues_after_qa_failure_and_writes_rendered_outputs(monkeypatch, tmp_path):
    import json

    from src import config_loader, main
    from src.agent7_push import PushplusAdapter
    from src.models import DeepReport

    event = make_event("缺字段的摘要")
    event.entities = ["Acme"]
    event.title = "Acme 动态"
    report = DeepReport(event, {"背景": ""}, False)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "theme_europe_storage.yaml").write_text(
        "theme_id: test\nanalysis_template_sections: [背景]\npush_targets:\n  - channel: wechat\n",
        encoding="utf-8",
    )

    class Response:
        status = 200

        def read(self):
            return b'{"code": 200}'

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    loaded_theme_ids = []
    theme_config = {
        "theme_id": "nordic_education",
        "analysis_template_sections": ["背景"],
        "push_targets": [{"channel": "wechat"}],
    }

    def load_theme_config(theme_id):
        loaded_theme_ids.append(theme_id)
        return theme_config

    requests = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("THEME", "nordic_education")
    monkeypatch.setattr(config_loader, "load_theme_config", load_theme_config)
    monkeypatch.setattr(main, "load_dotenv", lambda: None)
    monkeypatch.setattr(main, "LLMClient", lambda: object())
    monkeypatch.setattr(main, "EmbeddingClient", lambda: object())
    monkeypatch.setattr(main, "discover_articles", lambda config, searcher: [])
    monkeypatch.setattr(main, "process_articles", lambda articles, llm, theme_config: [])
    monkeypatch.setattr(main, "load_story_store", lambda theme_id: [])
    monkeypatch.setattr(main, "save_story_store", lambda *args: None)
    monkeypatch.setattr(main, "analyze", lambda result, searcher, llm, config: [report])
    monkeypatch.setattr(main, "build_adapters", lambda config: [PushplusAdapter("token")])
    monkeypatch.setattr("src.agent7_push.urlopen", lambda request, timeout: requests.append(request) or Response())

    main.main()

    assert loaded_theme_ids == ["nordic_education"]
    output = tmp_path / "output"
    repo_root = Path(main.__file__).resolve().parents[2]
    assert (repo_root / "docs" / "index.html").is_file()
    assert not (tmp_path / "docs" / "index.html").exists()
    saved = json.loads((output / "agent123_result.json").read_text(encoding="utf-8"))
    assert saved["qa"] == {"passed": False, "valid": 0, "total": 1, "issues": ["报告 Acme 动态 缺少或为空: sections.背景"]}
    assert len(requests) == 1


def test_daily_workflow_is_valid_and_configures_scheduled_secret_backed_pipeline():
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "daily.yml"

    assert workflow_path.is_file()
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    triggers = workflow.get("on", workflow.get(True))

    assert triggers["schedule"] == [{"cron": "0 6 * * *"}]
    assert triggers["workflow_dispatch"] == {}
    assert workflow["jobs"]["briefing"]["permissions"] == {"contents": "write"}
    assert "THEME: europe_storage" in workflow_text
    assert "LLM_PROVIDER: deepseek" in workflow_text
    assert "git add docs/ agent123/output/" in workflow_text
    assert "git push origin HEAD:" in workflow_text
    for secret_name in ("DEEPSEEK_API_KEY", "TAVILY_API_KEY", "PUSHPLUS_TOKEN"):
        assert f"${{{{ secrets.{secret_name} }}}}" in workflow_text
