from __future__ import annotations


class ReleaseDataUnavailableError(RuntimeError):
    """
    Raised by _prepare_jira_source_data when a release is absent from both
    the in-memory cache and the durable SQLite cache.

    Query-time code must never respond to this by fetching Jira directly —
    Jira is reachable only from the background scheduler
    (app/persistence/scheduler.py). str(this exception) is the exact,
    user-facing message every entry point (REST, AG-UI stream, ADK tools)
    surfaces unchanged.
    """

    def __init__(self, release_id: str) -> None:
        self.release_id = release_id
        super().__init__(
            f"No records were found for release '{release_id}'. Please provide "
            "a valid release ID or wait for the scheduled synchronization to "
            "populate the database."
        )
