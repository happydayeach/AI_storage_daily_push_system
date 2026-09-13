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
_TOKEN_PLACEHOLDERS = {"", "your_token"}


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

    def __init__(self, token: str, send_channel: str = "wechat", option: str | None = None):
        self.token = token
        self.send_channel = send_channel
        self.option = option

    def push(self, message: str, title: str = _DEFAULT_TITLE) -> bool:
        return self._post(
            _PUSHPLUS_URL,
            {
                "token": self.token,
                "title": title,
                "content": message,
                "template": "txt",
                "channel": self.send_channel,
                **({"option": self.option} if self.option else {}),
            },
            lambda response: response.get("code") == 200,
        )


def build_adapters(theme_config: dict, env: Mapping[str, str] | None = None) -> List[PushAdapter]:
    """Build one Pushplus adapter for each configured downstream target."""
    environment = os.environ if env is None else env
    token = environment.get("PUSHPLUS_TOKEN", "")
    if token in _TOKEN_PLACEHOLDERS:
        logger.warning("Skipping push targets without PUSHPLUS_TOKEN")
        return []

    return [
        PushplusAdapter(
            token,
            send_channel=target.get("channel", "wechat"),
            option=target.get("option"),
        )
        for target in theme_config.get("push_targets") or []
    ]


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
