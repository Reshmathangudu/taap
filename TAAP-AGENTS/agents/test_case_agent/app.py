import json
import logging
import uuid

from fastapi import FastAPI, HTTPException
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import ValidationError

from .agent import test_case_generation_agent
from .context_extraction import SupplementalContextError, process_supplemental_context
from .models import TestCaseGenerationInput, TestCaseGenerationResult

logger = logging.getLogger(__name__)

APP_NAME = "test_case_generation"
USER_ID = "risk-tier-system"


session_service = InMemorySessionService()

runner = Runner(
    agent=test_case_generation_agent,
    app_name=APP_NAME,
    session_service=session_service,
)

app = FastAPI(title="Test Case Generation Agent")


async def generate_test_cases(jira_context: dict) -> dict:

    session_id = f"test-generation-{uuid.uuid4()}"

    await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=session_id,
    )

    message = types.Content(
        role="user",
        parts=[
            types.Part(
                text=json.dumps(
                    jira_context,
                    ensure_ascii=False,
                )
            )
        ],
    )

    final_response = None

    events = runner.run_async(
        user_id=USER_ID,
        session_id=session_id,
        new_message=message,
    )

    async for event in events:

        if event.is_final_response():

            if (
                event.content
                and event.content.parts
                and event.content.parts[0].text
            ):
                final_response = event.content.parts[0].text

    if not final_response:
        raise RuntimeError(
            "Test Case Generation Agent returned no final response."
        )

    try:
        return json.loads(final_response)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Test Case Generation Agent returned malformed JSON: {exc}"
        ) from exc


@app.post("/generate-test-cases", response_model=TestCaseGenerationResult)
async def generate_test_cases_endpoint(
    payload: TestCaseGenerationInput,
) -> dict:
    """Validate -> preprocess supplemental source -> invoke agent -> validate output.

    Raw Base64/raw HTML never reaches the LLM: `process_supplemental_context`
    resolves `payload.supplemental_context` into plain `extracted_text` /
    `transcript` (or raises on invalid/unsupported/oversized input) before the
    normalized payload is sent to the agent.
    """

    try:
        normalized_context = await process_supplemental_context(
            payload.supplemental_context
        )
    except SupplementalContextError as exc:
        logger.warning(
            "Rejecting supplemental_context: %s (%s)", exc.message, exc.code
        )
        raise HTTPException(
            status_code=400,
            detail={"error_code": exc.code, "message": exc.message},
        ) from exc

    normalized_payload = payload.model_copy(
        update={"supplemental_context": normalized_context}
    )

    try:
        result = await generate_test_cases(normalized_payload.model_dump(mode="json"))
    except RuntimeError as exc:
        logger.error("Test Case Generation Agent execution failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        return TestCaseGenerationResult.model_validate(result).model_dump(mode="json")
    except ValidationError as exc:
        logger.error("Test Case Generation Agent returned malformed output: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"Agent returned malformed output: {exc}",
        ) from exc


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
