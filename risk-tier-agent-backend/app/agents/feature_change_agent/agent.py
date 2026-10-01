from __future__ import annotations

import truststore
from google.adk.agents import Agent

from app.agents.feature_change_agent.tools import analyze_jira_release_scope, analyze_release_scope
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
from app.services.llm_service import get_adk_litellm_model
from app.orchestrator.tools import get_change_impact


truststore.inject_into_ssl()


feature_change_agent = Agent(
    name="feature_epic_change_impact_agent",
    model=get_adk_litellm_model(),
    instruction=load_prompt("feature_change_agent.md"),
    before_agent_callback=log_before_agent_callback,
    after_agent_callback=log_after_agent_callback,
    before_tool_callback=log_before_tool_callback,
    after_tool_callback=log_after_tool_callback,
    on_tool_error_callback=log_on_tool_error_callback,
    before_model_callback=log_before_model_callback,
    after_model_callback=log_after_model_callback,
    tools=[
        get_pipeline_cache,
        analyze_jira_release_scope,
        get_change_impact
    ],
)