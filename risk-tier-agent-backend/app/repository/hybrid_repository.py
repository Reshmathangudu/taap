from __future__ import annotations

from typing import Any

from app.data_sources.hybrid_source import HybridRiskTierSource
from app.repository.excel_repository import ExcelRepository


class HybridRepository:
    """Route release hierarchy/test data to Jira+SQLite and all other sheets to Excel."""

    HYBRID_SHEETS = {"02_Epics", "03_User_Stories", "06_Test_Cases"}

    def __init__(
        self,
        excel: ExcelRepository,
        hybrid_source: HybridRiskTierSource,
        release_label: str,
    ) -> None:
        self.excel = excel
        self.hybrid_source = hybrid_source
        self.release_label = release_label
        self._hybrid_cache: dict[str, list[dict[str, Any]]] | None = None

    def _load_hybrid(self) -> dict[str, list[dict[str, Any]]]:
        if self._hybrid_cache is None:
            self._hybrid_cache = self.hybrid_source.load_release_hierarchy(
                self.release_label
            )
        return self._hybrid_cache

    def set_release_label(self, release_label: str) -> None:
        normalized = str(release_label or "").strip()
        if normalized and normalized != self.release_label:
            self.release_label = normalized
            self._hybrid_cache = None

    def rows(self, sheet_name: str) -> list[dict[str, Any]]:
        if sheet_name in self.HYBRID_SHEETS:
            return self._load_hybrid().get(sheet_name, [])
        return self.excel.rows(sheet_name)

    def filter(self, sheet_name: str, **criteria: Any) -> list[dict[str, Any]]:
        return [
            row
            for row in self.rows(sheet_name)
            if all(row.get(column) == expected for column, expected in criteria.items())
        ]

    def first(self, sheet_name: str, **criteria: Any) -> dict[str, Any] | None:
        rows = self.filter(sheet_name, **criteria)
        return rows[0] if rows else None
