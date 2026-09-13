"""Unified external push adapters for daily intelligence briefings."""

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Callable, List, Mapping
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_DEFAULT_TITLE = "每日情报简报"
_PUSHPLUS_URL = "http://www.pushplus.plus/send"
_PLACEHOLDERS = {"", "your_token", "your_webhook"}


class PushAdapter(ABC):
    """Common interface for outbound push channels."""

    channel: str

    @abstractmethod
    def push(self, message: str, title: str = _DEFAULT_TITLE) -> bool:
        """Send a briefing and return whether the channel accepted it."""


class _JsonWebhookAdapter(PushAdapter):
    """Base implementation for JSON POST webhook adapters."""

    def _post(self, url: str, payload: dict, success_fn: Callable[[dict], bool]) -> bool:
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                if response.status != 200:
                    logger.warning("%s push failed with HTTP status %s", self.channel, response.status)
                    return False
                response_payload = json.loads(response.read().decode("utf-8"))
        except Exception as error:
            logger.warning("%s push failed: %s", self.channel, error)
            return False

        if not isinstance(response_payload, dict) or not success_fn(response_payload):
            logger.warning("%s push rejected: %s", self.channel, response_payload)
            return False
        return True


class PushplusAdapter(_JsonWebhookAdapter):
    """Pushplus adapter using the token-based send endpoint."""

    channel = "pushplus"

    def __init__(self, token: str):
        self.token = token

    def push(self, message: str, title: str = _DEFAULT_TITLE) -> bool:
        return self._post(
            _PUSHPLUS_URL,
            {"token": self.token, "title": title, "content": message, "template": "txt"},
            lambda response: response.get("code") == 200,
        )


class WecomAdapter(_JsonWebhookAdapter):
    """WeCom group webhook adapter."""

    channel = "wecom"

    def __init__(self, webhook: str):
        self.webhook = webhook

    def push(self, message: str, title: str = _DEFAULT_TITLE) -> bool:
        return self._post(
            self.webhook,
            {"msgtype": "text", "text": {"content": message}},
            lambda response: response.get("errcode") == 0,
        )


class FeishuAdapter(_JsonWebhookAdapter):
    """Feishu group webhook adapter."""

    channel = "feishu"

    def __init__(self, webhook: str):
        self.webhook = webhook

    def push(self, message: str, title: str = _DEFAULT_TITLE) -> bool:
        return self._post(
            self.webhook,
            {"msg_type": "text", "content": {"text": message}},
            lambda response: response.get("code") == 0 or response.get("StatusCode") == 0,
        )


def build_adapters(theme_config: dict, env: Mapping[str, str] | None = None) -> List[PushAdapter]:
    """Build configured adapters, resolving blank credentials from the environment."""
    environment = os.environ if env is None else env
    adapters: List[PushAdapter] = []
    adapter_types = {
        "pushplus": ("token", "PUSHPLUS_TOKEN", PushplusAdapter),
        "wecom": ("webhook", "WECOM_WEBHOOK", WecomAdapter),
        "feishu": ("webhook", "FEISHU_WEBHOOK", FeishuAdapter),
    }
    for target in theme_config.get("push_targets") or []:
        channel = target.get("channel")
        if channel not in adapter_types:
            logger.warning("Skipping unsupported push channel: %r", channel)
            continue
        credential_key, environment_key, adapter_type = adapter_types[channel]
        credential = target.get(credential_key) or ""
        if credential in _PLACEHOLDERS:
            credential = environment.get(environment_key, "")
        if credential in _PLACEHOLDERS:
            logger.warning("Skipping %s push target without credentials", channel)
            continue
        adapters.append(adapter_type(credential))
    return adapters


def push_all(adapters: List[PushAdapter], message: str, title: str = _DEFAULT_TITLE) -> dict:
    """Push a briefing to every adapter without one failure stopping others."""
    results = {}
    for adapter in adapters:
        try:
            results[adapter.channel] = adapter.push(message, title)
        except Exception as error:
            logger.warning("%s push raised unexpectedly: %s", adapter.channel, error)
            results[adapter.channel] = False
    return results
