from __future__ import annotations

import truststore
from google.adk.agents import Agent

from app.agents.criticality_agent.tools import classify_application_criticality
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



from app.orchestrator.tools import get_application_criticality

truststore.inject_into_ssl()


criticality_agent = Agent(
    name="application_criticality_agent",
    model=get_adk_litellm_model(),
    instruction=load_prompt(
        "criticality_agent.md"
    ),
    before_agent_callback=log_before_agent_callback,
    after_agent_callback=log_after_agent_callback,
    before_tool_callback=log_before_tool_callback,
    after_tool_callback=log_after_tool_callback,
    on_tool_error_callback=log_on_tool_error_callback,
    before_model_callback=log_before_model_callback,
    after_model_callback=log_after_model_callback,

    # This agent is orchestrator-only.
    #
    # The Master Orchestrator reads the required worksheets and calls
    # classify_application_criticality(source_data=...).
    #
    # Do not register classify_application_criticality as an ADK tool,
    # because ADK/Spider would otherwise be able to call it directly
    # without the orchestrator-supplied worksheet data.
    tools=[get_pipeline_cache, classify_application_criticality,get_application_criticality],
)