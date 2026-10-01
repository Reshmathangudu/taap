# from __future__ import annotations

# from datetime import datetime, timezone
# from typing import Any
# from uuid import uuid4




# A2A_PROTOCOL = "a2a-local-v1"


# def make_request(
#     *,
#     sender: str,
#     receiver: str,
#     message_type: str,
#     release_id: str,
#     data: dict[str, Any],
# ) -> dict[str, Any]:
#     """Create a serializable A2A request envelope.

#     A2A: The Master Orchestrator is the data owner and sends each specialist
#     only the structured data blocks and upstream outputs required by that stage.
#     Specialists do not fetch Jira/Excel themselves.
#     """
#     return {
#         "protocol": A2A_PROTOCOL,
#         "message_id": str(uuid4()),
#         "timestamp": datetime.now(timezone.utc).isoformat(),
#         "sender": sender,
#         "receiver": receiver,
#         "message_type": message_type,
#         "release_id": str(release_id or "").strip().upper(),
#         "data": data,
#     }


# def validate_message(
#     message: dict[str, Any],
#     *,
#     receiver: str,
#     message_types: set[str] | None = None,
# ) -> dict[str, Any]:
#     """Validate an A2A request before a specialist consumes it."""
#     if not isinstance(message, dict):
#         raise TypeError("A2A message must be a dictionary.")
#     if message.get("protocol") != A2A_PROTOCOL:
#         raise ValueError("Invalid A2A protocol envelope.")
#     if str(message.get("receiver") or "").strip() != receiver:
#         raise ValueError(
#             f"A2A receiver mismatch: expected {receiver!r}, "
#             f"got {message.get('receiver')!r}."
#         )
#     if message_types and message.get("message_type") not in message_types:
#         raise ValueError(
#             f"Unsupported A2A message type {message.get('message_type')!r}."
#         )
#     data = message.get("data")
#     if not isinstance(data, dict):
#         raise TypeError("A2A message data must be a dictionary.")
#     if not str(message.get("release_id") or "").strip():
#         raise ValueError("A2A message release_id is required.")
#     return data


# def make_response(
#     request: dict[str, Any],
#     *,
#     sender: str,
#     data: dict[str, Any],
#     status: str = "COMPLETED",
# ) -> dict[str, Any]:
#     """Create an A2A response envelope correlated to a request."""
#     return {
#         "protocol": A2A_PROTOCOL,
#         "message_id": str(uuid4()),
#         "correlation_id": request.get("message_id"),
#         "timestamp": datetime.now(timezone.utc).isoformat(),
#         "sender": sender,
#         "receiver": request.get("sender"),
#         "message_type": "A2A_RESPONSE",
#         "status": status,
#         "release_id": request.get("release_id"),
#         "data": data,
#     }


from __future__ import annotations

from uuid import uuid4

from app.models import A2ARequest, A2AResponse


A2A_PROTOCOL = "a2a-local-v1"


def make_request(
    *,
    sender: str,
    receiver: str,
    message_type: str,
    release_id: str,
    data: dict,
) -> A2ARequest:
    """Create a validated Pydantic A2A request envelope."""

    return A2ARequest(
        protocol=A2A_PROTOCOL,
        message_id=str(uuid4()),
        sender=sender,
        receiver=receiver,
        message_type=message_type,
        release_id=release_id,
        data=data,
    )


def validate_message(
    message: A2ARequest,
    *,
    receiver: str,
    message_types: set[str] | None = None,
) -> dict:
    """Validate an A2A request before an agent consumes it."""

    if not isinstance(message, A2ARequest):
        raise TypeError(
            "A2A message must be an A2ARequest Pydantic model."
        )

    if message.protocol != A2A_PROTOCOL:
        raise ValueError("Invalid A2A protocol envelope.")

    if message.receiver.strip() != receiver:
        raise ValueError(
            f"A2A receiver mismatch: expected {receiver!r}, "
            f"got {message.receiver!r}."
        )

    if message_types and message.message_type not in message_types:
        raise ValueError(
            f"Unsupported A2A message type "
            f"{message.message_type!r}."
        )

    if not message.data:
        raise ValueError("A2A message data cannot be empty.")

    return message.data


def make_response(
    request: A2ARequest,
    *,
    sender: str,
    data: dict,
    status: str = "COMPLETED",
) -> A2AResponse:
    """Create a validated Pydantic A2A response envelope."""

    return A2AResponse(
        protocol=A2A_PROTOCOL,
        message_id=str(uuid4()),
        correlation_id=request.message_id,
        sender=sender,
        receiver=request.sender,
        message_type="A2A_RESPONSE",
        status=status,
        release_id=request.release_id,
        data=data,
    )