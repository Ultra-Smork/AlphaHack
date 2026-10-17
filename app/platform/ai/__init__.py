"""The assistant boundary.

The service layer depends only on the Client protocol, never on a provider.
Swap implementations (OpenAI-compatible HTTP, local model, or mock) without
touching business logic.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from ...config import Config

# Role values for a chat message.
ROLE_SYSTEM = "system"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"


class Message(BaseModel):
    """One turn in a conversation."""

    role: str
    content: str


class Client(Protocol):
    """Complete a conversation. Implementations must be safe for concurrent use."""

    def complete(self, messages: list[Message]) -> str:
        """Return the assistant reply for the given conversation."""
        ...


def new(cfg: Config) -> Client:
    """Select an implementation from config. With mock set (or no API key), the
    deterministic offline client is used.
    """
    from .mock import Mock
    from .openai import OpenAI

    if cfg.ai.mock or cfg.ai.api_key == "":
        return Mock()
    return OpenAI(cfg.ai)
