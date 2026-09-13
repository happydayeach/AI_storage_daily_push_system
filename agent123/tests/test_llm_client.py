"""
被测目标：src/llm_client.py
依赖：OpenAI 客户端、Codex 认证文件
覆盖场景：供应商选择、凭据和 API 调用参数
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import mock_open

import pytest
import yaml

from conftest import make_event
from src.models import DedupResult, ExtractedEvent, RawArticle, StoryRecord

@pytest.mark.parametrize(
    ("provider", "expected_model", "expected_api_key", "expected_base_url"),
    [
        ("deepseek", "deepseek-v4-flash", "deepseek-key", "https://api.deepseek.com/v1"),
        ("codex", "gpt-5.6-terra", "codex-token", "https://chatgpt.com/backend-api/codex"),
    ],
)
def test_llm_client_selects_provider_and_uses_its_api(monkeypatch, provider, expected_model, expected_api_key, expected_base_url):
    from src.llm_client import LLMClient

    created_clients = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.chat = type("Chat", (), {"completions": type("Completions", (), {"create": self.create_chat})()})()
            self.responses = type("Responses", (), {"create": self.create_response})()
            created_clients.append(self)

        def create_chat(self, **kwargs):
            self.chat_kwargs = kwargs
            return type("Response", (), {"choices": [type("Choice", (), {"message": type("Message", (), {"content": "deepseek reply"})()})()]})()

        def create_response(self, **kwargs):
            self.response_kwargs = kwargs
            return type("Response", (), {"output_text": "codex reply"})()

    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setattr("src.llm_client.OpenAI", FakeOpenAI)
    monkeypatch.setattr("builtins.open", mock_open(read_data='{"tokens":{"access_token":"codex-token","account_id":"account-1"}}'))

    result = LLMClient().chat("prompt", system_prompt="system", max_tokens=123)

    client = created_clients[0]
    assert client.kwargs["api_key"] == expected_api_key
    assert client.kwargs["base_url"] == expected_base_url
    assert result == f"{provider} reply"
    if provider == "deepseek":
        assert client.chat_kwargs == {
            "model": expected_model,
            "messages": [{"role": "system", "content": "system"}, {"role": "user", "content": "prompt"}],
            "max_tokens": 123,
            "temperature": 0.1,
            "stream": False,
            "extra_body": {"thinking": {"type": "disabled"}},
        }
    else:
        assert client.kwargs["default_headers"] == {"ChatGPT-Account-Id": "account-1"}
        assert client.response_kwargs == {
            "model": expected_model,
            "instructions": "system",
            "input": [{"role": "user", "content": "prompt"}],
            "reasoning": {"effort": "low"},
            "store": False,
            "stream": True,
        }
