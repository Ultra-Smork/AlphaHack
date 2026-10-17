"""A deterministic Client for offline development and tests."""

from __future__ import annotations

from . import ROLE_USER, Message


class Mock:
    def complete(self, messages: list[Message]) -> str:
        last = ""
        for message in reversed(messages):
            if message.role == ROLE_USER:
                last = message.content
                break
        return "[mock assistant] received: " + last
