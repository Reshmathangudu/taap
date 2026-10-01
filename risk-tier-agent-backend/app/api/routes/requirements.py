from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.requirements_agent.tools import (
    RequirementsConfigurationError,
    RequirementsUpstreamError,
    analyze_jira_requirements,
)

router = APIRouter(prefix="/requirements", tags=["requirements"])


class RequirementsRequest(BaseModel):
    issue_keys: list[str] | None = Field(default=None, min_length=1, max_length=100)
    walkthrough_notes: str = Field(default="", max_length=60000)


@router.post("/analyze")
def analyze_requirements(payload: RequirementsRequest):
    try:
        return analyze_jira_requirements(payload.issue_keys, payload.walkthrough_notes)
    except RequirementsConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except RequirementsUpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
