"""A Client for any OpenAI-compatible /chat/completions endpoint."""

from __future__ import annotations

import httpx

from ...config import AI
from . import Message

_TIMEOUT_SECONDS = 60.0
_MAX_RESPONSE_BYTES = 1 << 20


class OpenAI:
    def __init__(self, cfg: AI) -> None:
        self._base_url = cfg.base_url
        self._api_key = cfg.api_key
        self._model = cfg.model
        self._client = httpx.Client(timeout=_TIMEOUT_SECONDS)

    def complete(self, messages: list[Message]) -> str:
        response = self._client.post(
            self._base_url + "/chat/completions",
            headers={"Authorization": "Bearer " + self._api_key},
            json={"model": self._model, "messages": [m.model_dump() for m in messages]},
        )

        body = response.content[:_MAX_RESPONSE_BYTES]
        if response.status_code != 200:
            raise RuntimeError(f"ai: provider status {response.status_code}: {body!r}")

        try:
            choices = response.json().get("choices") or []
        except ValueError as exc:
            raise RuntimeError(f"ai: decode response: {exc}") from exc
        if not choices:
            raise RuntimeError("ai: empty choices")
        return choices[0]["message"]["content"]
