from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from the project-level .env file."""

    workbook_path: Path = Field(
        default=Path("data/Risk_Tier_Agent.xlsx"),
        validation_alias="RISK_TIER_WORKBOOK",
    )
    output_dir: Path = Field(
        default=Path("data/output"),
        validation_alias="RISK_TIER_OUTPUT_DIR",
    )
    default_release: str = Field(
        default="REL-25.4",
        validation_alias="RISK_TIER_DEFAULT_RELEASE",
    )

    # Per-agent/per-tool execution tracing (app/tracing/) — a detailed,
    # file-based trace tree under logs/<release_id>/<run_id>/, separate
    # from the coarser data/output/audit/ JSONL trail.
    logs_dir: Path = Field(
        default=Path("logs"),
        validation_alias="RISK_TIER_LOGS_DIR",
    )
    tracing_enabled: bool = Field(
        default=True,
        validation_alias="RISK_TIER_TRACING_ENABLED",
    )


    # Jira + large test repository configuration.
    jira_base_url: str | None = Field(default=None, validation_alias="JIRA_BASE_URL")
    jira_email: str | None = Field(default=None, validation_alias="JIRA_EMAIL")
    jira_api_token: str | None = Field(default=None, validation_alias="JIRA_API_TOKEN", repr=False)
    jira_project_key: str | None = Field(default=None, validation_alias="JIRA_PROJECT_KEY")
    jira_epic_issue_type: str = Field(default="Epic", validation_alias="JIRA_EPIC_ISSUE_TYPE")
    jira_story_issue_type: str = Field(default="Story", validation_alias="JIRA_STORY_ISSUE_TYPE")
    jira_field_epic_id: str = Field(default="", validation_alias="JIRA_FIELD_EPIC_ID")
    jira_field_story_id: str = Field(default="", validation_alias="JIRA_FIELD_STORY_ID")
    jira_field_module_id: str = Field(default="", validation_alias="JIRA_FIELD_MODULE_ID")
    jira_field_change_status: str = Field(default="", validation_alias="JIRA_FIELD_CHANGE_STATUS")
    jira_release_label: str = Field(default="", validation_alias="JIRA_RELEASE_LABEL")
    jira_mcp_page_size: int = Field(default=100, ge=1, le=100, validation_alias="JIRA_MCP_PAGE_SIZE")
    jira_mcp_max_pages: int = Field(default=1000, ge=1, validation_alias="JIRA_MCP_MAX_PAGES")
    jira_mcp_server_script: str = Field(default="app/mcp/jira_server.py", validation_alias="JIRA_MCP_SERVER_SCRIPT")
    jira_acceptance_criteria_field: str = Field(default="", validation_alias="JIRA_ACCEPTANCE_CRITERIA_FIELD")
    requirements_max_issues: int = Field(default=20, ge=1, le=100, validation_alias="REQUIREMENTS_MAX_ISSUES")
    requirements_max_input_chars: int = Field(default=60000, ge=1000, validation_alias="REQUIREMENTS_MAX_INPUT_CHARS")
    requirements_max_tokens: int = Field(default=8000, ge=1000, validation_alias="REQUIREMENTS_MAX_TOKENS")

    # Used only when a resolved release has no readable Release_Type (e.g.
    # it exists only as a label/Fix Version on other issues, not a
    # dedicated 'Release'-typed Jira issue with its own Release Type
    # field). Deliberately NOT a real release type like 'MAJOR'/'MINOR' —
    # that would be a guess this app has no basis for, and could silently
    # mis-include/exclude type-specific policy rows. Because
    # _row_applies_to_release_type treats a policy row as universal when
    # the row itself is typed 'ALL'/'ANY'/empty, using a sentinel here that
    # matches no real type simply means only those universal policies
    # apply — no type-specific policy is silently guessed into or out of
    # scope. Override only if this project deliberately wants unlabeled
    # releases treated as one specific real type.
    default_release_type: str = Field(
        default="UNSPECIFIED",
        validation_alias="RISK_TIER_DEFAULT_RELEASE_TYPE",
    )
    test_repository_db: Path = Field(default=Path("data/test_repository.db"), validation_alias="TEST_REPOSITORY_DB")
    use_jira_source: bool = Field(default=False, validation_alias="RISK_TIER_USE_JIRA_SOURCE")

    # How long the AG-UI streaming endpoint (/agui/run) lets one pipeline run
    # execute before ag-ui-adk cancels it as stale. The Jira/MCP load in
    # RiskTierMasterOrchestrator._load_jira_source_data is a full, paginated
    # project-wide issue fetch plus dynamic field discovery — on a large
    # project this can legitimately take well over ag-ui-adk's own 600s
    # (10 minute) default, so this is intentionally generous.
    agui_execution_timeout_seconds: int = Field(
        default=3600,
        validation_alias="AGUI_EXECUTION_TIMEOUT_SECONDS",
    )

    # How long a release's loaded Jira/MCP snapshot may be reused across
    # separate pipeline runs before it's considered stale and re-fetched.
    # Trade-off: within this window, a re-run of the same release will NOT
    # pick up intervening Jira changes. Set to 0 to disable caching entirely.
    jira_source_cache_ttl_seconds: int = Field(
        default=3600,
        validation_alias="JIRA_SOURCE_CACHE_TTL_SECONDS",
    )

    # Durable SQLite cache (app/persistence/) sitting underneath the
    # in-memory _JIRA_SOURCE_CACHE above — survives process restarts, unlike
    # the in-memory one. Deliberately a distinct field/file from the dead
    # test_repository_db above (that one belongs to an abandoned, unrelated
    # hybrid-source architecture and is never read by the live orchestrator).
    jira_cache_db_path: Path = Field(
        default=Path("data/jira_cache.db"),
        validation_alias="JIRA_CACHE_DB_PATH",
    )

    # How often the background scheduler (app/persistence/scheduler.py)
    # re-fetches every release it has ever cached, keeping the SQLite cache
    # warm without waiting for the next request to trigger a refetch.
    jira_cache_refresh_interval_seconds: int = Field(
        default=60,
        validation_alias="JIRA_CACHE_REFRESH_INTERVAL_SECONDS",
    )

    # Set to false to disable the background refresh scheduler entirely
    # (e.g. for a short-lived script or a test process) while still using
    # the SQLite cache itself for reads/writes.
    jira_cache_scheduler_enabled: bool = Field(
        default=True,
        validation_alias="JIRA_CACHE_SCHEDULER_ENABLED",
    )

    # LiteLLM/OpenAI configuration. The provider prefix is required by LiteLLM.
    llm_model: str = Field(
        default="openai/gpt-5-mini",
        validation_alias="LITELLM_MODEL",
    )
    openai_api_key: str | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
    )
    llm_temperature: float = Field(
        default=0.0,
        validation_alias="LITELLM_TEMPERATURE",
    )
    llm_max_tokens: int = Field(
        default=2000,
        validation_alias="LITELLM_MAX_TOKENS",
    )
    llm_timeout_seconds: int = Field(
        default=60,
        validation_alias="LITELLM_TIMEOUT_SECONDS",
    )
    llm_debug: bool = Field(
        default=False,
        validation_alias="LITELLM_DEBUG",
    )

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    def require_openai_key(self) -> str:
        """Return the OpenAI key or raise a clear configuration error."""
        if not self.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is missing. Add it to the project .env file before "
                "running 'adk web', 'adk run app', or scripts/test_llm.py."
            )
        return self.openai_api_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
