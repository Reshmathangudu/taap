from __future__ import annotations

from itertools import count
from typing import Any

from app.models import AgentMessage


class InMemoryMessageBus:
    """Records structured communication between the six agents."""

    def __init__(self) -> None:
        self._counter = count(1)
        self.messages: list[AgentMessage] = []

    def send(
        self,
        sender: str,
        receiver: str,
        message_type: str,
        payload: dict[str, Any],
    ) -> AgentMessage:
        message = AgentMessage(
            message_id=f"MSG-{next(self._counter):04d}",
            sender=sender,
            receiver=receiver,
            message_type=message_type,
            payload=payload,
        )
        self.messages.append(message)
        return message
