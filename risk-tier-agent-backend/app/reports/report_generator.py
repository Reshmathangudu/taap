from __future__ import annotations

import csv
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.models import PipelineState
from app.utils.serialization import to_serializable


CLASSIFICATION_HEADERS = [
    "test_case_id",
    "test_name",
    "module_id",
    "tier",
    "criticality_score",
    "change_impact_factor",
    "criticality_factor",
    "historical_value_score",
    "historical_value_factor",
    "release_type",
    "release_risk_factor",
    "composite_score",
    "risk_band",
    "base_classification",
    "classification",
    "classification_overridden",
    "execution_minutes",
    "protection_flags",
    "reasons",
]


class ReportGenerator:
    """Generate JSON and CSV reports for a completed Risk Tier pipeline.

    Excel output has intentionally been removed. The pipeline now produces:
    - <release_id>_risk_tier_report.json
    - <release_id>_test_classifications.csv
    """

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, state: PipelineState) -> dict[str, str]:
        release_id = _safe_release_id(state.release_id)
        json_path = self.output_dir / f"{release_id}_risk_tier_report.json"
        csv_path = self.output_dir / f"{release_id}_test_classifications.csv"

        self._write_json(state, json_path)
        self._write_csv(state, csv_path)

        return {
            "json": str(json_path),
            "csv": str(csv_path),
        }

    @staticmethod
    def _write_json(state: PipelineState, path: Path) -> None:
        serializable_state = to_serializable(state)
        path.write_text(
            json.dumps(
                serializable_state,
                indent=2,
                ensure_ascii=False,
                default=str,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _write_csv(state: PipelineState, path: Path) -> None:
        scoring = _as_dict(getattr(state, "scoring", None))
        scoring_results = _as_list(scoring.get("results", []))

        with path.open(mode="w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=CLASSIFICATION_HEADERS,
                extrasaction="ignore",
            )
            writer.writeheader()

            for source_row in scoring_results:
                row = _as_dict(source_row)
                output = {
                    header: csv_safe_value(row.get(header))
                    for header in CLASSIFICATION_HEADERS
                }
                writer.writerow(output)


def csv_safe_value(value: Any) -> Any:
    if value is None:
        return ""

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, set):
        value = sorted(value, key=lambda item: str(item))

    if isinstance(value, tuple):
        value = list(value)

    if isinstance(value, list):
        if all(_is_simple_scalar(item) for item in value):
            return " | ".join("" if item is None else str(item) for item in value)
        return _json_string(value)

    if isinstance(value, dict):
        return _json_string(value)

    return _json_string(to_serializable(value))


def _json_string(value: Any) -> str:
    return json.dumps(
        to_serializable(value),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _is_simple_scalar(value: Any) -> bool:
    return value is None or isinstance(
        value,
        (str, int, float, bool, Decimal, datetime, date, Path),
    )


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value

    serializable = to_serializable(value)
    return serializable if isinstance(serializable, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _safe_release_id(value: Any) -> str:
    release_id = str(value or "").strip()
    if not release_id:
        raise ValueError("Pipeline state release_id cannot be empty.")

    safe = []
    for character in release_id:
        safe.append(character if character.isalnum() or character in {"-", "_", "."} else "_")

    normalized = "".join(safe).strip("._")
    if not normalized:
        raise ValueError(
            "Pipeline state release_id does not contain any valid filename characters."
        )
    return normalized
