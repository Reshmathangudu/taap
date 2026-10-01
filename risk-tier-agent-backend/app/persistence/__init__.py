"""Durable SQLite cache sitting between Jira and the pipeline.

Only this package ever touches sqlite3 directly. The orchestrator and the
six specialist agents go through JiraCacheRepository, never the raw
database connection.
"""

from app.persistence.errors import ReleaseDataUnavailableError
from app.persistence.jira_cache_repository import (
    JiraCacheRepository,
    get_jira_cache_repository,
)

__all__ = [
    "JiraCacheRepository",
    "get_jira_cache_repository",
    "ReleaseDataUnavailableError",
]
