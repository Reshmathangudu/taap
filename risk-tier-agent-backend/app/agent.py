import truststore

truststore.inject_into_ssl()

from google.adk.agents import Agent

from app.agents.criticality_agent.agent import criticality_agent
from app.agents.feature_change_agent.agent import feature_change_agent
from app.agents.governance_agent.agent import governance_agent
from app.agents.historical_agent.agent import historical_agent
from app.agents.pipeline_stream_agent import RiskTierPipelineAgent
from app.agents.policy_agent.agent import policy_agent
from app.agents.scoring_agent.agent import scoring_agent
from app.observability.agent_logging import (
    log_after_agent_callback,
    log_after_model_callback,
    log_after_tool_callback,
    log_before_agent_callback,
    log_before_model_callback,
    log_before_tool_callback,
    log_on_tool_error_callback,
)
from app.orchestrator.master_orchestrator import stage_pipeline_run
from app.orchestrator.tools import RISK_TIER_ROOT_TOOLS
from app.prompts.loader import load_prompt
from app.services.llm_service import get_adk_litellm_model
from app.services.query_scope import scope_guard_before_agent_callback


# A BaseAgent instance can only ever have one parent (google-adk raises if a
# sub_agent already has one) — a fresh instance is required here rather than
# reusing app.agents.pipeline_stream_agent's module-level singleton, which
# stays parent-less for its own standalone use as /agui/run's top-level agent.
# RiskTierPipelineAgent holds no per-instance state beyond what BaseAgent
# provides, so two independent instances are safe.
_risk_tier_pipeline_subagent = RiskTierPipelineAgent(
    name="risk_tier_pipeline",
    description=(
        "Executes the complete deterministic Risk Tier pipeline (all six "
        "specialist agents) for one release and streams live per-agent "
        "progress. Transfer here only after stage_pipeline_run has staged "
        "the release id (and Jira link, if any) for this session — this "
        "agent reads them from session state, not from the transfer call."
    ),
    # RiskTierPipelineAgent is a plain BaseAgent (no LLM, no ADK tool calls
    # of its own — see app/agents/pipeline_stream_agent.py), so only the
    # agent-level callbacks apply here; its internal per-specialist-agent
    # progress is already logged separately via RiskTierMasterOrchestrator's
    # own _emit_stage calls.
    before_agent_callback=log_before_agent_callback,
    after_agent_callback=log_after_agent_callback,
)

root_agent = Agent(
    name="risk_tier_master_orchestrator",
    model=get_adk_litellm_model(),
    description=(
        "Coordinates the complete Risk Tier release analysis, answers "
        "release-specific questions, retrieves Jira/MCP-backed data, and "
        "delegates specialist analysis to the registered Risk Tier agents."
    ),
    instruction=load_prompt("master_orchestrator.md"),
    # Runs before every turn's LLM/tool loop starts. Logging first (so the
    # turn is on record even if scope_guard then short-circuits it), then
    # the OUT_OF_SCOPE check, which can end the whole invocation early (see
    # app/services/query_scope.py) — the query never reaches this agent's
    # own model call, its tools, or its sub-agents.
    before_agent_callback=[log_before_agent_callback, scope_guard_before_agent_callback],
    after_agent_callback=log_after_agent_callback,
    # Logs every tool call this agent makes, including ADK's own
    # auto-registered transfer_to_agent tool — i.e. every Master ->
    # sub-agent handoff (see app/observability/agent_logging.py).
    before_tool_callback=log_before_tool_callback,
    after_tool_callback=log_after_tool_callback,
    # ADK never calls after_tool_callback when a tool raises — this is the
    # only reachable place to observe a failed tool call.
    on_tool_error_callback=log_on_tool_error_callback,
    # Captures the real, fully-resolved system prompt/context sent to the
    # LLM and real provider-reported token usage for this agent's turn.
    before_model_callback=log_before_model_callback,
    after_model_callback=log_after_model_callback,
    tools=[
        stage_pipeline_run,
        *RISK_TIER_ROOT_TOOLS,
    ],
    sub_agents=[
        _risk_tier_pipeline_subagent,
        feature_change_agent,
        criticality_agent,
        historical_agent,
        policy_agent,
        scoring_agent,
        governance_agent,
    ],
)