from __future__ import annotations

import truststore
from google.adk.agents import Agent

from app.agents.policy_agent.tools import calibrate_risk_policy
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


from app.orchestrator.tools import get_policy

truststore.inject_into_ssl()


policy_agent = Agent(
    name="policy_risk_appetite_agent",
    model=get_adk_litellm_model(),
    instruction=load_prompt(
        "policy_agent.md"
    ),
    before_agent_callback=log_before_agent_callback,
    after_agent_callback=log_after_agent_callback,
    before_tool_callback=log_before_tool_callback,
    after_tool_callback=log_after_tool_callback,
    on_tool_error_callback=log_on_tool_error_callback,
    before_model_callback=log_before_model_callback,
    after_model_callback=log_after_model_callback,

    # Orchestrator-only agent:
    # the Master Orchestrator reads the required worksheets and calls
    # calibrate_risk_policy(source_data=..., release_type=...).
    #
    # Do not expose calibrate_risk_policy as an ADK tool because
    # Spider/ADK should not invoke it without orchestrator-supplied data.
    tools=[get_pipeline_cache, calibrate_risk_policy,get_policy],
)