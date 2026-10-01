from __future__ import annotations

import truststore
from google.adk.agents import Agent

from app.agents.scoring_agent.tools import calculate_test_selection
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

from app.orchestrator.tools import get_scoring

truststore.inject_into_ssl()


scoring_agent = Agent(
    name="decision_engine_risk_scoring_agent",
    model=get_adk_litellm_model(),
    instruction=load_prompt(
        "scoring_agent.md"
    ),
    before_agent_callback=log_before_agent_callback,
    after_agent_callback=log_after_agent_callback,
    before_tool_callback=log_before_tool_callback,
    after_tool_callback=log_after_tool_callback,
    on_tool_error_callback=log_on_tool_error_callback,
    before_model_callback=log_before_model_callback,
    after_model_callback=log_after_model_callback,

    # Scoring is executed only by the Master Orchestrator.
    # The orchestrator supplies:
    # - worksheet source data
    # - Feature Agent output
    # - Criticality Agent output
    # - Historical Agent output
    # - Policy Agent output
    tools=[get_pipeline_cache, calculate_test_selection,get_scoring],
)