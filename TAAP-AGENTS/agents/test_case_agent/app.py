import json
import uuid

from fastapi import FastAPI
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .agent import test_case_generation_agent
from .models import TestCaseGenerationInput, TestCaseGenerationResult


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

    return json.loads(final_response)


@app.post("/generate-test-cases", response_model=TestCaseGenerationResult)
async def generate_test_cases_endpoint(
    payload: TestCaseGenerationInput,
) -> dict:
    return await generate_test_cases(payload.model_dump())


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
