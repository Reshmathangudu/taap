from __future__ import annotations

import asyncio

from app.config import get_settings
from app.integrations.mcp_jira_client import MCPJiraClient
from app.logging_config import get_logger
from app.persistence.jira_cache_repository import get_jira_cache_repository

logger = get_logger(__name__)


async def refresh_all_known_releases() -> None:
    """
    Refresh every (project_key, release_id) this app has ever cached.

    Runs the existing, unchanged Jira-fetch logic
    (RiskTierMasterOrchestrator._load_jira_source_data) off the event loop
    via run_in_executor — the same pattern
    app/agents/pipeline_stream_agent.py already uses to keep a blocking
    Jira call from freezing the FastAPI event loop.

    One release's failure never aborts the others: each iteration is its
    own try/except, and a failure marks the release FAILED (retaining its
    previous valid data) rather than raising out of the loop.
    """
    # Imported here, not at module load time, to avoid a circular import —
    # master_orchestrator.py imports this package's repository at import
    # time, so this module can only reach back into the orchestrator
    # lazily, inside the function body.
    from app.orchestrator.master_orchestrator import RiskTierMasterOrchestrator

    repo = get_jira_cache_repository()
    settings = get_settings()
    loop = asyncio.get_running_loop()

    known_releases = repo.list_known_releases()
    logger.info("jira_cache SCHEDULED_SYNC_BATCH_START releases=%d", len(known_releases))

    for project_key, release_id in known_releases:
        logger.info("jira_cache SCHEDULED_SYNC_START project=%s release=%s", project_key, release_id)
        try:
            orchestrator = RiskTierMasterOrchestrator(
                output_dir=settings.output_dir,
                jira_client=MCPJiraClient(),
                jira_project_key=project_key,
                jira_release_label=release_id,
            )
            source_data = await loop.run_in_executor(
                None, orchestrator._load_jira_source_data, release_id
            )
            repo.save_release(project_key, release_id, source_data)
            logger.info("jira_cache SCHEDULED_SYNC_SUCCESS project=%s release=%s", project_key, release_id)
        except Exception as exc:
            logger.exception(
                "jira_cache SCHEDULED_SYNC_FAILED project=%s release=%s — retaining previous data",
                project_key, release_id,
            )
            repo.mark_sync_failed(project_key, release_id, str(exc))

    logger.info("jira_cache SCHEDULED_SYNC_BATCH_END releases=%d", len(known_releases))


async def refresh_loop(interval_seconds: int) -> None:
    """
    Background task: sleeps interval_seconds, then refreshes every known
    release, forever. Started as an asyncio task from the FastAPI lifespan
    hook so it runs independently without blocking request handling.

    Wrapped in its own try/except (in addition to refresh_all_known_releases'
    per-release one) so a bug in listing releases, or anything else in the
    batch call itself, can't silently kill the background task for the rest
    of the process lifetime — it just logs and waits for the next interval.
    """
    logger.info("jira_cache scheduler loop started interval_s=%d", interval_seconds)
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await refresh_all_known_releases()
        except Exception:
            logger.exception("jira_cache refresh_loop iteration crashed — will retry next interval")
