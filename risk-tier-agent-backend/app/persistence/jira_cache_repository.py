from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)

# The 16 block names _load_jira_source_data actually returns (see its
# return statement in app/orchestrator/master_orchestrator.py). Duplicated
# here rather than imported to avoid a circular import — this package is a
# leaf dependency of the orchestrator, never the other way around. A full
# release is only ever considered cached if every one of these is present;
# a partial set is treated as a miss so no agent silently gets an empty
# block it should have had data for.
EXPECTED_BLOCK_NAMES: tuple[str, ...] = (
    "releases", "modules", "epics", "stories", "requirements", "rtm",
    "test_cases", "release_scope", "dependencies", "out_of_scope",
    "executions", "defects", "flaky_tests", "policies",
    "regulatory_tests", "release_rules",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jira_release_blocks (
    project_key TEXT NOT NULL,
    release_id TEXT NOT NULL,
    block_name TEXT NOT NULL,
    data_json TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (project_key, release_id, block_name)
);

CREATE TABLE IF NOT EXISTS jira_release_sync_meta (
    project_key TEXT NOT NULL,
    release_id TEXT NOT NULL,
    last_synced_at TEXT NOT NULL,
    last_sync_status TEXT NOT NULL,
    last_error TEXT,
    PRIMARY KEY (project_key, release_id)
);
"""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JiraCacheRepository:
    """
    Durable SQLite cache of Jira source blocks, keyed by (project_key,
    release_id, block_name). This is the ONLY class in the app that opens
    a sqlite3 connection — the orchestrator and agents call this class,
    never sqlite3 directly.

    Each block is stored as a JSON blob rather than a relational table:
    _load_jira_source_data's 16 blocks are heterogeneous normalized-Jira-
    issue dicts with no fixed column set, so a
    (project_key, release_id, block_name) -> data_json row store maps 1:1
    onto the existing dict[str, list[dict]] shape with zero reinterpretation
    of row contents — exactly the boundary needed to add durability without
    touching any business logic.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.row_factory = sqlite3.Row
        return connection

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_full_release(
        self,
        project_key: str,
        release_id: str,
        ttl_seconds: int,
    ) -> dict[str, list[dict[str, Any]]] | None:
        """
        Return the full cached release if it exists, is complete (all 16
        expected blocks present), and was last successfully synced within
        ttl_seconds. Returns None on any miss — callers fall back to Jira.

        ttl_seconds <= 0 always misses, mirroring the existing in-memory
        _JIRA_SOURCE_CACHE's own "ttl_seconds > 0" gate in
        _prepare_jira_source_data.
        """
        start = time.perf_counter()

        if ttl_seconds <= 0:
            logger.info(
                "jira_cache READ project=%s release=%s result=MISS reason=ttl_disabled elapsed_ms=%.1f",
                project_key, release_id, (time.perf_counter() - start) * 1000,
            )
            return None

        with self._connect() as connection:
            meta_row = connection.execute(
                "SELECT last_synced_at FROM jira_release_sync_meta WHERE project_key=? AND release_id=?",
                (project_key, release_id),
            ).fetchone()

            if meta_row is None or not meta_row["last_synced_at"]:
                logger.info(
                    "jira_cache READ project=%s release=%s result=MISS reason=never_synced elapsed_ms=%.1f",
                    project_key, release_id, (time.perf_counter() - start) * 1000,
                )
                return None

            try:
                synced_at = datetime.fromisoformat(meta_row["last_synced_at"])
            except ValueError:
                logger.warning(
                    "jira_cache READ project=%s release=%s result=MISS reason=unparseable_timestamp",
                    project_key, release_id,
                )
                return None

            age_seconds = (datetime.now(timezone.utc) - synced_at).total_seconds()
            if age_seconds >= ttl_seconds:
                logger.info(
                    "jira_cache READ project=%s release=%s result=MISS reason=stale age_s=%.0f ttl_s=%d elapsed_ms=%.1f",
                    project_key, release_id, age_seconds, ttl_seconds, (time.perf_counter() - start) * 1000,
                )
                return None

            rows = connection.execute(
                "SELECT block_name, data_json FROM jira_release_blocks WHERE project_key=? AND release_id=?",
                (project_key, release_id),
            ).fetchall()

        blocks = {row["block_name"]: row["data_json"] for row in rows}
        missing = [name for name in EXPECTED_BLOCK_NAMES if name not in blocks]
        if missing:
            logger.warning(
                "jira_cache READ project=%s release=%s result=MISS reason=incomplete missing=%s elapsed_ms=%.1f",
                project_key, release_id, missing, (time.perf_counter() - start) * 1000,
            )
            return None

        source_data = {name: json.loads(blocks[name]) for name in EXPECTED_BLOCK_NAMES}

        logger.info(
            "jira_cache READ project=%s release=%s result=HIT age_s=%.0f elapsed_ms=%.1f",
            project_key, release_id, age_seconds, (time.perf_counter() - start) * 1000,
        )
        return source_data

    def get_full_release_any_freshness(
        self,
        project_key: str,
        release_id: str,
    ) -> dict[str, list[dict[str, Any]]] | None:
        """
        Return the full cached release regardless of how old it is, as long
        as every expected block is present.

        Used by the query-time read path (_prepare_jira_source_data), which
        is no longer allowed to fall back to Jira at all: under that policy,
        staleness is the scheduler's problem to fix on its next run, not a
        reason to treat existing data as unusable mid-request. Contrast with
        the TTL-gated get_full_release() above, which still misses on stale
        data and is kept for any caller that wants that stricter guarantee.
        """
        start = time.perf_counter()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT block_name, data_json FROM jira_release_blocks WHERE project_key=? AND release_id=?",
                (project_key, release_id),
            ).fetchall()

        blocks = {row["block_name"]: row["data_json"] for row in rows}
        missing = [name for name in EXPECTED_BLOCK_NAMES if name not in blocks]
        if missing:
            logger.info(
                "jira_cache READ(any_freshness) project=%s release=%s result=MISS missing=%s elapsed_ms=%.1f",
                project_key, release_id, missing, (time.perf_counter() - start) * 1000,
            )
            return None

        source_data = {name: json.loads(blocks[name]) for name in EXPECTED_BLOCK_NAMES}
        logger.info(
            "jira_cache READ(any_freshness) project=%s release=%s result=HIT elapsed_ms=%.1f",
            project_key, release_id, (time.perf_counter() - start) * 1000,
        )
        return source_data

    def get_blocks(
        self,
        project_key: str,
        release_id: str,
        block_names: Iterable[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Agent-specific read: return only the requested blocks (e.g. a
        single specialist's own *_INPUT_BLOCKS), not the whole release.
        Blocks that don't exist in the cache are simply absent from the
        result rather than raising — callers should treat a short result
        as a partial/no cache and fall back accordingly.
        """
        start = time.perf_counter()
        names = [str(name).strip() for name in block_names if str(name).strip()]
        if not names:
            return {}

        placeholders = ",".join("?" for _ in names)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT block_name, data_json FROM jira_release_blocks "
                f"WHERE project_key=? AND release_id=? AND block_name IN ({placeholders})",
                (project_key, release_id, *names),
            ).fetchall()

        result = {row["block_name"]: json.loads(row["data_json"]) for row in rows}
        logger.info(
            "jira_cache READ(blocks) project=%s release=%s requested=%d found=%d elapsed_ms=%.1f",
            project_key, release_id, len(names), len(result), (time.perf_counter() - start) * 1000,
        )
        return result

    def is_fresh(self, project_key: str, release_id: str, ttl_seconds: int) -> bool:
        return self.get_full_release(project_key, release_id, ttl_seconds) is not None

    def list_known_releases(self) -> list[tuple[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT project_key, release_id FROM jira_release_sync_meta"
            ).fetchall()
        return [(row["project_key"], row["release_id"]) for row in rows]

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def save_release(
        self,
        project_key: str,
        release_id: str,
        source_data: dict[str, list[dict[str, Any]]],
    ) -> None:
        """
        Upsert every block plus a SUCCESS meta row in one transaction, so a
        crash mid-write can never leave a mix of old and new blocks for
        the same release.
        """
        start = time.perf_counter()
        now = _utcnow_iso()

        with self._connect() as connection:
            connection.execute("BEGIN")
            try:
                for block_name, rows in source_data.items():
                    connection.execute(
                        """
                        INSERT INTO jira_release_blocks
                            (project_key, release_id, block_name, data_json, row_count, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(project_key, release_id, block_name) DO UPDATE SET
                            data_json = excluded.data_json,
                            row_count = excluded.row_count,
                            updated_at = excluded.updated_at
                        """,
                        (
                            project_key, release_id, block_name,
                            json.dumps(rows, ensure_ascii=False, default=str),
                            len(rows) if isinstance(rows, list) else 0,
                            now,
                        ),
                    )

                connection.execute(
                    """
                    INSERT INTO jira_release_sync_meta
                        (project_key, release_id, last_synced_at, last_sync_status, last_error)
                    VALUES (?, ?, ?, 'SUCCESS', NULL)
                    ON CONFLICT(project_key, release_id) DO UPDATE SET
                        last_synced_at = excluded.last_synced_at,
                        last_sync_status = 'SUCCESS',
                        last_error = NULL
                    """,
                    (project_key, release_id, now),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

        logger.info(
            "jira_cache WRITE project=%s release=%s blocks=%d elapsed_ms=%.1f",
            project_key, release_id, len(source_data), (time.perf_counter() - start) * 1000,
        )

    def register_pending_release(self, project_key: str, release_id: str) -> None:
        """
        Record that a query asked for a release neither cache has ever
        synced, so the next scheduled refresh (app/persistence/scheduler.py,
        via list_known_releases()) picks it up. This is the ONLY way an
        unseen release enters the sync rotation — query-time code never
        fetches Jira itself.

        A no-op if a meta row already exists (SUCCESS, FAILED, or an
        earlier PENDING) — never overwrites real sync history.
        """
        now = _utcnow_iso()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jira_release_sync_meta
                    (project_key, release_id, last_synced_at, last_sync_status, last_error)
                VALUES (?, ?, '', 'PENDING', NULL)
                ON CONFLICT(project_key, release_id) DO NOTHING
                """,
                (project_key, release_id),
            )
        logger.info(
            "jira_cache REGISTER_PENDING project=%s release=%s registered_at=%s",
            project_key, release_id, now,
        )

    def mark_sync_failed(self, project_key: str, release_id: str, error: str) -> None:
        """
        Record a failed sync WITHOUT touching jira_release_blocks — the
        previous valid data (if any) is left exactly as it was. Also
        deliberately does not overwrite last_synced_at on an existing row,
        so freshness checks keep measuring age from the last SUCCESSFUL
        sync, not from this failed attempt — otherwise a repeatedly-failing
        scheduled refresh would look "freshly synced" forever while the
        underlying data silently goes stale.
        """
        start = time.perf_counter()
        now = _utcnow_iso()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jira_release_sync_meta
                    (project_key, release_id, last_synced_at, last_sync_status, last_error)
                VALUES (?, ?, ?, 'FAILED', ?)
                ON CONFLICT(project_key, release_id) DO UPDATE SET
                    last_sync_status = 'FAILED',
                    last_error = excluded.last_error
                """,
                (project_key, release_id, now, str(error)[:2000]),
            )

        logger.warning(
            "jira_cache SYNC_FAILED project=%s release=%s error=%s elapsed_ms=%.1f — previous data retained",
            project_key, release_id, str(error)[:200], (time.perf_counter() - start) * 1000,
        )


@lru_cache(maxsize=1)
def get_jira_cache_repository() -> JiraCacheRepository:
    """
    Process-wide singleton, mirroring the existing get_settings() pattern.
    Constructing it runs ensure_schema() exactly once per process — this is
    also what the FastAPI startup hook calls to guarantee the DB/schema
    exist before the app starts serving requests.
    """
    return JiraCacheRepository(get_settings().jira_cache_db_path)
