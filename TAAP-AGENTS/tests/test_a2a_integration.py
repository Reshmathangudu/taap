"""Integration tests for the A2A-layer supplemental_context preprocessing.

These exercise `SupplementalContextPreprocessingMiddleware` directly against
a capturing fake inner ASGI app, instead of the real `a2a_app` (which would
otherwise require a live LLM call). This is the actual path the frontend's
Node service-layer hits today (JSON-RPC `message/send` over A2A), so these
tests are what prove raw Base64 never reaches the agent in production, not
just in the `app.py` REST endpoint.
"""

import base64
import json

import pytest

from agents.test_case_agent import context_extraction as ctx
from agents.test_case_agent.a2a_server import SupplementalContextPreprocessingMiddleware


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _valid_input(**overrides) -> dict:
    payload = {
        "story_key": "PROJ-123",
        "summary": "OTP verification",
        "description": "User enters OTP to verify identity.",
        "acceptance_criteria": [{"id": "AC-1", "text": "User can verify with a valid OTP."}],
    }
    payload.update(overrides)
    return payload


def _envelope(context_dict: dict, method: str = "message/send", request_id="req-1") -> bytes:
    text = json.dumps(context_dict)
    envelope = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": {
            "message": {
                "messageId": "m-1",
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
            }
        },
    }
    return json.dumps(envelope).encode("utf-8")


class _CapturingApp:
    def __init__(self):
        self.received_body = None

    async def __call__(self, scope, receive, send):
        body = b""
        more_body = True
        while more_body:
            message = await receive()
            body += message.get("body", b"")
            more_body = message.get("more_body", False)
        self.received_body = body
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}", "more_body": False})

    def received_text(self) -> str:
        envelope = json.loads(self.received_body.decode("utf-8"))
        return envelope["params"]["message"]["parts"][0]["text"]

    def received_context(self) -> dict:
        return json.loads(self.received_text())


class _CollectingSend:
    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)

    @property
    def status(self):
        for message in self.messages:
            if message["type"] == "http.response.start":
                return message["status"]
        return None

    @property
    def body(self) -> bytes:
        return b"".join(
            message["body"] for message in self.messages if message["type"] == "http.response.body"
        )

    def json(self) -> dict:
        return json.loads(self.body.decode("utf-8"))


def _make_receive(body: bytes):
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


def _scope():
    return {"type": "http", "method": "POST", "path": "/", "headers": []}


async def _run(body: bytes):
    inner = _CapturingApp()
    middleware = SupplementalContextPreprocessingMiddleware(inner)
    send = _CollectingSend()
    await middleware(_scope(), _make_receive(body), send)
    return inner, send


@pytest.mark.asyncio
async def test_jira_only_message_passes_through_byte_identical():
    body = _envelope(_valid_input())
    inner, send = await _run(body)
    assert inner.received_body == body  # byte-identical: inner app saw the exact request
    assert send.status == 200  # response came from the (fake) inner app, not a middleware short-circuit


@pytest.mark.asyncio
async def test_html_supplemental_context_is_stripped_of_base64_before_reaching_agent():
    html = "<p>Max attempts: 3</p><script>evil()</script>"
    body = _envelope(
        _valid_input(
            supplemental_context={
                "source_type": "HTML",
                "content_base64": _b64(html.encode("utf-8")),
            }
        )
    )

    inner, _send = await _run(body)
    context = inner.received_context()

    assert context["supplemental_context"]["content_base64"] is None
    assert context["supplemental_context"]["raw_html"] is None
    assert "evil()" not in context["supplemental_context"]["extracted_text"]
    assert "Max attempts: 3" in context["supplemental_context"]["extracted_text"]


@pytest.mark.asyncio
async def test_audio_supplemental_context_is_transcribed_before_reaching_agent(monkeypatch):
    class _FakeTranscription:
        text = "The walkthrough describes retry-state persistence."

    async def _fake_atranscription(*, model, file):
        return _FakeTranscription()

    monkeypatch.setattr(ctx.litellm, "atranscription", _fake_atranscription)

    body = _envelope(
        _valid_input(
            supplemental_context={
                "source_type": "AUDIO",
                "file_name": "walkthrough.mp3",
                "content_base64": _b64(b"fake-audio-bytes"),
            }
        )
    )

    inner, _send = await _run(body)
    context = inner.received_context()

    assert context["supplemental_context"]["content_base64"] is None
    assert (
        context["supplemental_context"]["transcript"]
        == "The walkthrough describes retry-state persistence."
    )


@pytest.mark.asyncio
async def test_invalid_supplemental_context_short_circuits_with_jsonrpc_error():
    body = _envelope(
        _valid_input(
            supplemental_context={
                "source_type": "FILE",
                "file_name": "notes.txt",
                "content_base64": "not-valid-base64!!!",
            }
        )
    )

    inner, send = await _run(body)

    assert inner.received_body is None  # never forwarded to the agent
    assert send.status == 200
    payload = send.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == "req-1"
    assert payload["error"]["data"]["error_code"] == "INVALID_BASE64"


@pytest.mark.asyncio
async def test_task_control_methods_are_never_inspected():
    envelope = {
        "jsonrpc": "2.0",
        "id": "req-2",
        "method": "tasks/get",
        "params": {"id": "some-task-id"},
    }
    body = json.dumps(envelope).encode("utf-8")

    inner, send = await _run(body)

    assert inner.received_body == body
    assert send.status == 200


@pytest.mark.asyncio
async def test_generation_conditions_pass_through_unmodified():
    body = _envelope(
        _valid_input(
            generation_conditions={
                "positive_test_cases": False,
                "negative_test_cases": False,
                "boundary_conditions": False,
            }
        )
    )

    inner, _send = await _run(body)
    context = inner.received_context()

    assert context["generation_conditions"] == {
        "positive_test_cases": False,
        "negative_test_cases": False,
        "boundary_conditions": False,
    }
