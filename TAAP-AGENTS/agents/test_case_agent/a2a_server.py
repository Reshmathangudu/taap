import json
import os

from google.adk.a2a.utils.agent_to_a2a import to_a2a

from .agent import root_agent


A2A_HOST = os.getenv("A2A_HOST", "localhost")
A2A_PORT = int(os.getenv("A2A_PORT", "8001"))

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


class A2AVersionCompatibilityMiddleware:
    """Normalizes stale v0.3 JSON-RPC requests that carry a v1 header."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        headers = list(scope.get("headers") or [])

        if not self._should_inspect(scope, headers):
            await self.app(scope, receive, send)
            return

        body = b""
        more_body = True
        while more_body:
            message = await receive()
            if message.get("type") != "http.request":
                await self.app(scope, self._replay_once(message), send)
                return

            body += message.get("body", b"")
            more_body = message.get("more_body", False)

        if self._is_legacy_jsonrpc_request(body):
            scope = dict(scope)
            scope["headers"] = self._replace_a2a_version(headers, b"0.3")

        await self.app(scope, self._replay_body(body), send)

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

    @staticmethod
    def _replay_body(body):
        sent = False

        async def receive():
            nonlocal sent
            if sent:
                return {"type": "http.request", "body": b"", "more_body": False}

            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        return receive

    @staticmethod
    def _replay_once(message):
        sent = False

        async def receive():
            nonlocal sent
            if sent:
                return {"type": "http.request", "body": b"", "more_body": False}

            sent = True
            return message

        return receive


a2a_app = to_a2a(
    root_agent,
    host=A2A_HOST,
    port=A2A_PORT,
)
a2a_app.add_middleware(A2AVersionCompatibilityMiddleware)
