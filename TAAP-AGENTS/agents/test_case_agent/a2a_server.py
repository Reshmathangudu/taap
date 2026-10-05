import json
import logging
import os

from google.adk.a2a.utils.agent_to_a2a import to_a2a
from pydantic import ValidationError

from .agent import root_agent
from .context_extraction import SupplementalContextError, process_supplemental_context
from .models import TestCaseGenerationInput

logger = logging.getLogger(__name__)

A2A_HOST = os.getenv("A2A_HOST", "localhost")
A2A_PORT = int(os.getenv("A2A_PORT", "8001"))

# JSON-RPC methods that carry a new user Message (as opposed to task-control
# methods like tasks/get, tasks/cancel, which reference an existing task and
# never need supplemental_context preprocessing).
SUPPLEMENTAL_CONTEXT_METHODS = {"message/send", "message/stream"}

LEGACY_JSONRPC_METHODS = {
    "message/send",
    "message/stream",
    "tasks/get",
    "tasks/cancel",
    "tasks/pushNotificationConfig/set",
    "tasks/pushNotificationConfig/get",
    "tasks/pushNotificationConfig/list",
    "tasks/pushNotificationConfig/delete",
    "tasks/resubscribe",
    "agent/getAuthenticatedExtendedCard",
}
A2A_VERSION_HEADER = b"a2a-version"


def _replay_body(body):
    """Build a `receive()` callable that replays an already-consumed ASGI body."""

    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}

        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


def _replay_once(message):
    """Build a `receive()` callable that replays a single already-consumed message."""

    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}

        sent = True
        return message

    return receive


async def _read_body(scope, receive, send, app):
    """Drain the inbound ASGI body, returning it as bytes, or `None` after
    forwarding a non-`http.request` message untouched (e.g. an early
    disconnect) — callers must return immediately when `None` comes back.
    """

    body = b""
    more_body = True
    while more_body:
        message = await receive()
        if message.get("type") != "http.request":
            await app(scope, _replay_once(message), send)
            return None
        body += message.get("body", b"")
        more_body = message.get("more_body", False)

    return body


class A2AVersionCompatibilityMiddleware:
    """Normalizes stale v0.3 JSON-RPC requests that carry a v1 header."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        headers = list(scope.get("headers") or [])

        if not self._should_inspect(scope, headers):
            await self.app(scope, receive, send)
            return

        body = await _read_body(scope, receive, send, self.app)
        if body is None:
            return

        if self._is_legacy_jsonrpc_request(body):
            scope = dict(scope)
            scope["headers"] = self._replace_a2a_version(headers, b"0.3")

        await self.app(scope, _replay_body(body), send)

    @staticmethod
    def _should_inspect(scope, headers):
        if scope.get("type") != "http":
            return False
        if scope.get("method") != "POST":
            return False
        if scope.get("path") != "/":
            return False

        for name, value in headers:
            if name.lower() == A2A_VERSION_HEADER:
                version = value.decode("latin-1")
                return version.startswith("1.")

        return False

    @staticmethod
    def _is_legacy_jsonrpc_request(body):
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False

        return (
            isinstance(payload, dict)
            and payload.get("jsonrpc") == "2.0"
            and payload.get("method") in LEGACY_JSONRPC_METHODS
        )

    @staticmethod
    def _replace_a2a_version(headers, version):
        updated = [
            (name, value)
            for name, value in headers
            if name.lower() != A2A_VERSION_HEADER
        ]
        updated.append((A2A_VERSION_HEADER, version))
        return updated


class SupplementalContextPreprocessingMiddleware:
    """Decodes/extracts `supplemental_context` in an inbound A2A message
    before it reaches the LLM.

    The Test Case Generation Agent has no tools and cannot decode Base64 or
    parse HTML/documents/audio itself, so this must happen in front of it.
    A `message/send` or `message/stream` JSON-RPC request's
    `params.message.parts[0].text` is the JSON-encoded `TestCaseGenerationInput`
    payload (see test-case-generation.js on the frontend side); this
    middleware parses that text, runs `process_supplemental_context` on its
    `supplemental_context`, and rewrites the text with the normalized result
    (Base64/raw HTML cleared, `extracted_text`/`transcript` populated) before
    forwarding the request. Every other request shape (task-control methods,
    agent-card negotiation, a message with no supplemental_context) passes
    through byte-for-byte unchanged.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if not self._should_inspect(scope):
            await self.app(scope, receive, send)
            return

        body = await _read_body(scope, receive, send, self.app)
        if body is None:
            return

        try:
            body = await self._maybe_rewrite_body(body)
        except SupplementalContextError as exc:
            logger.warning(
                "Rejecting A2A request with invalid supplemental_context: %s (%s)",
                exc.message,
                exc.code,
            )
            await self._send_jsonrpc_error(send, body, exc)
            return

        await self.app(scope, _replay_body(body), send)

    @staticmethod
    def _should_inspect(scope):
        return (
            scope.get("type") == "http"
            and scope.get("method") == "POST"
            and scope.get("path") == "/"
        )

    @staticmethod
    async def _maybe_rewrite_body(body: bytes) -> bytes:
        try:
            envelope = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return body

        if not isinstance(envelope, dict) or envelope.get("method") not in SUPPLEMENTAL_CONTEXT_METHODS:
            return body

        try:
            parts = envelope["params"]["message"]["parts"]
            raw_text = parts[0]["text"]
        except (KeyError, IndexError, TypeError):
            return body

        try:
            context_dict = json.loads(raw_text)
        except json.JSONDecodeError:
            return body

        if not isinstance(context_dict, dict):
            return body

        supplemental = context_dict.get("supplemental_context") or {}
        if supplemental.get("source_type", "NONE") == "NONE":
            return body

        try:
            parsed_input = TestCaseGenerationInput.model_validate(context_dict)
        except ValidationError:
            # Malformed input: let the agent's own input_schema validation
            # report it downstream rather than duplicating that error shape.
            return body

        normalized_context = await process_supplemental_context(
            parsed_input.supplemental_context
        )
        normalized_input = parsed_input.model_copy(
            update={"supplemental_context": normalized_context}
        )

        parts[0]["text"] = json.dumps(
            normalized_input.model_dump(mode="json"), ensure_ascii=False
        )
        return json.dumps(envelope).encode("utf-8")

    @staticmethod
    async def _send_jsonrpc_error(send, body: bytes, exc: SupplementalContextError) -> None:
        request_id = None
        try:
            request_id = json.loads(body.decode("utf-8")).get("id")
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            pass

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32602,
                "message": "Invalid supplemental_context",
                "data": {"error_code": exc.code, "detail": exc.message},
            },
        }
        response_body = json.dumps(payload).encode("utf-8")

        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": response_body, "more_body": False})


a2a_app = to_a2a(
    root_agent,
    host=A2A_HOST,
    port=A2A_PORT,
)
a2a_app.add_middleware(A2AVersionCompatibilityMiddleware)
a2a_app.add_middleware(SupplementalContextPreprocessingMiddleware)
