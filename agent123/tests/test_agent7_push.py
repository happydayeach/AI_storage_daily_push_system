"""
被测目标：src/agent7_push.py
依赖：标准库 urllib/json
覆盖场景：Pushplus 请求、适配器构建、失败容错与下游目标区分
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import mock_open

import pytest
import yaml

from conftest import make_event
from src.models import DedupResult, ExtractedEvent, RawArticle, StoryRecord

def test_pushplus_adapter_posts_send_channel_and_option_and_accepts_success_response(monkeypatch):
    from src.agent7_push import PushplusAdapter

    captured = {}

    class Response:
        status = 200

        def read(self):
            return b'{"code": 200}'

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = request.data
        captured["content_type"] = request.get_header("Content-type")
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("src.agent7_push.urlopen", fake_urlopen)

    assert PushplusAdapter(
        "pushplus-token", send_channel="webhook", option="webhook-code"
    ).push("briefing", title="Custom title") is True
    assert captured == {
        "url": "https://www.pushplus.plus/send",
        "method": "POST",
        "body": b'{"token": "pushplus-token", "title": "Custom title", "content": "briefing", "template": "html", "channel": "webhook", "option": "webhook-code"}',
        "content_type": "application/json",
        "timeout": 15,
    }


def test_pushplus_adapter_omits_option_when_not_configured(monkeypatch):
    from src.agent7_push import PushplusAdapter

    captured = {}

    class Response:
        status = 200

        def read(self):
            return b'{"code": 200}'

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    def fake_urlopen(request, timeout):
        captured["body"] = request.data
        return Response()

    monkeypatch.setattr("src.agent7_push.urlopen", fake_urlopen)

    assert PushplusAdapter("pushplus-token").push("briefing") is True
    import json

    assert json.loads(captured["body"]) == {
        "token": "pushplus-token",
        "title": "每日情报简报",
        "content": "briefing",
        "template": "html",
        "channel": "wechat",
    }


def test_build_adapters_uses_one_pushplus_adapter_per_target(caplog):
    from src.agent7_push import PushplusAdapter, build_adapters

    adapters = build_adapters(
        {
            "push_targets": [
                {"channel": "wechat"},
                {"channel": "webhook", "option": "webhook-code", "template": "json"},
            ]
        },
        env={"PUSHPLUS_TOKEN": "environment-token"},
    )

    assert [type(adapter) for adapter in adapters] == [PushplusAdapter, PushplusAdapter]
    assert [(adapter.token, adapter.send_channel, adapter.option, adapter.template) for adapter in adapters] == [
        ("environment-token", "wechat", None, "html"),
        ("environment-token", "webhook", "webhook-code", "json"),
    ]


def test_push_returns_false_for_transport_http_and_json_failures(monkeypatch):
    from src.agent7_push import PushplusAdapter

    def failing_urlopen(*args, **kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr("src.agent7_push.urlopen", failing_urlopen)
    assert PushplusAdapter("token").push("briefing") is False

    class BadStatusResponse:
        status = 500

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr("src.agent7_push.urlopen", lambda *args, **kwargs: BadStatusResponse())
    assert PushplusAdapter("token").push("briefing") is False

    class BadJsonResponse:
        status = 200

        def read(self):
            return b"not json"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr("src.agent7_push.urlopen", lambda *args, **kwargs: BadJsonResponse())
    assert PushplusAdapter("token").push("briefing") is False

    class NonObjectJsonResponse:
        status = 200

        def read(self):
            return b"[]"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr("src.agent7_push.urlopen", lambda *args, **kwargs: NonObjectJsonResponse())
    assert PushplusAdapter("token").push("briefing") is False


def test_push_all_continues_after_adapter_exception():
    from src.agent7_push import PushAdapter, push_all

    class FailingAdapter(PushAdapter):
        channel = "failing"
        send_channel = "failing"
        option = None

        def push(self, message, title="每日情报简报"):
            raise OSError("broken")

    class SuccessfulAdapter(PushAdapter):
        channel = "successful"
        send_channel = "successful"
        option = None

        def __init__(self):
            self.calls = []

        def push(self, message, title="每日情报简报"):
            self.calls.append((message, title))
            return True

    successful = SuccessfulAdapter()

    assert push_all([FailingAdapter(), successful], "briefing", "Custom title") == {
        "failing": False,
        "successful": True,
    }
    assert successful.calls == [("briefing", "Custom title")]


def test_push_all_distinguishes_pushplus_downstream_targets(monkeypatch):
    from src.agent7_push import PushplusAdapter, push_all

    monkeypatch.setattr(PushplusAdapter, "push", lambda self, message, title: True)

    results = push_all(
        [
            PushplusAdapter("token", send_channel="wechat"),
            PushplusAdapter("token", send_channel="webhook", option="feishu"),
        ],
        "briefing",
    )

    assert results == {"wechat": True, "webhook:feishu": True}


def test_build_adapters_skips_missing_token_and_null_targets(caplog):
    from src.agent7_push import build_adapters

    assert build_adapters({"push_targets": [{"channel": "wechat"}]}, env={}) == []
    assert build_adapters({"push_targets": None}) == []
    assert "PUSHPLUS_TOKEN" in caplog.text
