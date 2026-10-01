from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable


SCHEMA = """
CREATE TABLE IF NOT EXISTS test_cases (
    test_case_id TEXT PRIMARY KEY,
    test_name TEXT NOT NULL,
    module_id TEXT NOT NULL,
    requirement_id TEXT NOT NULL,
    story_id TEXT NOT NULL,
    test_type TEXT,
    automation_status TEXT,
    execution_minutes REAL,
    regulatory_flag TEXT,
    status TEXT,
    created_date TEXT
);
CREATE INDEX IF NOT EXISTS idx_test_story ON test_cases(story_id);
CREATE INDEX IF NOT EXISTS idx_test_requirement ON test_cases(requirement_id);
CREATE INDEX IF NOT EXISTS idx_test_module ON test_cases(module_id);
CREATE INDEX IF NOT EXISTS idx_test_status ON test_cases(status);
"""


class TestRepository:
    """SQLite repository suitable for tens or hundreds of thousands of test records."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def upsert_many(self, rows: Iterable[dict[str, Any]], batch_size: int = 5000) -> int:
        sql = """
        INSERT INTO test_cases (
            test_case_id, test_name, module_id, requirement_id, story_id,
            test_type, automation_status, execution_minutes,
            regulatory_flag, status, created_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(test_case_id) DO UPDATE SET
            test_name=excluded.test_name,
            module_id=excluded.module_id,
            requirement_id=excluded.requirement_id,
            story_id=excluded.story_id,
            test_type=excluded.test_type,
            automation_status=excluded.automation_status,
            execution_minutes=excluded.execution_minutes,
            regulatory_flag=excluded.regulatory_flag,
            status=excluded.status,
            created_date=excluded.created_date
        """
        count = 0
        buffer: list[tuple[Any, ...]] = []
        with self._connect() as connection:
            for row in rows:
                buffer.append((
                    row["Test_Case_ID"], row["Test_Name"], row["Module_ID"],
                    row["Requirement_ID"], row["Story_ID"], row.get("Test_Type"),
                    row.get("Automation_Status"), row.get("Execution_Minutes"),
                    row.get("Regulatory_Flag"), row.get("Status"), row.get("Created_Date"),
                ))
                if len(buffer) >= batch_size:
                    connection.executemany(sql, buffer)
                    count += len(buffer)
                    buffer.clear()
            if buffer:
                connection.executemany(sql, buffer)
                count += len(buffer)
            connection.commit()
        return count

    def active_tests(self, story_ids: list[str] | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM test_cases WHERE UPPER(status) = 'ACTIVE'"
        params: list[Any] = []
        if story_ids:
            placeholders = ",".join("?" for _ in story_ids)
            query += f" AND story_id IN ({placeholders})"
            params.extend(story_ids)
        query += " ORDER BY test_case_id"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._to_agent_row(row) for row in rows]

    def count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM test_cases").fetchone()[0])

    @staticmethod
    def _to_agent_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "Test_Case_ID": row["test_case_id"],
            "Test_Name": row["test_name"],
            "Module_ID": row["module_id"],
            "Requirement_ID": row["requirement_id"],
            "Story_ID": row["story_id"],
            "Test_Type": row["test_type"],
            "Automation_Status": row["automation_status"],
            "Execution_Minutes": row["execution_minutes"],
            "Regulatory_Flag": row["regulatory_flag"],
            "Status": row["status"],
            "Created_Date": row["created_date"],
        }
