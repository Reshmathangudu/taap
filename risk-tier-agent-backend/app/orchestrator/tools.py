from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Iterable

from app.config import get_settings
from app.orchestrator.master_orchestrator import RiskTierMasterOrchestrator
from app.persistence.errors import ReleaseDataUnavailableError
from app.query_tools import answer_agent_question

VALID_CLASSIFICATIONS = {
    "MUST_TEST",
    "RECOMMENDED",
    "OPTIONAL",
    "EXCLUDE",
    "EXCLUDE_CANDIDATE",
}

ACTIVE_SELECTION_CLASSIFICATIONS = {
    "MUST_TEST",
    "RECOMMENDED",
}

# ADK calls each tool independently. Keep the last validated Jira context so
# follow-up questions in the same ADK session do not require the user to paste
# the Jira link again. This is only a routing hint; every query still creates
# a new orchestrator/client and fetches current Jira data.
_LAST_JIRA_CONTEXT: dict[str, str] = {}


def _output_directory() -> Path:
    """
    Resolve the same output directory used by the pipeline.

    Using application settings prevents the query tools from reading a
    different folder from the Report Generator.
    """
    output_dir = Path(
        get_settings().output_dir
    )
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    return output_dir


def execute_risk_tier_pipeline(
    jira_link: str,
    release_id: str,
) -> dict[str, Any]:
    settings = get_settings()

    normalized_release_id = str(release_id or "").strip().upper()
    normalized_jira_link = str(jira_link or "").strip()

    if not normalized_release_id:
        return {
            "status": "needs_input",
            "message": "Please provide the release ID.",
        }

    if not normalized_jira_link:
        return {
            "status": "needs_input",
            "message": "Please provide the Jira link.",
        }

    _LAST_JIRA_CONTEXT.update(
        jira_link=normalized_jira_link,
        release_id=normalized_release_id,
    )

    orchestrator = RiskTierMasterOrchestrator.from_settings(
        settings=settings,
        jira_link=normalized_jira_link,
    )

    try:
        state = orchestrator.execute(normalized_release_id)
    except ReleaseDataUnavailableError as exc:
        return {
            "status": "not_found",
            "release_id": normalized_release_id,
            "message": str(exc),
        }

    scoring = state.scoring.get(
        "agent_output",
        state.scoring,
    )

    governance = state.governance.get(
        "agent_output",
        state.governance,
    )

    policy = state.policy.get(
        "agent_output",
        state.policy,
    )

    change_impact = state.change_impact.get(
        "agent_output",
        state.change_impact,
    )

    criticality = state.criticality.get(
        "agent_output",
        state.criticality,
    )

    history = state.history.get(
        "agent_output",
        state.history,
    )

    return {
        "status": "success",
        "release_id": normalized_release_id,

        "release": state.release,

        "change_impact_summary": change_impact.get(
            "summary",
            {},
        ),

        "criticality_summary": criticality.get(
            "summary",
            {},
        ),

        "historical_summary": history.get(
            "summary",
            {},
        ),

        "policy_summary": policy.get(
            "summary",
            {},
        ),

        "classification_summary": scoring.get(
            "summary",
            {},
        ),

        "governance_summary": governance.get(
            "summary",
            {},
        ),

        "report_files": state.report_files,
    }


def get_must_test_cases(
    release_id: str,
) -> dict[str, Any]:
    """
    Read a generated classification CSV and return all MUST_TEST cases.

    This helper does not execute the Risk Tier pipeline. The complete
    pipeline must run first and generate:

        <output_dir>/<release_id>_test_classifications.csv
    """

    return get_test_cases_by_classification(
        release_id=release_id,
        classification="MUST_TEST",
        response_key="must_test_cases",
    )


def get_test_cases_by_classification(
    release_id: str,
    classification: str,
    response_key: str = "test_cases",
) -> dict[str, Any]:
    """
    Return test cases matching a requested classification.

    Supported classifications:
    - MUST_TEST
    - RECOMMENDED
    - OPTIONAL
    - EXCLUDE
    - EXCLUDE_CANDIDATE
    """

    try:
        normalized_release_id = (
            _normalize_release_id(
                release_id
            )
        )
    except ValueError as error:
        return _error_result(
            message=str(error),
            release_id=str(
                release_id or ""
            ).strip(),
            classification=(
                _normalize_classification(
                    classification
                )
            ),
            response_key=response_key,
        )

    normalized_classification = (
        _normalize_classification(
            classification
        )
    )

    if not normalized_classification:
        return _error_result(
            message=(
                "classification cannot be empty."
            ),
            release_id=normalized_release_id,
            classification="",
            response_key=response_key,
        )

    if (
        normalized_classification
        not in VALID_CLASSIFICATIONS
    ):
        return _error_result(
            message=(
                "Unsupported classification "
                f"{normalized_classification!r}. "
                "Supported classifications are: "
                f"{sorted(VALID_CLASSIFICATIONS)}"
            ),
            release_id=normalized_release_id,
            classification=(
                normalized_classification
            ),
            response_key=response_key,
        )

    csv_path = _classification_report_path(
        normalized_release_id
    )

    if not csv_path.exists():
        return _error_result(
            message=(
                "The classification report does not exist. "
                f"Expected file: {csv_path}. "
                "Run the complete Risk Tier pipeline first."
            ),
            release_id=normalized_release_id,
            classification=(
                normalized_classification
            ),
            response_key=response_key,
            report_path=str(csv_path),
        )

    if not csv_path.is_file():
        return _error_result(
            message=(
                "The classification report path is not "
                f"a file: {csv_path}"
            ),
            release_id=normalized_release_id,
            classification=(
                normalized_classification
            ),
            response_key=response_key,
            report_path=str(csv_path),
        )

    try:
        report = _read_classification_report(
            csv_path
        )
    except (
        OSError,
        UnicodeError,
        csv.Error,
        ValueError,
    ) as error:
        return _error_result(
            message=(
                "Unable to read the classification "
                f"report: {error}"
            ),
            release_id=normalized_release_id,
            classification=(
                normalized_classification
            ),
            response_key=response_key,
            report_path=str(csv_path),
        )

    matching_cases = [
        row
        for row in report["rows"]
        if row["classification"]
        == normalized_classification
    ]

    matching_cases.sort(
        key=lambda item: (
            item["test_case_id"],
            item.get("test_name", ""),
        )
    )

    result: dict[str, Any] = {
        "status": "success",
        "release_id": normalized_release_id,
        "classification": (
            normalized_classification
        ),
        "report_path": str(csv_path),
        "count": len(matching_cases),
        response_key: matching_cases,
        "summary": {
            "classification": (
                normalized_classification
            ),
            "matching_test_count": len(
                matching_cases
            ),
            "total_report_rows": report[
                "total_rows"
            ],
            "available_classifications": (
                report[
                    "classification_counts"
                ]
            ),
        },
    }

    if (
        normalized_classification
        == "MUST_TEST"
    ):
        result["must_test_count"] = len(
            matching_cases
        )

        if response_key != "must_test_cases":
            result["must_test_cases"] = (
                matching_cases
            )

    result["agent_output"] = {
        "release_id": normalized_release_id,
        "classification": (
            normalized_classification
        ),
        "count": len(matching_cases),
        "test_case_ids": [
            row["test_case_id"]
            for row in matching_cases
        ],
        "test_cases": matching_cases,
    }

    result["markdown"] = (
        format_classification_cards(
            release_id=normalized_release_id,
            classification=(
                normalized_classification
            ),
            test_cases=matching_cases,
        )
    )

    return result


def get_must_test_cards(
    release_id: str,
) -> dict[str, Any]:
    """
    Return MUST_TEST cases with Markdown formatted for ADK.
    """

    result = get_must_test_cases(
        release_id
    )

    if result.get("status") != "success":
        return result

    return {
        **result,
        "markdown": format_classification_cards(
            release_id=result[
                "release_id"
            ],
            classification="MUST_TEST",
            test_cases=result.get(
                "must_test_cases",
                [],
            ),
        ),
    }


def get_classification_cards(
    release_id: str,
    classification: str,
) -> dict[str, Any]:
    """
    Return any supported classification as ADK Markdown cards.
    """

    result = get_test_cases_by_classification(
        release_id=release_id,
        classification=classification,
    )

    if result.get("status") != "success":
        return result

    return {
        **result,
        "markdown": format_classification_cards(
            release_id=result[
                "release_id"
            ],
            classification=result[
                "classification"
            ],
            test_cases=result.get(
                "test_cases",
                [],
            ),
        ),
    }


def get_classification_summary(
    release_id: str,
) -> dict[str, Any]:
    """
    Return classification totals from the generated CSV report.
    """

    try:
        normalized_release_id = (
            _normalize_release_id(
                release_id
            )
        )
    except ValueError as error:
        return {
            "status": "error",
            "release_id": str(
                release_id or ""
            ).strip(),
            "message": str(error),
            "summary": {},
        }

    csv_path = _classification_report_path(
        normalized_release_id
    )

    if not csv_path.exists():
        return {
            "status": "error",
            "release_id": normalized_release_id,
            "report_path": str(csv_path),
            "message": (
                "The classification report does not exist. "
                f"Expected file: {csv_path}. "
                "Run the complete Risk Tier pipeline first."
            ),
            "summary": {},
        }

    try:
        report = _read_classification_report(
            csv_path
        )
    except (
        OSError,
        UnicodeError,
        csv.Error,
        ValueError,
    ) as error:
        return {
            "status": "error",
            "release_id": normalized_release_id,
            "report_path": str(csv_path),
            "message": (
                "Unable to read the classification "
                f"report: {error}"
            ),
            "summary": {},
        }

    counts = {
        classification: report[
            "classification_counts"
        ].get(
            classification,
            0,
        )
        for classification in (
            "MUST_TEST",
            "RECOMMENDED",
            "OPTIONAL",
            "EXCLUDE",
        )
    }

    selected_count = sum(
        counts[classification]
        for classification
        in ACTIVE_SELECTION_CLASSIFICATIONS
    )

    total_tests = report[
        "total_rows"
    ]

    summary = {
        "total_tests": total_tests,
        **counts,
        "selected_tests": selected_count,
        "not_selected_tests": (
            total_tests - selected_count
        ),
        "selection_percentage": (
            round(
                selected_count
                / total_tests
                * 100,
                2,
            )
            if total_tests
            else 0.0
        ),
    }

    result: dict[str, Any] = {
        "status": "success",
        "release_id": normalized_release_id,
        "report_path": str(csv_path),
        "summary": summary,
        "agent_output": summary,
    }

    result["markdown"] = (
        format_classification_summary(
            release_id=normalized_release_id,
            summary=summary,
        )
    )

    return result


def _build_pipeline_summary(state: Any) -> dict[str, Any]:
    """Build a compact summary from the orchestrator pipeline state."""

    change_impact = getattr(state, "change_impact", {}) or {}
    criticality = getattr(state, "criticality", {}) or {}
    history = getattr(state, "history", {}) or {}
    policy = getattr(state, "policy", {}) or {}
    scoring = getattr(state, "scoring", {}) or {}
    governance = getattr(state, "governance", {}) or {}
    release = getattr(state, "release", {}) or {}

    change_summary = change_impact.get("summary", {}) if isinstance(change_impact, dict) else {}
    criticality_summary = criticality.get("summary", {}) if isinstance(criticality, dict) else {}
    history_summary = history.get("summary", {}) if isinstance(history, dict) else {}
    policy_summary = policy.get("summary", {}) if isinstance(policy, dict) else {}
    scoring_summary = scoring.get("summary", {}) if isinstance(scoring, dict) else {}
    governance_summary = governance.get("summary", {}) if isinstance(governance, dict) else {}

    release_type = (
        scoring.get("release_type")
        if isinstance(scoring, dict)
        else None
    ) or (
        policy.get("release_type")
        if isinstance(policy, dict)
        else None
    ) or release.get("Release_Type") or release.get("release_type") or "UNKNOWN"

    # The Feature Change Agent exposes two distinct downstream populations:
    #
    # 1. downstream_module_test_ids:
    #    all active tests on declared downstream/dependent modules
    #
    # 2. downstream_test_ids:
    #    additional downstream tests that are not already direct impacts
    #
    # The executive metric "Downstream Impacted Tests" must represent the
    # additional impact, not the full downstream-module population and not
    # the sum of the two populations.
    # The pipeline state can contain either:
    #   1. the full Feature Agent result with an "agent_output" child, or
    #   2. the compact agent_output mapping directly.
    #
    # Normalize both shapes so the executive report always reads the
    # Feature Agent's authoritative downstream_test_ids rather than a
    # stale/aggregated summary value.
    if isinstance(change_impact, dict):
        nested_agent_output = change_impact.get(
            "agent_output"
        )
        if isinstance(nested_agent_output, dict):
            feature_agent_output = nested_agent_output
        else:
            feature_agent_output = change_impact
    else:
        feature_agent_output = {}

    downstream_test_ids = feature_agent_output.get(
        "downstream_test_ids",
        [],
    )
    downstream_module_test_ids = feature_agent_output.get(
        "downstream_module_test_ids",
        [],
    )

    if not isinstance(downstream_test_ids, (list, tuple, set)):
        downstream_test_ids = []

    if not isinstance(downstream_module_test_ids, (list, tuple, set)):
        downstream_module_test_ids = []

    # Prefer the Feature Agent's authoritative additional-downstream IDs.
    # Fall back to the existing summary only for backward compatibility with
    # older state payloads that do not expose agent_output.
    authoritative_downstream_count = len(
        {
            str(test_id).strip()
            for test_id in downstream_test_ids
            if str(test_id).strip()
        }
    )

    # The current Feature Agent contract always provides downstream_test_ids.
    # Treat that list as authoritative. Never fall back to a pre-aggregated
    # downstream_impacted_tests value because older summaries may contain the
    # module-level downstream population instead of the additional downstream
    # population required by the current contract.
    downstream_impacted_tests = authoritative_downstream_count

    downstream_module_test_case_count = len(
        {
            str(test_id).strip()
            for test_id in downstream_module_test_ids
            if str(test_id).strip()
        }
    )

    return {
        "release_id": getattr(state, "release_id", ""),
        "release_type": str(release_type).strip() or "UNKNOWN",
        "total_tests": scoring_summary.get("total_tests", 0),
        "must_test": scoring_summary.get("MUST_TEST", 0),
        "recommended": scoring_summary.get("RECOMMENDED", 0),
        "optional": scoring_summary.get("OPTIONAL", 0),
        "exclude": scoring_summary.get("EXCLUDE", 0),
        "change_impact": {
            "changed_epics": change_summary.get("changed_epics", change_summary.get("changed_epic_count", 0)),
            "changed_stories": change_summary.get("changed_user_stories", change_summary.get("changed_story_count", 0)),
            "changed_requirements": change_summary.get("changed_requirements", 0),
            "directly_impacted_tests": change_summary.get("directly_impacted_tests", 0),
            "downstream_impacted_tests": downstream_impacted_tests,
            "downstream_module_test_cases": downstream_module_test_case_count,
            "traceability_gaps": change_summary.get("traceability_gaps", 0),
            "new_feature_protected_tests": change_summary.get("new_feature_protected_tests", 0),
        },
        "criticality": {
            "tier_1_modules": criticality_summary.get("tier_1_modules", 0),
            "tier_2_modules": criticality_summary.get("tier_2_modules", 0),
            "tier_3_modules": criticality_summary.get("tier_3_modules", 0),
            "tier_4_modules": criticality_summary.get("tier_4_modules", 0),
        },
        "historical": {
            "test_cases_analysed": history_summary.get("test_cases_analysed", history_summary.get("total_test_cases", 0)),
            "historical_executions": history_summary.get("historical_executions", 0),
            "passed_executions": history_summary.get("passed_executions", 0),
            "failed_executions": history_summary.get("failed_executions", 0),
            "confirmed_defects": history_summary.get("confirmed_defects", 0),
            "production_defects": history_summary.get("production_defects", 0),
            "flaky_tests": history_summary.get("flaky_tests", 0),
            "defect_protected_tests": history_summary.get("defect_protected_tests", 0),
            "tests_with_insufficient_history": history_summary.get("tests_with_insufficient_history", 0),
        },
        "policy": {
            "release_type": policy_summary.get("release_type", str(release_type).strip() or "UNKNOWN"),
            "regulatory_test_count": policy_summary.get("regulatory_test_count", 0),
            "mandatory_test_count": policy_summary.get("mandatory_test_count", 0),
            "exclusion_prohibited_test_count": policy_summary.get("exclusion_prohibited_test_count", 0),
            "maximum_exclusion_percentage": policy_summary.get("overall_max_exclusion_percent", policy_summary.get("maximum_allowed_exclusion_percent", 0.0)),
            "approval_required": policy_summary.get("require_approval_for_exclusion", policy_summary.get("approval_required", True)),
        },
        "governance": {
            "exclusion_candidates": governance_summary.get("exclusion_candidates", 0),
            "approved_exclusions": governance_summary.get("approved_exclusions", 0),
            "pending_approvals": governance_summary.get("pending_approvals", 0),
            "exclusion_rate": governance_summary.get("exclusion_rate_percent", governance_summary.get("exclusion_rate", 0.0)),
            "maximum_exclusion_rate": governance_summary.get("maximum_allowed_exclusion_percent", governance_summary.get("maximum_allowed_exclusion_rate", 0.0)),
            "exclusion_cap_exceeded": governance_summary.get("over_cap", governance_summary.get("exclusion_cap_exceeded", False)),
        },
    }


def _format_pipeline_markdown(result: dict[str, Any]) -> str:
    summary = result.get("summary", {})
    change = summary.get("change_impact", {})
    criticality = summary.get("criticality", {})
    historical = summary.get("historical", {})
    policy = summary.get("policy", {})
    governance = summary.get("governance", {})

    lines = [
        f"# Risk Tier Executive Report — {summary.get('release_id', result.get('release_id', 'UNKNOWN'))}",
        "",
        "## 1. Executive Summary",
        "",
        f"- Release ID: {summary.get('release_id', result.get('release_id', 'UNKNOWN'))}",
        f"- Release Type: {summary.get('release_type', 'UNKNOWN')}",
        f"- Analysis Status: COMPLETED",
        f"- Total Active Test Cases: {summary.get('total_tests', 0)}",
        f"- Must-Test Count: {summary.get('must_test', 0)}",
        f"- Recommended Count: {summary.get('recommended', 0)}",
        f"- Optional Count: {summary.get('optional', 0)}",
        f"- Exclude Candidate Count: {summary.get('exclude', 0)}",
        f"- Pending Governance Approvals: {governance.get('pending_approvals', 0)}",
        "",
        "---",
        "",
        "## 2. Change Impact Summary",
        "",
        f"- Changed Epics: {change.get('changed_epics', 0)}",
        f"- Changed User Stories: {change.get('changed_stories', 0)}",
        f"- Changed Requirements: {change.get('changed_requirements', 0)}",
        f"- Directly Impacted Tests: {change.get('directly_impacted_tests', 0)}",
        f"- Downstream Impacted Tests: {change.get('downstream_impacted_tests', 0)}",
        f"- Downstream Module Test Cases: {change.get('downstream_module_test_cases', 0)}",
        f"- Traceability Gaps: {change.get('traceability_gaps', 0)}",
        f"- New Feature Protected Tests: {change.get('new_feature_protected_tests', 0)}",
        "",
        "---",
        "",
        "## 3. Application Criticality Summary",
        "",
        f"- Tier-1 Module Count: {criticality.get('tier_1_modules', 0)}",
        f"- Tier-2 Module Count: {criticality.get('tier_2_modules', 0)}",
        f"- Tier-3 Module Count: {criticality.get('tier_3_modules', 0)}",
        f"- Tier-4 Module Count: {criticality.get('tier_4_modules', 0)}",
        "",
        "Module tier count is not the same as test-case count. Test cases inherit the tier of their mapped module.",
        "",
        "---",
        "",
        "## 4. Historical Execution Summary",
        "",
        f"- Test Cases Analysed: {historical.get('test_cases_analysed', 0)}",
        f"- Historical Executions: {historical.get('historical_executions', 0)}",
        f"- Passed Executions: {historical.get('passed_executions', 0)}",
        f"- Failed Executions: {historical.get('failed_executions', 0)}",
        f"- Confirmed Defects: {historical.get('confirmed_defects', 0)}",
        f"- Production Defects: {historical.get('production_defects', 0)}",
        f"- Flaky Tests: {historical.get('flaky_tests', 0)}",
        f"- Defect Protected Tests: {historical.get('defect_protected_tests', 0)}",
        f"- Tests with Insufficient History: {historical.get('tests_with_insufficient_history', 0)}",
        "",
        "---",
        "",
        "## 5. Policy Summary",
        "",
        f"- Release Type: {policy.get('release_type', 'UNKNOWN')}",
        f"- Regulatory Test Count: {policy.get('regulatory_test_count', 0)}",
        f"- Mandatory Test Count: {policy.get('mandatory_test_count', 0)}",
        f"- Exclusion-Prohibited Test Count: {policy.get('exclusion_prohibited_test_count', 0)}",
        f"- Maximum Exclusion Percentage: {policy.get('maximum_exclusion_percentage', 0)}",
        f"- Approval Required: {'Yes' if policy.get('approval_required') else 'No'}",
        "",
        "---",
        "",
        "## 6. Final Risk Classification Summary",
        "",
        "| Classification | Count | Meaning |",
        "|---|---:|---|",
        f"| Must-Test | {summary.get('must_test', 0)} | Protected or high-risk tests |",
        f"| Recommended | {summary.get('recommended', 0)} | Recommended execution |",
        f"| Optional | {summary.get('optional', 0)} | Optional execution |",
        f"| Exclude Candidates | {summary.get('exclude', 0)} | Requires governance review |",
        "",
        "---",
        "",
        "## 7. Governance Summary",
        "",
        f"- Exclusion Candidates: {governance.get('exclusion_candidates', 0)}",
        f"- Approved Exclusions: {governance.get('approved_exclusions', 0)}",
        f"- Pending Approvals: {governance.get('pending_approvals', 0)}",
        f"- Exclusion Rate: {governance.get('exclusion_rate', 0)}",
        f"- Maximum Exclusion Rate: {governance.get('maximum_exclusion_rate', 0)}",
        f"- Exclusion Cap Exceeded: {'Yes' if governance.get('exclusion_cap_exceeded') else 'No'}",
        "",
        "---",
        "",
        "## 8. Generated Reports",
        "",
    ]

    report_files = result.get("report_files", {})
    if isinstance(report_files, dict):
        lines.extend([
            f"- JSON Report path: {report_files.get('json', report_files.get('json_report', 'Not available'))}",
            f"- CSV Report path: {report_files.get('csv', report_files.get('csv_report', 'Not available'))}",
            f"- Excel Report path: {report_files.get('excel', report_files.get('excel_report', 'Not available'))}",
        ])
    else:
        lines.extend([
            f"- JSON Report path: {report_files}",
            f"- CSV Report path: {report_files}",
            f"- Excel Report path: {report_files}",
        ])

    return "\n".join(lines)


def _serialize_any(value: Any) -> Any:
    """Best-effort recursive serializer for pipeline state objects."""
    from dataclasses import asdict, is_dataclass
    from datetime import date, datetime, time

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return _serialize_any(asdict(value))
    if isinstance(value, dict):
        return {str(key): _serialize_any(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_any(item) for item in value]
    if hasattr(value, "__dict__"):
        return _serialize_any(vars(value))
    return str(value)




def _read_classification_report(
    csv_path: Path,
) -> dict[str, Any]:
    """
    Read and normalize the classification report once.
    """

    normalized_rows: list[
        dict[str, Any]
    ] = []

    classification_counts: dict[
        str,
        int,
    ] = {}

    with csv_path.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(
            file
        )

        if not reader.fieldnames:
            raise ValueError(
                "The classification CSV has no headers."
            )

        column_map = _resolve_columns(
            reader.fieldnames
        )

        test_id_column = column_map[
            "test_case_id"
        ]
        classification_column = (
            column_map[
                "classification"
            ]
        )
        test_name_column = column_map.get(
            "test_name"
        )
        module_id_column = column_map.get(
            "module_id"
        )
        score_column = column_map.get(
            "composite_score"
        )
        tier_column = column_map.get(
            "tier"
        )
        reasons_column = column_map.get(
            "reasons"
        )
        risk_band_column = column_map.get(
            "risk_band"
        )
        base_classification_column = column_map.get(
            "base_classification"
        )
        overridden_column = column_map.get(
            "classification_overridden"
        )
        protection_flags_column = column_map.get(
            "protection_flags"
        )
        change_factor_column = column_map.get(
            "change_impact_factor"
        )
        criticality_factor_column = column_map.get(
            "criticality_factor"
        )
        historical_score_column = column_map.get(
            "historical_value_score"
        )
        historical_factor_column = column_map.get(
            "historical_value_factor"
        )
        release_factor_column = column_map.get(
            "release_risk_factor"
        )

        for source_row in reader:
            test_case_id = str(
                source_row.get(
                    test_id_column,
                    "",
                )
                or ""
            ).strip()

            if not test_case_id:
                continue

            classification = (
                _normalize_classification(
                    source_row.get(
                        classification_column,
                        "",
                    )
                )
            )

            if not classification:
                classification = "UNKNOWN"

            normalized_row = {
                "test_case_id": (
                    test_case_id
                ),
                "test_name": _column_value(
                    source_row,
                    test_name_column,
                ),
                "module_id": _column_value(
                    source_row,
                    module_id_column,
                ),
                "tier": _normalize_tier(
                    _column_value(
                        source_row,
                        tier_column,
                    )
                ),
                "composite_score": (
                    _optional_float(
                        _column_value(
                            source_row,
                            score_column,
                        )
                    )
                ),
                "classification": (
                    classification
                ),
                "base_classification": _normalize_classification(
                    _column_value(
                        source_row,
                        base_classification_column,
                    )
                ),
                "classification_overridden": _column_value(
                    source_row,
                    overridden_column,
                ),
                "risk_band": _column_value(
                    source_row,
                    risk_band_column,
                ),
                "protection_flags": _column_value(
                    source_row,
                    protection_flags_column,
                ),
                "change_impact_factor": _optional_float(
                    _column_value(
                        source_row,
                        change_factor_column,
                    )
                ),
                "criticality_factor": _optional_float(
                    _column_value(
                        source_row,
                        criticality_factor_column,
                    )
                ),
                "historical_value_score": _optional_float(
                    _column_value(
                        source_row,
                        historical_score_column,
                    )
                ),
                "historical_value_factor": _optional_float(
                    _column_value(
                        source_row,
                        historical_factor_column,
                    )
                ),
                "release_risk_factor": _optional_float(
                    _column_value(
                        source_row,
                        release_factor_column,
                    )
                ),
                "reasons": _column_value(
                    source_row,
                    reasons_column,
                ),
            }

            normalized_rows.append(
                normalized_row
            )

            classification_counts[
                classification
            ] = (
                classification_counts.get(
                    classification,
                    0,
                )
                + 1
            )

    return {
        "rows": normalized_rows,
        "total_rows": len(
            normalized_rows
        ),
        "classification_counts": (
            classification_counts
        ),
    }


def _resolve_columns(
    headers: Iterable[str],
) -> dict[str, str]:
    normalized_headers = {
        _normalize_header(header): header
        for header in headers
        if header
    }

    test_id_column = _first_matching_column(
        normalized_headers,
        (
            "test_case_id",
            "test_id",
            "testcase_id",
            "tc_id",
        ),
    )

    classification_column = (
        _first_matching_column(
            normalized_headers,
            (
                "classification",
                "final_classification",
                "risk_classification",
                "decision",
                "recommendation",
            ),
        )
    )

    if not test_id_column:
        raise ValueError(
            "A test-case identifier column was not found. "
            f"Available columns: {list(headers)}"
        )

    if not classification_column:
        raise ValueError(
            "A classification column was not found. "
            f"Available columns: {list(headers)}"
        )

    return {
        "test_case_id": test_id_column,
        "classification": (
            classification_column
        ),
        "test_name": _first_matching_column(
            normalized_headers,
            (
                "test_name",
                "test_case_name",
                "testcase_name",
                "name",
            ),
        ),
        "module_id": _first_matching_column(
            normalized_headers,
            (
                "module_id",
                "module",
                "application_id",
            ),
        ),
        "tier": _first_matching_column(
            normalized_headers,
            (
                "tier",
                "application_tier",
                "criticality_tier",
            ),
        ),
        "composite_score": (
            _first_matching_column(
                normalized_headers,
                (
                    "composite_score",
                    "risk_score",
                    "score",
                ),
            )
        ),
        "reasons": _first_matching_column(
            normalized_headers,
            (
                "reasons",
                "reason",
                "explanation",
            ),
        ),
    }


def format_classification_cards(
    release_id: str,
    classification: str,
    test_cases: list[dict[str, Any]],
) -> str:
    """
    Format test cases as Markdown cards for ADK.
    """

    normalized_classification = (
        _normalize_classification(
            classification
        )
    )

    display_name = (
        normalized_classification.replace(
            "_",
            " ",
        ).title()
    )

    decision_icon = {
        "MUST_TEST": "🔴",
        "RECOMMENDED": "🟠",
        "OPTIONAL": "🟡",
        "EXCLUDE": "⚪",
        "EXCLUDE_CANDIDATE": "⚠️",
    }.get(
        normalized_classification,
        "•",
    )

    lines: list[str] = [
        f"## {display_name} Cases — {release_id}",
        "",
        f"**Total: {len(test_cases)} test cases**",
        "",
    ]

    if not test_cases:
        lines.append(
            f"No {display_name} cases were found."
        )

        return "\n".join(lines)

    for index, test_case in enumerate(
        test_cases,
        start=1,
    ):
        test_case_id = str(
            test_case.get(
                "test_case_id",
                "",
            )
        ).strip()

        test_name = str(
            test_case.get(
                "test_name",
                "",
            )
            or ""
        ).strip()

        module_id = str(
            test_case.get(
                "module_id",
                "",
            )
            or ""
        ).strip()

        tier = str(
            test_case.get(
                "tier",
                "",
            )
            or ""
        ).strip()

        composite_score = (
            test_case.get(
                "composite_score"
            )
        )

        lines.extend(
            [
                f"> ### {index}. `{test_case_id}`",
                ">",
                "> **Test:** "
                f"{test_name or 'Test name not available'}",
            ]
        )

        if module_id:
            lines.extend(
                [
                    ">",
                    f"> **Module:** `{module_id}`",
                ]
            )

        if tier:
            lines.extend(
                [
                    ">",
                    f"> **Tier:** `{tier}`",
                ]
            )

        if composite_score is not None:
            lines.extend(
                [
                    ">",
                    "> **Composite score:** "
                    f"`{composite_score:.2f}`",
                ]
            )

        lines.extend(
            [
                ">",
                f"> **Decision:** {decision_icon} "
                f"`{normalized_classification}`",
                "",
                "---",
                "",
            ]
        )

    return "\n".join(lines)


def format_classification_summary(
    release_id: str,
    summary: dict[str, Any],
) -> str:
    """Format classification totals as Markdown."""

    return "\n".join(
        [
            f"# Risk Tier Summary — {release_id}",
            "",
            "| Classification | Count |",
            "|---|---:|",
            "| MUST_TEST | "
            f"{summary.get('MUST_TEST', 0)} |",
            "| RECOMMENDED | "
            f"{summary.get('RECOMMENDED', 0)} |",
            "| OPTIONAL | "
            f"{summary.get('OPTIONAL', 0)} |",
            "| EXCLUDE | "
            f"{summary.get('EXCLUDE', 0)} |",
            "| **Total** | "
            f"**{summary.get('total_tests', 0)}** |",
            "",
            "> **Selected tests:** "
            f"{summary.get('selected_tests', 0)}",
            ">",
            "> **Selection percentage:** "
            f"{summary.get('selection_percentage', 0):.2f}%",
        ]
    )


def _classification_report_path(
    release_id: str,
) -> Path:
    """
    Construct and validate the classification CSV path.
    """

    output_root = (
        _output_directory().resolve()
    )

    report_path = (
        output_root
        / f"{release_id}_test_classifications.csv"
    ).resolve()

    if report_path.parent != output_root:
        raise ValueError(
            "Invalid classification report path."
        )

    return report_path


def _normalize_release_id(
    release_id: Any,
) -> str:
    normalized = str(
        release_id or ""
    ).strip()

    if not normalized:
        raise ValueError(
            "release_id cannot be empty."
        )

    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]*",
        normalized,
    ):
        raise ValueError(
            "release_id may contain only letters, "
            "numbers, periods, underscores and hyphens."
        )

    return normalized


def _normalize_classification(
    value: Any,
) -> str:
    return (
        str(value or "")
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )


def _normalize_tier(
    value: Any,
) -> str:
    normalized = (
        _normalize_classification(
            value
        )
    )

    return {
        "1": "TIER_1",
        "TIER1": "TIER_1",
        "TIER_1": "TIER_1",
        "2": "TIER_2",
        "TIER2": "TIER_2",
        "TIER_2": "TIER_2",
        "3": "TIER_3",
        "TIER3": "TIER_3",
        "TIER_3": "TIER_3",
        "4": "TIER_4",
        "TIER4": "TIER_4",
        "TIER_4": "TIER_4",
    }.get(
        normalized,
        normalized,
    )


def _normalize_header(
    value: Any,
) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def _first_matching_column(
    headers: dict[str, str],
    candidates: Iterable[str],
) -> str:
    for candidate in candidates:
        column = headers.get(
            candidate
        )

        if column:
            return column

    return ""


def _column_value(
    row: dict[str, Any],
    column: str | None,
) -> str:
    if not column:
        return ""

    return str(
        row.get(
            column,
            "",
        )
        or ""
    ).strip()


def _optional_float(
    value: Any,
) -> float | None:
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (
        TypeError,
        ValueError,
    ):
        return None


def _error_result(
    message: str,
    release_id: str,
    classification: str,
    response_key: str,
    report_path: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "error",
        "release_id": release_id,
        "classification": classification,
        "message": message,
        "count": 0,
        response_key: [],
    }

    if classification == "MUST_TEST":
        result["must_test_count"] = 0

    if report_path:
        result["report_path"] = (
            report_path
        )

    return result

def _resolve_jira_context(
    jira_link: str | None,
    release_id: str,
) -> tuple[Any, str, str]:
    """Create the same Jira-backed orchestrator context used by the pipeline."""
    settings = get_settings()
    normalized_release_id = _normalize_release_id(release_id).upper()
    normalized_link = str(jira_link or "").strip()
    if not normalized_link:
        normalized_link = _LAST_JIRA_CONTEXT.get("jira_link", "")
    if not normalized_release_id:
        normalized_release_id = _LAST_JIRA_CONTEXT.get("release_id", "").upper()

    orchestrator = RiskTierMasterOrchestrator.from_settings(
        settings=settings,
        jira_link=normalized_link or None,
    )

    if not orchestrator.jira_client:
        raise RuntimeError(
            "Jira is not available for this query. Provide the Jira link and ensure MCP/Jira credentials are configured."
        )

    return (
        orchestrator.jira_client,
        orchestrator.jira_project_key,
        normalized_release_id,
    )


def get_release_epics(
    release_id: str,
    jira_link: str | None = None,
) -> dict[str, Any]:
    """Return the epics in a Jira release with their key, name and summary."""
    try:
        client, project_key, normalized_release_id = _resolve_jira_context(
            jira_link,
            release_id,
        )

        jql = (
            f'project = "{project_key}" AND issuetype = "Epic" '
            f'AND labels = "{normalized_release_id}" ORDER BY key ASC'
        )
        issues = client.search(
            jql,
            ["summary", "description", "status", "labels", "parent"],
        )

        epics: list[dict[str, Any]] = []
        for issue in issues or []:
            fields = issue.get("fields", {}) or {}
            summary = str(fields.get("summary") or "").strip()
            status = str((fields.get("status") or {}).get("name") or "").strip()
            description = fields.get("description") or ""
            if isinstance(description, dict):
                description = _plain_jira_description(description)
            epics.append(
                {
                    "epic_key": str(issue.get("key") or "").strip(),
                    "summary": summary,
                    "status": status,
                    "description": str(description).strip(),
                }
            )

        lines = [
            f"## Epics — {normalized_release_id}",
            "",
            f"**Total: {len(epics)} epics**",
            "",
        ]
        if not epics:
            lines.append("No epics were found in Jira for this release.")
        else:
            for index, epic in enumerate(epics, start=1):
                lines.extend(
                    [
                        f"### {index}. `{epic['epic_key']}` — {epic['summary'] or 'Summary not available'}",
                        f"- Status: {epic['status'] or 'Not available'}",
                    ]
                )
                if epic["description"]:
                    lines.append(f"- Description: {epic['description']}")
                lines.append("")

        return {
            "status": "success",
            "release_id": normalized_release_id,
            "count": len(epics),
            "epics": epics,
            "markdown": "\n".join(lines).strip(),
        }

    except Exception as exc:
        return {
            "status": "error",
            "release_id": str(release_id or "").strip(),
            "error_type": type(exc).__name__,
            "message": str(exc),
        }


def get_release_hierarchy(
    release_id: str,
    jira_link: str | None = None,
    epic_key: str | None = None,
) -> dict[str, Any]:
    """Fetch the complete Epic -> Story -> Requirement -> Test hierarchy.

    This is a direct Jira tool for ADK follow-up questions. It deliberately
    does not delegate to a specialist agent that may not be registered in the
    current ADK runtime.
    """
    try:
        client, project_key, normalized_release_id = _resolve_jira_context(
            jira_link,
            release_id,
        )
        fields = [
            "summary", "description", "status", "issuetype", "parent",
            "labels", "issuelinks", "subtasks",
        ]
        issues = client.search(
            f'project = "{project_key}" AND labels = "{normalized_release_id}" ORDER BY key ASC',
            fields,
        )

        def issue_type(issue: dict[str, Any]) -> str:
            return str(((issue.get("fields") or {}).get("issuetype") or {}).get("name") or "").lower()

        def issue_parent(issue: dict[str, Any]) -> str:
            return str(((issue.get("fields") or {}).get("parent") or {}).get("key") or "").strip()

        def issue_row(issue: dict[str, Any]) -> dict[str, Any]:
            f = issue.get("fields") or {}
            return {
                "key": str(issue.get("key") or ""),
                "summary": str(f.get("summary") or ""),
                "issue_type": str((f.get("issuetype") or {}).get("name") or ""),
                "status": str((f.get("status") or {}).get("name") or ""),
                "parent_key": issue_parent(issue),
                "labels": f.get("labels") or [],
            }

        epics = [i for i in issues if "epic" in issue_type(i)]
        if epic_key:
            requested = str(epic_key).strip().upper()
            epics = [i for i in epics if str(i.get("key") or "").upper() == requested]

        epic_keys = {str(i.get("key") or "") for i in epics}
        stories = [i for i in issues if "story" in issue_type(i) or "task" in issue_type(i)]
        requirements = [i for i in issues if "requirement" in issue_type(i)]
        tests = [i for i in issues if "test" in issue_type(i)]

        def linked_to(issue: dict[str, Any], keys: set[str]) -> bool:
            f = issue.get("fields") or {}
            links = f.get("issuelinks") or []
            return any(
                str((link.get("outwardIssue") or link.get("inwardIssue") or {}).get("key") or "") in keys
                for link in links
            )

        hierarchy = []
        for epic in epics:
            ek = str(epic.get("key") or "")
            epic_stories = [s for s in stories if issue_parent(s) == ek or linked_to(s, {ek})]
            story_keys = {str(s.get("key") or "") for s in epic_stories}
            epic_requirements = [r for r in requirements if issue_parent(r) in story_keys or linked_to(r, story_keys)]
            req_keys = {str(r.get("key") or "") for r in epic_requirements}
            epic_tests = [t for t in tests if issue_parent(t) in story_keys | req_keys or linked_to(t, story_keys | req_keys)]
            hierarchy.append({
                "epic": issue_row(epic),
                "stories": [
                    {"story": issue_row(s), "requirements": [issue_row(r) for r in epic_requirements if issue_parent(r) == str(s.get("key") or "") or linked_to(r, {str(s.get("key") or "")})],
                     "tests": [issue_row(t) for t in epic_tests if issue_parent(t) == str(s.get("key") or "") or linked_to(t, {str(s.get("key") or "")})]}
                    for s in epic_stories
                ],
                "requirements": [issue_row(r) for r in epic_requirements if issue_parent(r) not in story_keys],
                "tests": [issue_row(t) for t in epic_tests if issue_parent(t) not in story_keys | req_keys],
            })
        return {"status": "success", "release_id": normalized_release_id, "count": len(hierarchy), "hierarchy": hierarchy}
    except Exception as exc:
        return {"status": "error", "release_id": str(release_id or ""), "error_type": type(exc).__name__, "message": str(exc)}


def search_jira(
    jql: str,
    fields: list[str] | None = None,
    jira_link: str | None = None,
    release_id: str | None = None,
) -> dict[str, Any]:
    """Run an arbitrary read-only Jira search for ADK questions.

    This is the reusable Jira retrieval tool. New customer questions should
    be answered by changing JQL/fields, not by adding another Python tool.
    """
    try:
        requested_release = str(release_id or _LAST_JIRA_CONTEXT.get("release_id", "")).strip()
        client, _project_key, _normalized_release = _resolve_jira_context(
            jira_link,
            requested_release,
        )
        normalized_jql = str(jql or "").strip()
        if not normalized_jql:
            raise ValueError("jql is required.")
        requested_fields = fields or [
            "summary", "description", "status", "issuetype", "parent",
            "labels", "issuelinks", "assignee", "priority",
        ]
        issues = client.search(normalized_jql, requested_fields)
        return {
            "status": "success",
            "jql": normalized_jql,
            "count": len(issues),
            "issues": issues,
        }
    except Exception as exc:
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }


def _plain_jira_description(value: Any) -> str:
    """Flatten Atlassian Document Format into readable text."""
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return str(value or "")

    chunks: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            text = node.get("text")
            if text:
                chunks.append(str(text))
            for child in node.get("content", []) or []:
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return " ".join(" ".join(chunks).split())


def explain_test_classification(
    release_id: str,
    test_case_id: str,
) -> dict[str, Any]:
    """Explain why one test received its final classification."""
    try:
        normalized_release_id = _normalize_release_id(release_id).upper()
        requested_id = str(test_case_id or "").strip().upper()
        if not requested_id:
            raise ValueError("test_case_id is required.")

        csv_path = _classification_report_path(normalized_release_id)
        if not csv_path.exists():
            raise ValueError(
                f"The classification report does not exist: {csv_path}. Run the complete Risk Tier pipeline first."
            )

        report = _read_classification_report(csv_path)
        matches = [
            row
            for row in report["rows"]
            if str(row.get("test_case_id") or "").strip().upper() == requested_id
        ]

        if not matches:
            return {
                "status": "error",
                "release_id": normalized_release_id,
                "test_case_id": requested_id,
                "message": f"Test case {requested_id} was not found in the classification report.",
            }

        row = matches[0]
        classification = row.get("classification", "")
        base_classification = row.get("base_classification", "")
        protection_flags = row.get("protection_flags", "")
        reasons = row.get("reasons", "")

        lines = [
            f"## Classification Explanation — {requested_id}",
            "",
            f"**Test:** {row.get('test_name') or 'Name not available'}",
            f"**Final classification:** `{classification}`",
            f"**Base classification:** `{base_classification or 'Not available'}`",
            f"**Composite score:** `{row.get('composite_score') if row.get('composite_score') is not None else 'Not available'}`",
            f"**Risk band:** `{row.get('risk_band') or 'Not available'}`",
            f"**Application tier:** `{row.get('tier') or 'Not available'}`",
            f"**Change impact factor:** `{row.get('change_impact_factor') if row.get('change_impact_factor') is not None else 'Not available'}`",
            f"**Criticality factor:** `{row.get('criticality_factor') if row.get('criticality_factor') is not None else 'Not available'}`",
            f"**Historical value score:** `{row.get('historical_value_score') if row.get('historical_value_score') is not None else 'Not available'}`",
            f"**Historical value factor:** `{row.get('historical_value_factor') if row.get('historical_value_factor') is not None else 'Not available'}`",
            f"**Release-risk factor:** `{row.get('release_risk_factor') if row.get('release_risk_factor') is not None else 'Not available'}`",
            "",
            "### Why",
        ]

        reason_items = _split_explanation_values(reasons)
        if reason_items:
            lines.extend(f"- {item}" for item in reason_items)
        else:
            lines.append("- No detailed reason text was stored in the classification report.")

        flags = _split_explanation_values(protection_flags)
        lines.extend(["", "### Protection flags"])
        if flags:
            lines.extend(f"- `{flag}` — {_explain_protection_flag(flag)}" for flag in flags)
        else:
            lines.append("- None")

        return {
            "status": "success",
            "release_id": normalized_release_id,
            "test_case_id": requested_id,
            "classification": classification,
            "base_classification": base_classification,
            "composite_score": row.get("composite_score"),
            "risk_band": row.get("risk_band"),
            "tier": row.get("tier"),
            "protection_flags": flags,
            "reasons": reason_items,
            "markdown": "\n".join(lines),
        }
    except Exception as exc:
        return {
            "status": "error",
            "release_id": str(release_id or "").strip(),
            "test_case_id": str(test_case_id or "").strip(),
            "error_type": type(exc).__name__,
            "message": str(exc),
        }


def _split_explanation_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            import ast
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except (ValueError, SyntaxError):
            pass
    return [item.strip() for item in text.split(";") if item.strip()]


def _explain_protection_flag(flag: str) -> str:
    explanations = {
        "REGULATORY_ALWAYS_EXECUTE": "The test is regulatory and must always execute.",
        "POLICY_MANDATORY": "Release policy marks the test as mandatory or always-execute.",
        "POLICY_EXCLUSION_PROHIBITED": "Policy explicitly prohibits excluding this test.",
        "NEW_FEATURE_PROTECTION": "The test covers a new or changed feature and is protected from exclusion.",
        "DEFECT_CATCH_PROTECTION": "The test previously caught a confirmed defect and is protected from exclusion.",
        "TIER_1_FLOOR": "The test inherits a Tier-1 module floor and is protected as high criticality.",
        "FLAKY_REMEDIATE_NOT_EXCLUDE": "Historical execution marks the test as flaky; it remains in the suite for remediation rather than being excluded.",
        "INSUFFICIENT_HISTORY_INCLUDE": "The test has insufficient execution history, so it cannot be excluded solely because history is missing.",
    }
    return explanations.get(flag, "This protection flag was supplied by the Risk Tier decision logic.")


def get_flaky_test_explanation(
    release_id: str,
    test_case_id: str | None = None,
    jira_link: str | None = None,
) -> dict[str, Any]:
    """Explain flaky-test status and the rule applied to the selected test(s)."""
    try:
        normalized_release_id = _normalize_release_id(release_id).upper()
        orchestrator = RiskTierMasterOrchestrator.from_settings(
            settings=get_settings(),
            jira_link=str(jira_link or "").strip() or None,
        )

        history_data = orchestrator._load_sheet_data(
            orchestrator.HISTORICAL_INPUT_BLOCKS
            if hasattr(orchestrator, "HISTORICAL_INPUT_BLOCKS")
            else ("test_cases", "executions", "defects", "flaky_tests")
        )

        # Use the same Historical Execution Agent calculation used by the pipeline.
        from app.agents.historical_agent.tools import analyze_historical_execution

        history = analyze_historical_execution(
            source_data=history_data,
            release_id=normalized_release_id,
        )
        payload = history.get("agent_output", history)
        summaries = payload.get("test_summaries", history.get("test_summaries", {}))
        requested_id = str(test_case_id or "").strip().upper()

        if requested_id:
            selected = summaries.get(requested_id)
            if selected is None:
                selected = summaries.get(str(test_case_id or "").strip())
            if selected is None:
                return {
                    "status": "error",
                    "release_id": normalized_release_id,
                    "test_case_id": requested_id,
                    "message": f"No historical summary was found for {requested_id}.",
                }
            flaky = bool(selected.get("flaky"))
            reason = (
                "Historical execution data flagged this test as flaky, so it is kept for remediation and not excluded solely for flakiness."
                if flaky
                else "This test is not currently flagged as flaky by the Historical Execution Agent."
            )
            return {
                "status": "success",
                "release_id": normalized_release_id,
                "test_case_id": requested_id,
                "flaky": flaky,
                "execution_count": selected.get("Execution_Count"),
                "passed_count": selected.get("Passed_Count"),
                "failed_count": selected.get("Failed_Count"),
                "pass_rate": selected.get("Pass_Rate"),
                "linked_defects": selected.get("linked_defect_ids", []),
                "markdown": "\n".join([
                    f"## Flaky Test Explanation — {requested_id}",
                    "",
                    f"**Flaky:** `{flaky}`",
                    "",
                    f"**Why:** {reason}",
                    "",
                    f"**Executions:** {selected.get('execution_count', 0)}",
                    f"**Passed:** {selected.get('passed_count', 0)}",
                    f"**Failed:** {selected.get('failed_count', 0)}",
                    f"**Pass rate:** {selected.get('pass_rate', 0)}",
                ]),
            }

        flaky_rows = [
            (tc_id, summary)
            for tc_id, summary in summaries.items()
            if bool(summary.get("flaky"))
        ]
        lines = [
            f"## Flaky Tests — {normalized_release_id}",
            "",
            f"**Total flaky tests: {len(flaky_rows)}**",
            "",
            "Flaky status comes from the Historical Execution Agent. Flaky tests remain visible for remediation and are not automatically excluded.",
            "",
        ]
        for tc_id, summary in sorted(flaky_rows):
            lines.append(
                f"- `{tc_id}` — {summary.get('Execution_Count', 0)} executions, {summary.get('Failed_Count', 0)} failures, pass rate {summary.get('Pass_Rate', 0)}"
            )

        return {
            "status": "success",
            "release_id": normalized_release_id,
            "count": len(flaky_rows),
            "flaky_tests": [
                {"test_case_id": tc_id, **summary}
                for tc_id, summary in flaky_rows
            ],
            "markdown": "\n".join(lines),
        }
    except Exception as exc:
        return {
            "status": "error",
            "release_id": str(release_id or "").strip(),
            "test_case_id": str(test_case_id or "").strip(),
            "error_type": type(exc).__name__,
            "message": str(exc),
        }


def get_pipeline_cache(
    release_id: str,
    agent: str,
) -> dict[str, Any]:
    """
    Retrieve completed Risk Tier pipeline data for a specialist.
    Never re-runs Jira or the pipeline.
    """
    orchestrator = RiskTierMasterOrchestrator.for_query()

    return orchestrator.get_cached_agent_context(
        release_id=release_id,
        agent=agent,
    )


def _cached_agent_context(
    release_id: str,
    agent: str,
    question: str = "",
) -> dict[str, Any]:
    """
    Shared helper for the release-level drill-down tools below.

    Reads the already-completed pipeline's cached state only — it never
    re-fetches Jira and never reruns the pipeline. Run
    execute_risk_tier_pipeline (or stage_pipeline_run) for this release
    first; otherwise this returns a status="error" result.
    """
    normalized_release_id = str(release_id or "").strip().upper()

    try:
        orchestrator = RiskTierMasterOrchestrator.for_query()

        return orchestrator.get_cached_agent_context(
            release_id=normalized_release_id,
            agent=agent,
            question=question,
        )
    except Exception as exc:
        return {
            "status": "error",
            "release_id": normalized_release_id,
            "agent": agent,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }


def get_change_impact(release_id: str) -> dict[str, Any]:
    """
    Return the cached Feature/Epic Change Impact analysis for a release:
    direct and downstream impacted tests, new-feature protection, and
    traceability gaps. Requires the pipeline to have already run.
    """
    return _cached_agent_context(
        release_id,
        agent="feature",
        question="change impact",
    )


def get_application_criticality(release_id: str) -> dict[str, Any]:
    """
    Return the cached Application Criticality analysis for a release:
    module tier assignments, per-test tier tags, and protected tests.
    """
    return _cached_agent_context(
        release_id,
        agent="criticality",
        question="criticality tier",
    )


def get_historical_intelligence(release_id: str) -> dict[str, Any]:
    """
    Return the cached Historical Execution Intelligence analysis for a
    release: flaky tests, defect-protected tests, and tests with
    insufficient execution history.
    """
    return _cached_agent_context(
        release_id,
        agent="history",
        question="historical execution flaky defect",
    )


def get_policy(release_id: str) -> dict[str, Any]:
    """
    Return the cached Policy / Risk Appetite analysis for a release:
    mandatory and regulatory tests, exclusion caps, and approval rules.
    """
    return _cached_agent_context(
        release_id,
        agent="policy",
        question="policy mandatory regulatory",
    )


def get_scoring(release_id: str) -> dict[str, Any]:
    """
    Return the cached Decision Engine / Risk Scoring analysis for a
    release: per-test composite scores, risk bands, and classifications.
    """
    return _cached_agent_context(
        release_id,
        agent="scoring",
        question="scoring classification",
    )


def get_governance(release_id: str) -> dict[str, Any]:
    """
    Return the cached Exclusion Risk / Governance analysis for a release:
    exclusion candidates, approvals, pending approvals, and exclusion cap.
    """
    return _cached_agent_context(
        release_id,
        agent="governance",
        question="governance exclusion approval",
    )


def get_release_traceability(release_id: str) -> dict[str, Any]:
    """
    Return the cached Epic -> Story -> Requirement -> Test traceability
    for a release, including any traceability gaps.
    """
    return _cached_agent_context(
        release_id,
        agent="feature",
        question="traceability rtm mapping",
    )


def explain_test_decision(
    release_id: str,
    test_case_id: str,
) -> dict[str, Any]:
    """
    Explain why one test received its final classification. Alias for
    explain_test_classification, kept under this name for compatibility
    with the previous MCP-based tool set.
    """
    return explain_test_classification(release_id, test_case_id)


def _jira_client_and_project(
    jira_link: str | None = None,
) -> tuple[Any, str]:
    """
    Resolve a Jira-backed MCPJiraClient without requiring a release id.

    Used by the Jira write tools below, which act on a single issue and
    are not scoped to a release the way the read/query tools above are.
    """
    settings = get_settings()
    normalized_link = (
        str(jira_link or "").strip()
        or _LAST_JIRA_CONTEXT.get("jira_link", "")
    )

    orchestrator = RiskTierMasterOrchestrator.from_settings(
        settings=settings,
        jira_link=normalized_link or None,
    )

    if not orchestrator.jira_client:
        raise RuntimeError(
            "Jira is not available. Provide the Jira link and ensure "
            "MCP/Jira credentials are configured."
        )

    return orchestrator.jira_client, orchestrator.jira_project_key


def create_jira_issue(
    summary: str,
    description: str = "",
    issue_type: str = "Task",
    project_key: str | None = None,
    jira_link: str | None = None,
) -> dict[str, Any]:
    """Create a new Jira issue in the configured (or given) project."""
    try:
        client, resolved_project_key = _jira_client_and_project(jira_link)

        result = client.create_issue(
            project_key=str(project_key or resolved_project_key or "").strip(),
            summary=summary,
            description=description,
            issue_type=issue_type,
        )

        return {"status": "success", **result}
    except Exception as exc:
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }


def add_jira_comment(
    issue_key: str,
    comment: str,
    jira_link: str | None = None,
) -> dict[str, Any]:
    """Add a comment to an existing Jira issue."""
    try:
        client, _project_key = _jira_client_and_project(jira_link)

        result = client.add_comment(
            issue_key=issue_key,
            comment=comment,
        )

        return {"status": "success", **result}
    except Exception as exc:
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }


def update_jira_issue(
    issue_key: str,
    summary: str | None = None,
    description: str | None = None,
    priority: str | None = None,
    jira_link: str | None = None,
) -> dict[str, Any]:
    """Update summary, description, and/or priority on a Jira issue."""
    try:
        client, _project_key = _jira_client_and_project(jira_link)

        result = client.update_issue(
            issue_key=issue_key,
            summary=summary,
            description=description,
            priority=priority,
        )

        return {"status": "success", **result}
    except Exception as exc:
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }


def delete_jira_issue(
    issue_key: str,
    confirm: bool = False,
    jira_link: str | None = None,
) -> dict[str, Any]:
    """
    Permanently delete a Jira issue. Requires confirm=true; otherwise
    returns confirmation_required without deleting anything. This is a
    destructive, irreversible action against shared Jira state — only
    call it after the user has explicitly confirmed the deletion.
    """
    try:
        client, _project_key = _jira_client_and_project(jira_link)

        result = client.delete_issue(
            issue_key=issue_key,
            confirm=confirm,
        )

        return {"status": result.get("status", "success"), **result}
    except Exception as exc:
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }


# ============================================================
# ADK ROOT AGENT TOOL REGISTRY
# ============================================================

RISK_TIER_ROOT_TOOLS = [
    get_release_epics,
    get_release_hierarchy,
    search_jira,
    get_must_test_cards,
    get_must_test_cases,
    get_test_cases_by_classification,
    get_classification_cards,
    get_classification_summary,
    format_classification_summary,
    explain_test_classification,
    explain_test_decision,
    get_flaky_test_explanation,
    get_change_impact,
    get_application_criticality,
    get_historical_intelligence,
    get_policy,
    get_scoring,
    get_governance,
    get_release_traceability,
    create_jira_issue,
    add_jira_comment,
    update_jira_issue,
    delete_jira_issue,
]