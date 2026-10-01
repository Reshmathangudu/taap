from __future__ import annotations

import asyncio
import html
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from app.persistence.jira_cache_repository import get_jira_cache_repository
from app.persistence.scheduler import refresh_loop
from app.persistence.errors import ReleaseDataUnavailableError
from pydantic import BaseModel, Field
from ag_ui_adk import ADKAgent, add_adk_fastapi_endpoint
from google.adk.apps import App
from app.tracing.adk_plugin import RiskTierTracingPlugin
from app.services.a2a import make_request
from app.config import get_settings
from app.api.routes.requirements import router as requirements_router
from app.models import PipelineState
from app.models.domain import AgentRun
from app.orchestrator.master_orchestrator import RiskTierMasterOrchestrator
from app.orchestrator.tools import (
    get_test_cases_by_classification,
)
from app.agents.pipeline_stream_agent import risk_tier_pipeline_agent
from app.agents.feature_change_agent.tools import (
    handle_a2a_request as feature_agent_request,
)

from app.agents.criticality_agent.tools import (
    handle_a2a_request as criticality_agent_request,
)

from app.agents.historical_agent.tools import (
    handle_a2a_request as historical_agent_request,
)
from app.agents.policy_agent.tools import (
    handle_a2a_request as policy_agent_request,
)

from app.agents.scoring_agent.tools import (
    handle_a2a_request as scoring_agent_request,
)

from app.agents.governance_agent.tools import (
    handle_a2a_request as governance_agent_request,
)
from app.utils.serialization import to_serializable

import time

from fastapi import Request

from app.observability.context import (
    create_trace_context,
    reset_trace_context,
    set_trace_context,
)

from app.observability.logger import log_event

from app.agents.feature_change_agent.tools import (
    handle_a2a_request as feature_agent_request,
)

from app.agents.criticality_agent.tools import (
    handle_a2a_request as criticality_agent_request,
)




class AnalyzeRequest(BaseModel):
    release_id: str = Field(min_length=1, examples=["REL-25.4"])
    jira_link: str = Field(
        min_length=1,
        examples=["https://your-company.atlassian.net/browse/REL-25.4"],
        description="Jira project, release, or issue URL used to resolve the data source.",
    )

class AgentQueryRequest(BaseModel):

    release_id: str = Field(

        min_length=1,

        examples=["REL-25.4"],

    )


    question: str = Field(

        min_length=1,

        examples=["Which epics were selected as changed?"],

    )


    model_id: str = Field(

        default="gpt-5-mini",

        examples=["gpt-5-mini", "gpt-5.5", "gpt-4.1"],

    )


    # system_prompt: str | None = Field(

    #     default=None,

    #     description=(

    #         "Optional custom system prompt. "

    #         "If not provided, the agent's default .md prompt will be used."

    #     ),

    # )
 


class SignoffRequest(BaseModel):
    role: str = Field(min_length=1, examples=["QA Lead"])
    note: str = Field(min_length=1, examples=["Approved after residual-risk review."])


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Constructing the repository runs ensure_schema() — this guarantees
    # the SQLite cache file/tables exist before the app starts serving
    # requests, without adding a separate init step to remember to call.
    get_jira_cache_repository()

    settings = get_settings()
    scheduler_task: asyncio.Task | None = None
    if settings.jira_cache_scheduler_enabled:
        scheduler_task = asyncio.create_task(
            refresh_loop(settings.jira_cache_refresh_interval_seconds)
        )
        logger.info(
            "Jira cache background scheduler started (interval=%ss)",
            settings.jira_cache_refresh_interval_seconds,
        )
    else:
        logger.info("Jira cache background scheduler disabled (JIRA_CACHE_SCHEDULER_ENABLED=false)")

    yield

    if scheduler_task is not None:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        logger.info("Jira cache background scheduler stopped")


app = FastAPI(
    title="Risk Tier Agent API",
    version="0.2.0",
    description=(
        "REST API for the Risk Tier six-agent pipeline and the React dashboard."
    ),
    lifespan=lifespan,
)

app.include_router(requirements_router)

required_fields = {
    "feature": [
        "changed_epics",
        "changed_stories",
        "changed_requirements",
        "direct_test_ids",
    ],
    "criticality": [
        "module_assignments",
        "summary",
    ],
    "historical": [
        "flaky_test_ids",
        "summary",
    ],
    "policy": [
        "mandatory_test_ids",
        "summary",
    ],
    "scoring": [
        "results",
        "summary",
    ],
    "governance": [
        "records",
        "summary",
    ],
}

# @app.post(
#     "/api/v1/agents/feature-impact"
# )
# def feature_agent(
#     payload: dict[str, Any],
# ) -> dict[str, Any]:

#     return feature_agent_request(
#         payload
#     )

# @app.post(
#     "/api/v1/agents/criticality"
# )
# def criticality_agent(
#     payload: dict[str, Any],
# ) -> dict[str, Any]:

#     return criticality_agent_request(
#         payload
#     )

# @app.post(
#     "/api/v1/agents/historical"
# )
# def historical_agent(
#     payload: dict[str, Any],
# ) -> dict[str, Any]:

#     return historical_agent_request(
#         payload
#     )

# @app.post(
#     "/api/v1/agents/policy"
# )
# def policy_agent(
#     payload: dict[str, Any],
# ) -> dict[str, Any]:

#     return policy_agent_request(
#         payload
#     )

# @app.post(
#     "/api/v1/agents/scoring"
# )
# def scoring_agent(
#     payload: dict[str, Any],
# ) -> dict[str, Any]:

#     return scoring_agent_request(
#         payload
#     )

# @app.post(
#     "/api/v1/agents/governance"
# )
# def governance_agent(
#     payload: dict[str, Any],
# ) -> dict[str, Any]:

#     return governance_agent_request(
#         payload
#     )


@app.post("/api/v1/agents/query/{agent_name}")
def query_agent(
    agent_name: str,
    payload: AgentQueryRequest,
) -> dict[str, Any]:

    registry = {
        "feature": (
            feature_agent_request,
            "Feature / Epic Change Impact Agent",
        ),
        "criticality": (
            criticality_agent_request,
            "Application Criticality Classification Agent",
        ),
        "historical": (
            historical_agent_request,
            "Historical Execution Intelligence Agent",
        ),
        "policy": (
            policy_agent_request,
            "Policy / Risk Appetite Calibration Agent",
        ),
        "scoring": (
            scoring_agent_request,
            "Decision Engine / Risk Scoring Agent",
        ),
        "governance": (
            governance_agent_request,
            "Exclusion Risk & Governance Agent",
        ),
    }

    agent_key = agent_name.lower()

    if agent_key not in registry:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown agent '{agent_name}'"
        )

    handler, receiver = registry[agent_key]

    release_id = payload.release_id.strip().upper()
    question = payload.question.strip()
    model_id = payload.model_id.strip()

    if not release_id:
        raise HTTPException(
            status_code=400,
            detail="release_id is required."
        )

    if not question:
        raise HTTPException(
            status_code=400,
            detail="question is required."
        )

    state = RiskTierMasterOrchestrator.get_cached_state(
        release_id
    )

    if state is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No completed pipeline exists for "
                f"{release_id}. Run Analyze first."
            ),
        )

    orchestrator = RiskTierMasterOrchestrator.for_query()

    return orchestrator.answer_agent_question(
        release_id=release_id,
        question=question,
        agent=agent_key,
        model_id=model_id,
    )


class AskQuestionRequest(BaseModel):
    release_id: str = Field(min_length=1, examples=["REL-25.4"])
    question: str = Field(
        min_length=1,
        examples=["Which Tier-1 tests were prevented from being downgraded during scoring?"],
    )


@app.post("/api/v1/agents/ask")
def ask_agent_question(payload: AskQuestionRequest) -> dict[str, Any]:
    """General-purpose drill-down Q&A — no agent to pick.

    Unlike /api/v1/agents/query/{agent_name} (which forces the caller to name
    one of the six specialists up front), this leaves `agent` unset so
    RiskTierMasterOrchestrator.answer_agent_question's own
    _detect_query_agents(...) routes the question to whichever specialist(s)
    it's actually about, exactly like the ADK conversational path already
    does. Reads only from a completed pipeline's cached state — same as
    every other query tool, this never re-runs the pipeline or calls an LLM.
    """
    release_id = payload.release_id.strip().upper()
    question = payload.question.strip()

    state = RiskTierMasterOrchestrator.get_cached_state(release_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"No completed pipeline exists for {release_id}. Run an analysis first.",
        )

    orchestrator = RiskTierMasterOrchestrator.for_query()
    return orchestrator.answer_agent_question(release_id=release_id, question=question)


class MasterQueryRequest(BaseModel):
    query: str = Field(min_length=1, examples=["analyze release R25.4", "which tests are flaky?"])


@app.post("/api/v1/master/query")
def master_query(payload: MasterQueryRequest) -> dict[str, Any]:
    """Single entry point for the unified chat input.

    The frontend forwards the user's raw text unchanged — no client-side
    classification. The Master Orchestrator alone decides what it needs:

    - A full pipeline run (RiskTierMasterOrchestrator.detect_pipeline_run_request
      recognizes a release token): responds with {"action": "run_pipeline",
      "release_id": ...} and does NOT execute or touch the data folder itself
      — the caller drives the actual run through the existing /agui/run
      stream, unchanged, which is what writes to the data folder on success.
    - Anything else: answered immediately from the last completed release's
      cached state via the existing, unchanged answer_agent_question — a
      pure read that never creates, updates, or overwrites anything in the
      data folder.
    """
    query_text = payload.query.strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="query is required")

    pipeline_release_id = RiskTierMasterOrchestrator.detect_pipeline_run_request(query_text)
    if pipeline_release_id:
        return {"action": "run_pipeline", "release_id": pipeline_release_id}

    release_id = _resolve_latest_release_id()
    if not release_id:
        return {
            "action": "answer",
            "markdown": (
                'No release has been analyzed yet — ask me to analyze one first, '
                'e.g. "analyze release R25.4".'
            ),
            "agents_consulted": [],
        }

    state = RiskTierMasterOrchestrator.get_cached_state(release_id)
    if state is None:
        return {
            "action": "answer",
            "markdown": f"No completed pipeline is available for {release_id}. Run an analysis first.",
            "agents_consulted": [],
        }

    orchestrator = RiskTierMasterOrchestrator.for_query()
    result = orchestrator.answer_agent_question(release_id=release_id, question=query_text)
    return {
        "action": "answer",
        "markdown": result["markdown"],
        "agents_consulted": result["agents_consulted"],
    }


@app.middleware("http")
async def trace_requests(
    request: Request,
    call_next,
):
    start = time.perf_counter()

    release_id = (
        request.path_params.get("release_id")
        or request.headers.get("X-Release-ID")
        or ""
    )

    trace = create_trace_context(
        release_id=release_id,
        # trace_id=request.headers.get("X-Trace-ID"),
        # request_id=request.headers.get("X-Request-ID"),
        # pipeline_id=request.headers.get("X-Pipeline-ID"),
    )

    token = set_trace_context(trace)

    log_event(
        "API_REQUEST_STARTED",
        stage="API",
        status="STARTED",
        method=request.method,
        path=request.url.path,
    )

    try:
        response = await call_next(request)

        duration = (
            time.perf_counter() - start
        ) * 1000

        log_event(
            "API_REQUEST_COMPLETED",
            stage="API",
            status="SUCCESS",
            duration_ms=duration,
            method=request.method,
            path=request.url.path,
            http_status=response.status_code,
        )

        response.headers["X-Trace-ID"] = trace.trace_id
        #response.headers["X-Request-ID"] = trace.request_id
        response.headers["X-Pipeline-ID"] = trace.pipeline_id

        return response

    except Exception as exc:
        duration = (
            time.perf_counter() - start
        ) * 1000

        log_event(
            "API_REQUEST_FAILED",
            level="ERROR",
            stage="API",
            status="FAILED",
            duration_ms=duration,
            method=request.method,
            path=request.url.path,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )

        raise

    finally:
        reset_trace_context(token)



# Local React/Vite development plus easy deployment from another browser origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# AG-UI streaming endpoint for real-time pipeline-run progress. Wraps the
# deterministic RiskTierPipelineAgent (no LLM call) rather than the
# conversational root_agent — see app/agents/pipeline_stream_agent.py.
#
# execution_timeout_seconds overrides ag-ui-adk's own 600s (10 minute)
# default: a full Jira/MCP load on a large project can legitimately run
# longer than that, and the default was cutting real runs off mid-stream.
#
# Constructed via ADKAgent.from_app(App(..., plugins=[...])) rather than
# the plain component-style ADKAgent(adk_agent=...) — the latter does not
# support ADK plugins at all (see ag_ui_adk's own docstring on from_app).
# RiskTierTracingPlugin is what makes a crashed or early-exited agent turn
# still close its trace/run cleanly (see app/tracing/adk_plugin.py) —
# unreachable from the per-agent before/after_agent_callback alone.
_agui_pipeline_agent = ADKAgent.from_app(
    App(
        name="risk_tier_agent",
        root_agent=risk_tier_pipeline_agent,
        plugins=[RiskTierTracingPlugin()],
    ),
    user_id="risk_tier_user",
    execution_timeout_seconds=get_settings().agui_execution_timeout_seconds,
)
add_adk_fastapi_endpoint(app, _agui_pipeline_agent, path="/agui/run")


# AG-UI conversational endpoint: the real LLM-driven root_agent (see
# app/agent.py + app/prompts/master_orchestrator.md). Unlike /agui/run, this
# one DOES call an LLM and DOES incur real OpenAI cost/latency per turn — the
# frontend's unified input box only routes here for things that don't look
# like a plain release-analysis trigger (which stays on the fast, free,
# live-streaming /agui/run path above). This is where genuine multi-turn
# behavior lives: the agent can ask a clarifying question ("for which
# release?") and, per its prompt, reuses the validated release/Jira context
# already established earlier in the same AG-UI thread rather than asking
# again every turn.
#
# Constructing root_agent requires OPENAI_API_KEY (get_adk_litellm_model()
# raises without it) — guarded so a missing key disables only this endpoint,
# not the deterministic pipeline-run/REST paths, which never needed an LLM.
try:
    from app.agent import root_agent as _conversational_root_agent
except Exception as exc:
    logger.warning(
        "Conversational /agui/chat endpoint disabled (root_agent could not be constructed): %s",
        exc,
    )
    _conversational_root_agent = None

if _conversational_root_agent is not None:
    _agui_chat_agent = ADKAgent.from_app(
        App(
            name="risk_tier_agent_chat",
            root_agent=_conversational_root_agent,
            plugins=[RiskTierTracingPlugin()],
        ),
        user_id="risk_tier_user",
        execution_timeout_seconds=get_settings().agui_execution_timeout_seconds,
    )
    add_adk_fastapi_endpoint(app, _agui_chat_agent, path="/agui/chat")


def _normalize_release_id(value: str) -> str:
    release_id = str(value or "").strip().upper()
    if not release_id:
        raise HTTPException(status_code=400, detail="release_id is required")
    return release_id


def _unwrap(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    candidate = value.get("agent_output")
    return candidate if isinstance(candidate, dict) else value


_TIER_DIGIT_RE = re.compile(r"([1-4])")


def _tier_number(value: Any) -> int:
    """
    Parse a tier value into the plain 1-4 int the frontend expects.

    The classification report stores tier as "TIER_1".."TIER_4" (see
    _normalize_tier in app/orchestrator/tools.py) — never a bare digit — so
    a naive str(value).isdigit() check always fails and silently maps every
    row to 0, which the frontend then displays as a default Tier 4.
    """
    match = _TIER_DIGIT_RE.search(str(value or ""))
    return int(match.group(1)) if match else 0


def _governance_records(state: PipelineState) -> list[dict[str, Any]]:
    """
    Return the full per-test governance rows for a release.

    The Governance agent's `agent_output` sub-dict only carries compact id
    lists (approved/pending/rejected test ids), not full rows. The full
    records (test_case_id, governance_decision, approval_status, residual
    risk, etc.) live at the top level of state.governance, one level above
    what _unwrap() prefers. Read that directly; fall back to the unwrapped
    shape only if a future agent_output ever does carry full rows.
    """
    governance = state.governance if isinstance(state.governance, dict) else {}
    records = governance.get("records")
    if isinstance(records, list) and records:
        return records
    fallback = _unwrap(state.governance).get("records")
    return fallback if isinstance(fallback, list) else []


def _load_state(release_id: str) -> PipelineState:
    normalized = _normalize_release_id(release_id)
    state = RiskTierMasterOrchestrator.get_cached_state(normalized)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No completed pipeline is available for {normalized}. "
                "Run POST /api/v1/releases/{release_id}/analyze first."
            ),
        )
    return state


def _release_type(state: PipelineState) -> str:
    release = state.release or {}
    return str(
        release.get("Release_Type")
        or release.get("release_type")
        or "UNKNOWN"
    ).upper()


def _build_dashboard(state: PipelineState) -> dict[str, Any]:
    change = _unwrap(state.change_impact)
    criticality = _unwrap(state.criticality)
    history = _unwrap(state.history)
    policy = _unwrap(state.policy)
    scoring = _unwrap(state.scoring)
    governance = _unwrap(state.governance)
    summary = state.summary()

    audit = []
    for run in state.audit_log:
        audit.append(
            {
                "agent": run.agent,
                "status": run.status,
                "summary": run.summary,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            }
        )

    return {
        "status": "success",
        "release_id": state.release_id,
        "release_type": _release_type(state),
        "analysis_status": "COMPLETE",
        "summary": summary,
        "change_impact": change.get("summary", {}),
        "criticality": criticality.get("summary", {}),
        "historical": history.get("summary", {}),
        "policy": policy.get("summary", {}),
        "scoring": scoring.get("summary", {}),
        "governance": governance.get("summary", {}),
        "report_files": state.report_files or {},
        "audit": audit,
    }


def _classification_rows(state: PipelineState) -> list[dict[str, Any]]:
    release_id = state.release_id
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for classification in (
        "MUST_TEST",
        "RECOMMENDED",
        "OPTIONAL",
        "EXCLUDE",
        "EXCLUDE_CANDIDATE",
    ):
        result = get_test_cases_by_classification(
            release_id=release_id,
            classification=classification,
        )
        if result.get("status") != "success":
            continue
        for row in result.get("test_cases", []):
            test_id = str(row.get("test_case_id") or "").strip()
            if not test_id or test_id in seen:
                continue
            seen.add(test_id)
            rows.append(row)

    gov_records = _governance_records(state)
    gov_by_id = {
        str(row.get("test_case_id") or "").strip(): row
        for row in gov_records
        if isinstance(row, dict) and row.get("test_case_id")
    }

    normalized: list[dict[str, Any]] = []
    for row in rows:
        test_id = str(row.get("test_case_id") or "").strip()
        classification = str(row.get("classification") or "UNKNOWN").upper()
        flags = row.get("protection_flags") or []
        if isinstance(flags, str):
            flags = [item.strip() for item in re.split(r"[;,|]", flags) if item.strip()]

        gov = gov_by_id.get(test_id, {})
        exclusion = None
        if gov:
            residual = str(
                gov.get("residual_risk")
                or gov.get("residual")
                or ""
            ).lower()
            signoff = gov.get("required_approval_role") or gov.get("approval_role") or ""
            status = str(gov.get("governance_status") or "pending").lower()
            if residual or signoff or status:
                exclusion = {
                    "likelihood": gov.get("likelihood") or "Not available",
                    "impact": gov.get("business_impact") or gov.get("impact") or "Not available",
                    "residual": residual or "low",
                    "signoff": signoff or "Not required",
                    "status": "signed" if status in {"approved", "signed", "approve_exclusion"} else (
                        "none" if status in {"none", "not_required"} else "pending"
                    ),
                }

        normalized.append(
            {
                "id": test_id,
                "name": row.get("test_name") or test_id,
                "module": row.get("module_id") or "Not available",
                "tier": _tier_number(row.get("tier")),
                "classification": {
                    "MUST_TEST": "must",
                    "RECOMMENDED": "rec",
                    "OPTIONAL": "opt",
                    "EXCLUDE": "exclude",
                    "EXCLUDE_CANDIDATE": "exclude",
                }.get(classification, "unknown"),
                "classification_raw": classification,
                "score": float(row.get("composite_score") or 0),
                "protection_flags": flags,
                "base_classification": row.get("base_classification") or classification,
                "risk_band": row.get("risk_band"),
                "change_impact_factor": row.get("change_impact_factor"),
                "criticality_factor": row.get("criticality_factor"),
                "historical_value_score": row.get("historical_value_score"),
                "historical_value_factor": row.get("historical_value_factor"),
                "release_risk_factor": row.get("release_risk_factor"),
                "reasons": row.get("reasons") or [],
                "exclusion": exclusion,
            }
        )

    return [_enrich_row_with_factors(row) for row in normalized]


def _enrich_row_with_factors(row: dict[str, Any]) -> dict[str, Any]:
    """Add the UI's per-factor breakdown, rationale, and flags to one row.

    Applied to every row from _classification_rows (not just single-test
    lookups) so the list endpoint carries everything TestDetail needs
    without a second network call per test case.
    """

    def factor(name: str, value: Any, label: str, color: str) -> list[Any]:
        numeric = 0 if value is None else float(value)
        return [name, label, max(0, min(100, numeric)), color]

    change_score = row.get("change_impact_factor")
    crit_score = row.get("criticality_factor")
    hist_score = row.get("historical_value_factor")
    risk_score = row.get("release_risk_factor")

    row["factors"] = [
        factor(
            "Change impact",
            change_score,
            "High" if float(change_score or 0) >= 70 else "Medium" if float(change_score or 0) >= 40 else "Low",
            "danger" if float(change_score or 0) >= 70 else "warn" if float(change_score or 0) >= 40 else "success",
        ),
        factor(
            "Criticality",
            crit_score,
            f"Tier {row['tier']}" if row["tier"] else "Not available",
            "danger" if row["tier"] == 1 else "warn" if row["tier"] == 2 else "success",
        ),
        factor(
            "Historical reliability",
            hist_score,
            "Protected / high value" if float(hist_score or 0) >= 70 else "Historical signal",
            "danger" if float(hist_score or 0) >= 70 else "warn" if float(hist_score or 0) >= 40 else "success",
        ),
        factor(
            "Risk appetite adjustment",
            risk_score,
            "Release posture",
            "danger" if float(risk_score or 0) >= 70 else "warn" if float(risk_score or 0) >= 40 else "success",
        ),
    ]

    reasons = row.get("reasons") or []
    safe_reason = "<br/>".join(html.escape(str(reason)) for reason in reasons) or (
        f"Final classification: {row['classification_raw']}"
    )
    row["rationale"] = safe_reason
    row["flags"] = row.get("protection_flags", [])
    return row


def _test_detail(state: PipelineState, test_id: str) -> dict[str, Any]:
    test_id = str(test_id or "").strip().upper()
    rows = _classification_rows(state)
    row = next((item for item in rows if item["id"].upper() == test_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Test case {test_id} not found")
    return row


def _hierarchy(state: PipelineState) -> list[dict[str, Any]]:
    change = _unwrap(state.change_impact)
    source = RiskTierMasterOrchestrator.get_cached_source_data(state.release_id)

    epic_rows = source.get("epics", [])
    story_rows = source.get("stories", [])
    requirement_rows = source.get("requirements", [])
    rtm_rows = source.get("rtm", [])
    test_rows = source.get("test_cases", [])

    changed_epic_ids = {
        str(value).strip()
        for value in change.get("changed_epic_ids", change.get("scoped_epic_ids", []))
        if str(value).strip()
    }

    def get_value(row: dict[str, Any], *keys: str) -> str:
        for key in keys:
            if key in row and row[key] not in (None, ""):
                return str(row[key]).strip()
        return ""

    tests_by_req: dict[str, list[str]] = {}
    for row in rtm_rows:
        req = get_value(row, "requirement_id", "Requirement_ID", "requirement", "Requirement")
        test = get_value(row, "test_case_id", "Test_Case_ID", "test_id", "Test_ID")
        if req and test:
            tests_by_req.setdefault(req, []).append(test)

    req_by_story: dict[str, list[dict[str, Any]]] = {}
    for row in requirement_rows:
        req_id = get_value(row, "id", "key", "Requirement_ID", "requirement_id")
        story_id = get_value(row, "story_id", "Story_ID", "parent_id", "parent")
        if req_id:
            req_by_story.setdefault(story_id, []).append(
                {"id": req_id, "name": get_value(row, "name", "summary", "Summary"), "tests": tests_by_req.get(req_id, [])}
            )

    stories_by_epic: dict[str, list[dict[str, Any]]] = {}
    for row in story_rows:
        story_id = get_value(row, "id", "key", "Story_ID", "story_id")
        epic_id = get_value(row, "epic_id", "Epic_ID", "parent_id", "parent")
        if story_id:
            stories_by_epic.setdefault(epic_id, []).append(
                {
                    "id": story_id,
                    "name": get_value(row, "name", "summary", "Summary"),
                    "requirements": req_by_story.get(story_id, []),
                }
            )

    result: list[dict[str, Any]] = []
    for row in epic_rows:
        epic_id = get_value(row, "id", "key", "Epic_ID", "epic_id")
        if not epic_id:
            continue
        if changed_epic_ids and epic_id not in changed_epic_ids:
            continue
        result.append(
            {
                "id": epic_id,
                "name": get_value(row, "name", "summary", "Summary"),
                "stories": stories_by_epic.get(epic_id, []),
            }
        )
    return result


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _resolve_latest_release_id() -> str | None:
    output_dir = Path(get_settings().output_dir)
    suffix = "_risk_tier_report.json"
    candidates = sorted(
        output_dir.glob(f"*{suffix}"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    return candidates[0].name[: -len(suffix)]


@app.get("/api/v1/releases/latest")
def get_latest_release() -> dict[str, Any]:
    """Return the most recently completed release, if any.

    Lets the frontend recover which release to show (e.g. a panel mounted
    fresh, or after localStorage was cleared) without the user having to
    re-run anything — it just reflects whatever the last completed pipeline
    run on this backend produced.
    """
    return {"release_id": _resolve_latest_release_id()}


@app.post("/api/v1/releases/{release_id}/analyze")
def analyze_release(release_id: str, request: AnalyzeRequest) -> dict[str, Any]:
    
    normalized_release_id = _normalize_release_id(release_id)
    print("=" * 60)
    print("FASTAPI ANALYZE ENDPOINT HIT")
    print("Release:", release_id)
    print("Jira:", request.jira_link)
    print("=" * 60)
    try:
        orchestrator = RiskTierMasterOrchestrator.from_settings(
            get_settings(),
            jira_link=request.jira_link.strip(),
        )
        state = orchestrator.execute(normalized_release_id)
        return _build_dashboard(state)
    except ReleaseDataUnavailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/analyze")
def analyze_legacy(request: AnalyzeRequest) -> dict[str, Any]:
    return analyze_release(request.release_id, request)


@app.get("/api/v1/releases/{release_id}/dashboard")
def get_dashboard(release_id: str) -> dict[str, Any]:
    return _build_dashboard(_load_state(release_id))


@app.get("/api/v1/releases/{release_id}/tests")
def get_tests(
    release_id: str,
    classification: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> dict[str, Any]:
    state = _load_state(release_id)
    rows = _classification_rows(state)
    if classification:
        normalized = classification.strip().upper()
        rows = [row for row in rows if row["classification_raw"] == normalized]
    if search:
        needle = search.strip().lower()
        rows = [
            row
            for row in rows
            if needle in row["id"].lower() or needle in row["name"].lower()
        ]
    return {
        "release_id": state.release_id,
        "count": len(rows),
        "tests": rows,
    }


@app.get("/api/v1/releases/{release_id}/tests/{test_id}")
def get_test_detail(release_id: str, test_id: str) -> dict[str, Any]:
    state = _load_state(release_id)
    return {
        "release_id": state.release_id,
        "test": _test_detail(state, test_id),
    }


@app.get("/api/v1/releases/{release_id}/hierarchy")
def get_release_hierarchy(release_id: str) -> dict[str, Any]:
    state = _load_state(release_id)
    hierarchy = _hierarchy(state)
    return {
        "release_id": state.release_id,
        "epics": hierarchy,
    }


@app.get("/api/v1/releases/{release_id}/governance")
def get_governance(release_id: str) -> dict[str, Any]:
    state = _load_state(release_id)
    governance = _unwrap(state.governance)
    summary = governance.get("summary", {})
    records = _governance_records(state)
    return {
        "release_id": state.release_id,
        "summary": summary,
        "records": records,
    }


@app.post("/api/v1/releases/{release_id}/governance/{test_id}/signoff")
def signoff(
    release_id: str,
    test_id: str,
    request: SignoffRequest,
) -> dict[str, Any]:
    state = _load_state(release_id)
    records = _governance_records(state)
    target_id = str(test_id).strip().upper()
    found = False

    for row in records:
        if str(row.get("test_case_id") or "").strip().upper() == target_id:
            row["governance_status"] = "SIGNED"
            row["approval_role"] = request.role.strip()
            row["approval_note"] = request.note.strip()
            row["approved_by"] = request.role.strip()
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail=f"Governance record for {target_id} not found")

    # Keep the in-process cache authoritative for the UI after sign-off.
    _ = state
    return {
        "status": "success",
        "release_id": state.release_id,
        "test_case_id": target_id,
        "approval_role": request.role.strip(),
        "approval_note": request.note.strip(),
    }


@app.get("/api/v1/releases/{release_id}/risk-appetite")
def get_risk_appetite(release_id: str) -> dict[str, Any]:
    state = _load_state(release_id)
    policy = _unwrap(state.policy)
    release_type = _release_type(state)
    tier_policies = policy.get("tier_policies", {})
    regulatory_ids = policy.get("regulatory_test_ids") or policy.get("regulatory_tests") or []
    return {
        "release_id": state.release_id,
        "release_type": release_type,
        "approval_role": policy.get("approval_role") or policy.get("approval_required_role") or "QA_LEAD",
        "overall_max_exclusion": policy.get("overall_max_exclusion", 0),
        "minimum_must_test_rate": policy.get("minimum_must_test_rate", 0),
        "require_approval_for_exclusion": bool(policy.get("require_approval_for_exclusion", False)),
        "tier_policies": tier_policies,
        "regulatory_test_ids": sorted(list(regulatory_ids)) if isinstance(regulatory_ids, (list, set, tuple)) else [],
        "regulatory_count": len(regulatory_ids) if isinstance(regulatory_ids, (list, set, tuple, dict)) else 0,
    }


def _format_audit_text(run: AgentRun) -> str:
    """
    Render one AgentRun's summary dict as a human-readable line.

    _run_stage's summary shapes: {"records": N} on success for the six
    specialist stages, state.report_files (e.g. {"json": path, "csv":
    path}) on success for the Report Generator stage, and
    {"error_type": ..., "error": ...} on any failure. Passing the raw dict
    straight to the frontend (as this endpoint used to) renders as the
    literal string "[object Object]" once JS does String(dict) on it.
    """
    summary = run.summary if isinstance(run.summary, dict) else {}

    if run.status == "FAILED":
        error_type = summary.get("error_type", "Error")
        error = summary.get("error", "")
        return f"{error_type}: {error}" if error else str(error_type)

    if "records" in summary:
        records = summary["records"]
        noun = "record" if records == 1 else "records"
        return f"Completed — {records} {noun} produced."

    report_paths = {k: v for k, v in summary.items() if k in ("json", "csv", "excel") and v}
    if report_paths:
        parts = [f"{key.upper()}: {Path(value).name}" for key, value in report_paths.items()]
        return "Reports generated — " + ", ".join(parts)

    if not summary:
        return "Completed."

    return "Completed — " + ", ".join(f"{k}: {v}" for k, v in summary.items())


@app.get("/api/v1/releases/{release_id}/audit")
def get_audit(release_id: str) -> dict[str, Any]:
    state = _load_state(release_id)
    return {
        "release_id": state.release_id,
        "entries": [
            {
                # Seconds matter here: several stages routinely complete
                # within the same displayed minute, and "%H:%M" alone made
                # every row in a fast run look like it fired at the exact
                # same time even though each has its own started_at.
                "time": run.started_at.strftime("%H:%M:%S") if run.started_at else "--:--:--",
                "agent": run.agent,
                "status": run.status,
                "text": _format_audit_text(run),
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            }
            for run in state.audit_log
        ],
        "feedback": [],
    }


@app.get("/api/v1/releases/{release_id}/reports")
def get_reports(release_id: str) -> dict[str, Any]:
    state = _load_state(release_id)
    return {
        "release_id": state.release_id,
        "report_files": state.report_files or {},
    }


# Keep this import path compatible with the project's existing callers.
def serialized_state(state: PipelineState) -> dict[str, Any]:
    return to_serializable(state)
