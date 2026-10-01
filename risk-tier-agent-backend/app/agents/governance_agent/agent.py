from __future__ import annotations

import truststore
from google.adk.agents import Agent

from app.agents.governance_agent.tools import evaluate_exclusion_governance
from app.observability.agent_logging import (
    log_after_agent_callback,
    log_after_model_callback,
    log_after_tool_callback,
    log_before_agent_callback,
    log_before_model_callback,
    log_before_tool_callback,
    log_on_tool_error_callback,
)
from app.orchestrator.tools import get_pipeline_cache
from app.prompts.loader import load_prompt
from app.services.llm_service import (
    get_adk_litellm_model,
)

from app.orchestrator.tools import get_governance


truststore.inject_into_ssl()


governance_agent = Agent(
    name="exclusion_risk_governance_agent",
    model=get_adk_litellm_model(),
    instruction=load_prompt(
        "governance_agent.md"
    ),
    before_agent_callback=log_before_agent_callback,
    after_agent_callback=log_after_agent_callback,
    before_tool_callback=log_before_tool_callback,
    after_tool_callback=log_after_tool_callback,
    on_tool_error_callback=log_on_tool_error_callback,
    before_model_callback=log_before_model_callback,
    after_model_callback=log_after_model_callback,

    # Orchestrator-only agent:
    # the Master Orchestrator directly calls
    # evaluate_exclusion_governance(scoring=..., policy=...).
    #
    # Do not expose evaluate_exclusion_governance as an ADK tool because
    # Spider/ADK should not invoke Governance without the validated outputs
    # of the Scoring and Policy stages.
    tools=[get_pipeline_cache, evaluate_exclusion_governance, get_governance],
)