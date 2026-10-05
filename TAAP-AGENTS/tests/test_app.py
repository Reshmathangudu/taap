"""Tests for the `app.py` REST flow: validate -> preprocess -> invoke -> validate output.

The agent invocation itself (`generate_test_cases`, which drives the ADK
Runner/LLM) is mocked throughout — these tests cover the surrounding
request/response contract, not model behavior.
"""

import base64

import httpx
import pytest

from agents.test_case_agent import app as app_module


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _valid_payload(**overrides) -> dict:
    payload = {
        "story_key": "PROJ-123",
        "summary": "OTP verification",
        "description": "User enters OTP to verify identity.",
        "acceptance_criteria": [{"id": "AC-1", "text": "User can verify with a valid OTP."}],
    }
    payload.update(overrides)
    return payload


def _valid_result(**overrides) -> dict:
    result = {
        "story_key": "PROJ-123",
        "requirement_summary": "User verifies identity via OTP.",
        "coverage_analysis": [
            {
                "acceptance_criterion_id": "AC-1",
                "status": "NOT_COVERED",
                "existing_test_case_ids": [],
                "coverage_gap": "No existing test case.",
            }
        ],
        "generated_test_cases": [],
        "clarifications_required": [],
        "generation_summary": "1 AC NOT_COVERED, 0 generated.",
    }
    result.update(overrides)
    return result


async def _post(payload: dict) -> httpx.Response:
    transport = httpx.ASGITransport(app=app_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/generate-test-cases", json=payload)


@pytest.mark.asyncio
async def test_jira_only_request_is_backward_compatible(monkeypatch):
    captured = {}

    async def _fake_generate(jira_context):
        captured["context"] = jira_context
        return _valid_result()

    monkeypatch.setattr(app_module, "generate_test_cases", _fake_generate)

    response = await _post(_valid_payload())

    assert response.status_code == 200
    assert captured["context"]["supplemental_context"]["source_type"] == "NONE"
    assert captured["context"]["generation_conditions"] == {
        "positive_test_cases": True,
        "negative_test_cases": True,
        "boundary_conditions": True,
    }


@pytest.mark.asyncio
async def test_html_base64_is_not_forwarded_to_the_agent(monkeypatch):
    captured = {}

    async def _fake_generate(jira_context):
        captured["context"] = jira_context
        return _valid_result()

    monkeypatch.setattr(app_module, "generate_test_cases", _fake_generate)

    html = "<p>Password requires 8 characters minimum.</p>"
    response = await _post(
        _valid_payload(
            supplemental_context={
                "source_type": "HTML",
                "content_base64": _b64(html.encode("utf-8")),
            }
        )
    )

    assert response.status_code == 200
    supplemental = captured["context"]["supplemental_context"]
    assert supplemental["content_base64"] is None
    assert "Password requires 8 characters minimum." in supplemental["extracted_text"]


@pytest.mark.asyncio
async def test_invalid_base64_returns_400(monkeypatch):
    async def _fake_generate(_jira_context):
        raise AssertionError("agent should not be invoked for invalid input")

    monkeypatch.setattr(app_module, "generate_test_cases", _fake_generate)

    response = await _post(
        _valid_payload(
            supplemental_context={
                "source_type": "FILE",
                "file_name": "notes.txt",
                "content_base64": "not-valid-base64!!!",
            }
        )
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "INVALID_BASE64"


@pytest.mark.asyncio
async def test_unsupported_file_format_returns_400(monkeypatch):
    async def _fake_generate(_jira_context):
        raise AssertionError("agent should not be invoked for invalid input")

    monkeypatch.setattr(app_module, "generate_test_cases", _fake_generate)

    response = await _post(
        _valid_payload(
            supplemental_context={
                "source_type": "FILE",
                "file_name": "archive.zip",
                "content_base64": _b64(b"PK\x03\x04"),
            }
        )
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "UNSUPPORTED_FORMAT"


@pytest.mark.asyncio
async def test_missing_supplemental_content_returns_400(monkeypatch):
    async def _fake_generate(_jira_context):
        raise AssertionError("agent should not be invoked for invalid input")

    monkeypatch.setattr(app_module, "generate_test_cases", _fake_generate)

    response = await _post(
        _valid_payload(supplemental_context={"source_type": "AUDIO"})
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "MISSING_CONTENT"


@pytest.mark.asyncio
async def test_agent_execution_failure_returns_502(monkeypatch):
    async def _fake_generate(_jira_context):
        raise RuntimeError("Test Case Generation Agent returned no final response.")

    monkeypatch.setattr(app_module, "generate_test_cases", _fake_generate)

    response = await _post(_valid_payload())

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_malformed_agent_output_returns_502(monkeypatch):
    async def _fake_generate(_jira_context):
        return {"story_key": "PROJ-123"}  # missing required output fields

    monkeypatch.setattr(app_module, "generate_test_cases", _fake_generate)

    response = await _post(_valid_payload())

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_all_generation_conditions_false_still_invokes_agent(monkeypatch):
    captured = {}

    async def _fake_generate(jira_context):
        captured["context"] = jira_context
        return _valid_result(
            generated_test_cases=[],
            clarifications_required=[
                "No generation condition was selected; no new test cases were generated."
            ],
        )

    monkeypatch.setattr(app_module, "generate_test_cases", _fake_generate)

    response = await _post(
        _valid_payload(
            generation_conditions={
                "positive_test_cases": False,
                "negative_test_cases": False,
                "boundary_conditions": False,
            }
        )
    )

    assert response.status_code == 200
    assert "context" in captured  # the agent WAS invoked — not short-circuited in code
    body = response.json()
    assert body["generated_test_cases"] == []
    assert body["clarifications_required"]
