from __future__ import annotations

import truststore
from google.adk.agents import Agent

#from app.agents.historical_agent.tools import analyze_historical_execution
from app.agents.historical_agent.tools import analyze_historical_execution
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

from app.orchestrator.tools import get_historical_intelligence

truststore.inject_into_ssl()


historical_agent = Agent(
    name="historical_execution_agent",
    model=get_adk_litellm_model(),
    instruction=load_prompt(
        "historical_agent.md"
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
    # analyze_historical_execution(source_data=..., release_id=...).
    #
    # Do not expose analyze_historical_execution as an ADK tool because
    # Spider/ADK should not invoke it without orchestrator-supplied data.
    tools=[get_pipeline_cache, analyze_historical_execution,get_historical_intelligence],
)