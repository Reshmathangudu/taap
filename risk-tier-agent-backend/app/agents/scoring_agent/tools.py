# #old_scoring_agent/tools.py
# from __future__ import annotations

# from typing import Any
# from app.observability.logger import (
#     log_event,
#     trace_error,
# )

# from app.observability.audit import audit_event

# from app.models import A2ARequest, A2AResponse
# from app.services.a2a import make_response, validate_message

# from app.utils.helpers import is_yes, tier_factor


# DEFAULT_WEIGHTS: dict[str, float] = {
#     "CHANGE_IMPACT": 0.40,
#     "CRITICALITY": 0.30,
#     "HISTORICAL_VALUE": 0.20,
#     "RELEASE_RISK": 0.10,
# }


# DEFAULT_THRESHOLDS: dict[str, float] = {
#     "MUST_TEST": 80.0,
#     "RECOMMENDED": 60.0,
#     "OPTIONAL": 40.0,
#     "EXCLUDE": 0.0,
# }


# RELEASE_RISK_FACTORS: dict[str, float] = {
#     "MAJOR": 0.80,
#     "MINOR": 0.60,
#     "PATCH": 0.40,
#     "HOTFIX": 0.70,
#     "EMERGENCY": 1.00,
# }


# HARD_PROTECTIONS = {
#     "REGULATORY_ALWAYS_EXECUTE",
#     "POLICY_MANDATORY",
#     "POLICY_EXCLUSION_PROHIBITED",
#     "NEW_FEATURE_PROTECTION",
#     "DEFECT_CATCH_PROTECTION",
#     "TIER_1_FLOOR",
#     # MAJOR release posture: Tier-1/Tier-2 modules remain in the regression floor.
#     "MAJOR_RELEASE_TIER12_FLOOR",
#     # BR-HIST-05: insufficient history defaults to inclusion / MUST_TEST.
#     "INSUFFICIENT_HISTORY_INCLUDE",
# }


# SOFT_PROTECTIONS = {
#     # BR-HIST-03: flaky tests route to remediation and cannot justify exclusion.
#     "FLAKY_REMEDIATE_NOT_EXCLUDE",
# }


# REQUIRED_INPUT_KEYS: tuple[str, ...] = (
#     "test_cases",
# )

# OPTIONAL_INPUT_KEYS: tuple[str, ...] = (
#     "scoring_weights",
#     "thresholds",
# )


# def calculate_test_selection(
#     source_data: dict[
#         str,
#         list[dict[str, Any]],
#     ],
#     change_impact: dict[str, Any],
#     criticality: dict[str, Any],
#     history: dict[str, Any],
#     policy: dict[str, Any],
# ) -> dict[str, Any]:
#     log_event(
#     "SCORING_STARTED",
#     agent="Decision Engine / Risk Scoring Agent",
#     stage="SCORING",
#     status="STARTED",
#     )
#     """
#     Calculate scores and final test classifications.

#     The Master Orchestrator must provide all raw input rows through
#     ``source_data`` and the structured outputs from the preceding agents.
#     This agent does not open or read the Excel workbook.

#     Required source_data keys:
#     - test_cases

#     Optional source_data keys:
#     - scoring_weights
#     - thresholds

#     When optional configuration is absent, the documented internal defaults
#     are used. The Master Orchestrator normally supplies these blocks explicitly.

#     Agent inputs:
#     - Feature / Epic Change Impact output
#     - Application Criticality output
#     - Historical Execution Intelligence output
#     - Policy / Risk Appetite output

#     Generated outputs:
#     - Per-test scoring result
#     - Classification summary
#     - Compact agent-to-agent payload
#     - Markdown dashboard

#     This function does not read:
#     - A5_Test_Scoring
#     """

#     _validate_orchestrator_inputs(
#         source_data=source_data,
#         change_impact=change_impact,
#         criticality=criticality,
#         history=history,
#         policy=policy,
#     )

#     test_case_rows = source_data["test_cases"]
#     log_event(
#     "SCORING_INPUTS_LOADED",
#     agent="Decision Engine / Risk Scoring Agent",
#     stage="SCORING",
#     status="SUCCESS",
#     test_cases=len(test_case_rows),
#     )


#     scoring_weight_rows = source_data.get("scoring_weights", [])
#     threshold_rows = source_data.get("thresholds", [])

#     weights = (
#         _load_weights(scoring_weight_rows)
#         if scoring_weight_rows
#         else DEFAULT_WEIGHTS.copy()
#     )
#     thresholds = (
#         _load_thresholds(threshold_rows)
#         if threshold_rows
#         else DEFAULT_THRESHOLDS.copy()
#     )

#     # Test Status is a business field. Jira workflow Status (e.g. "To Do")
#     # must never override it.
#     active_tests = [
#         row
#         for row in test_case_rows
#         if _normalized(
#             _first_non_empty(
#                 _value(
#                     row,
#                     "Test_Status",
#                     "Test Status",
#                     "TestStatus",
#                 ),
#                 "ACTIVE",
#             )
#         )
#         in {
#             "ACTIVE",
#             "ENABLED",
#             "CURRENT",
#             "APPROVED",
#         }
#     ]
#     log_event(
#     "ACTIVE_TESTS_FILTERED",
#     agent="Decision Engine / Risk Scoring Agent",
#     stage="SCORING",
#     active_tests=len(active_tests),
#     )


#     # ---------------------------------------------------------
#     # Read compact or full Feature Agent output
#     # ---------------------------------------------------------
#     change_payload = change_impact.get(
#         "agent_output",
#         change_impact,
#     )

#     direct_test_ids = _string_set(
#         change_payload.get(
#             "direct_test_ids",
#             change_impact.get(
#                 "direct_test_ids",
#                 [],
#             ),
#         )
#     )

#     downstream_test_ids = _string_set(
#         change_payload.get(
#             "downstream_test_ids",
#             change_impact.get(
#                 "downstream_test_ids",
#                 [],
#             ),
#         )
#     )

#     new_feature_test_ids = _string_set(
#         change_payload.get(
#             "new_feature_test_ids",
#             change_impact.get(
#                 "new_feature_test_ids",
#                 [],
#             ),
#         )
#     )

#     # ---------------------------------------------------------
#     # Read compact or full Criticality Agent output
#     # ---------------------------------------------------------
#     criticality_payload = criticality.get(
#         "agent_output",
#         criticality,
#     )

#     test_tags = criticality_payload.get(
#         "test_tags",
#         criticality.get(
#             "test_tags",
#             {},
#         ),
#     )

#     # ---------------------------------------------------------
#     # Read compact or full Historical Agent output
#     # ---------------------------------------------------------
#     history_payload = history.get(
#         "agent_output",
#         history,
#     )

#     historical_summaries = history_payload.get(
#         "test_summaries",
#         history.get(
#             "test_summaries",
#             {},
#         ),
#     )

#     # ---------------------------------------------------------
#     # Read compact or full Policy Agent output
#     # ---------------------------------------------------------
#     policy_payload = policy.get(
#         "agent_output",
#         policy,
#     )

#     release_type = _normalized(
#         _first_non_empty(
#             policy_payload.get(
#                 "release_type"
#             ),
#             policy.get(
#                 "release_type"
#             ),
#             "UNKNOWN",
#         )
#     )

#     release_factor = RELEASE_RISK_FACTORS.get(
#         release_type,
#         0.60,
#     )

#     regulatory_test_ids = _string_set(
#         _first_non_empty(
#             policy_payload.get(
#                 "regulatory_test_ids"
#             ),
#             list(
#                 policy.get(
#                     "regulatory_tests",
#                     {},
#                 ).keys()
#             ),
#             [],
#         )
#     )

#     mandatory_test_ids = _string_set(
#         _first_non_empty(
#             policy_payload.get(
#                 "mandatory_test_ids"
#             ),
#             policy.get(
#                 "mandatory_test_ids"
#             ),
#             [],
#         )
#     )

#     always_execute_test_ids = _string_set(
#         _first_non_empty(
#             policy_payload.get(
#                 "always_execute_test_ids"
#             ),
#             policy.get(
#                 "always_execute_test_ids"
#             ),
#             [],
#         )
#     )

#     exclusion_prohibited_test_ids = _string_set(
#         _first_non_empty(
#             policy_payload.get(
#                 "exclusion_prohibited_test_ids"
#             ),
#             policy.get(
#                 "exclusion_prohibited_test_ids"
#             ),
#             [],
#         )
#     )

#     test_policy_decisions = (
#         policy_payload.get(
#             "test_policy_decisions"
#         )
#         or policy.get(
#             "test_policy_decisions"
#         )
#         or {}
#     )

#     results: list[dict[str, Any]] = []

#     # ---------------------------------------------------------
#     # Score every active test
#     # ---------------------------------------------------------
#     for test_case in active_tests:
#         test_case_id_value = _value(
#             test_case,
#             "Test_Case_ID",
#             "Test Case ID",
#             "TestCase_ID",
#             "Test_ID",
#             "TC_ID",
#         )

#         if not test_case_id_value:
#             continue

#         test_case_id = str(
#             test_case_id_value
#         ).strip()

#         test_name = _value(
#             test_case,
#             "Test_Name",
#             "Test Name",
#             "Test_Case_Name",
#             "Name",
#             "Description",
#         )

#         module_id = _value(
#             test_case,
#             "Module_ID",
#             "Module ID",
#             "ModuleId",
#         )

#         tag = test_tags.get(
#             test_case_id,
#             {
#                 "tier": "TIER_3",
#                 "tier_floor_protection": False,
#                 "criticality_score": 2.50,
#                 "minimum_coverage": 0.50,
#             },
#         )

#         historical = historical_summaries.get(
#             test_case_id,
#             {},
#         )

#         test_policy = test_policy_decisions.get(
#             test_case_id,
#             {},
#         )

#         change_factor = _change_impact_factor(
#             test_case_id=test_case_id,
#             direct_test_ids=direct_test_ids,
#             downstream_test_ids=(
#                 downstream_test_ids
#             ),
#         )

#         tier = _normalize_tier(
#             tag.get(
#                 "tier",
#                 "TIER_3",
#             )
#         )

#         criticality_factor = tier_factor(
#             tier
#         )

#         historical_value_score = _to_float(
#             historical.get(
#                 "Historical_Value_Score",
#                 0,
#             ),
#             default=0.0,
#         )

#         historical_factor = min(
#             max(
#                 historical_value_score
#                 / 100.0,
#                 0.0,
#             ),
#             1.0,
#         )

#         weighted_components = {
#             "CHANGE_IMPACT": (
#                 weights.get(
#                     "CHANGE_IMPACT",
#                     0.40,
#                 )
#                 * change_factor
#             ),
#             "CRITICALITY": (
#                 weights.get(
#                     "CRITICALITY",
#                     0.30,
#                 )
#                 * criticality_factor
#             ),
#             "HISTORICAL_VALUE": (
#                 weights.get(
#                     "HISTORICAL_VALUE",
#                     0.20,
#                 )
#                 * historical_factor
#             ),
#             "RELEASE_RISK": (
#                 weights.get(
#                     "RELEASE_RISK",
#                     0.10,
#                 )
#                 * release_factor
#             ),
#         }

#         composite_score = 100.0 * sum(
#             weighted_components.values()
#         )

#         protection_flags = _protection_flags(
#             test_case_id=test_case_id,
#             tier=tier,
#             release_type=release_type,
#             tag=tag,
#             historical=historical,
#             test_policy=test_policy,
#             regulatory_test_ids=(
#                 regulatory_test_ids
#             ),
#             mandatory_test_ids=(
#                 mandatory_test_ids
#             ),
#             always_execute_test_ids=(
#                 always_execute_test_ids
#             ),
#             exclusion_prohibited_test_ids=(
#                 exclusion_prohibited_test_ids
#             ),
#             new_feature_test_ids=(
#                 new_feature_test_ids
#             ),
#             direct_test_ids=direct_test_ids,
#         )

#         base_classification = (
#             _classification_from_score(
#                 score=composite_score,
#                 thresholds=thresholds,
#             )
#         )

#         final_classification = (
#             _apply_protection_rules(
#                 base_classification=(
#                     base_classification
#                 ),
#                 protection_flags=(
#                     protection_flags
#                 ),
#             )
#         )

#         risk_band = _risk_band(
#             composite_score
#         )

#         # BR-HIST-02: historical consistency is only a final exclusion
#         # candidate when the test also inherits Tier 3 or Tier 4 criticality.
#         # This is a candidate signal, not an automatic EXCLUDE decision.
#         consistent_pass_zero_defect_candidate = (
#             is_yes(historical.get("consistent_pass_zero_defect_eligible"))
#             and tier in {"TIER_3", "TIER_4"}
#         )

#         reasons = _build_reasons(
#             test_case_id=test_case_id,
#             tier=tier,
#             change_factor=change_factor,
#             historical_value_score=(
#                 historical_value_score
#             ),
#             release_type=release_type,
#             release_factor=release_factor,
#             base_classification=(
#                 base_classification
#             ),
#             final_classification=(
#                 final_classification
#             ),
#             protection_flags=(
#                 protection_flags
#             ),
#             direct_test_ids=(
#                 direct_test_ids
#             ),
#             downstream_test_ids=(
#                 downstream_test_ids
#             ),
#         )

#         execution_minutes = _to_float(
#             _value(
#                 test_case,
#                 "Execution_Minutes",
#                 "Execution Minutes",
#                 "Duration_Minutes",
#                 "Duration",
#             ),
#             default=0.0,
#         )

#         results.append(
#             {
#                 "test_case_id": test_case_id,
#                 "test_name": test_name,
#                 "module_id": module_id,
#                 "tier": tier,
#                 "criticality_score": _to_float(
#                     tag.get(
#                         "criticality_score",
#                         0,
#                     )
#                 ),
#                 "change_impact_factor": round(
#                     change_factor,
#                     4,
#                 ),
#                 "criticality_factor": round(
#                     criticality_factor,
#                     4,
#                 ),
#                 "historical_value_score": round(
#                     historical_value_score,
#                     2,
#                 ),
#                 "historical_value_factor": round(
#                     historical_factor,
#                     4,
#                 ),
#                 "release_type": release_type,
#                 "release_risk_factor": round(
#                     release_factor,
#                     4,
#                 ),
#                 "score_components": {
#                     factor: round(
#                         contribution * 100,
#                         2,
#                     )
#                     for factor, contribution
#                     in weighted_components.items()
#                 },
#                 "composite_score": round(
#                     composite_score,
#                     2,
#                 ),
#                 "risk_band": risk_band,
#                 "protection_flags": sorted(
#                     protection_flags
#                 ),
#                 "base_classification": (
#                     base_classification
#                 ),
#                 "classification": (
#                     final_classification
#                 ),
#                 "consistent_pass_zero_defect_candidate": (
#                     consistent_pass_zero_defect_candidate
#                 ),
#                 "classification_overridden": (
#                     base_classification
#                     != final_classification
#                 ),
#                 "execution_minutes": (
#                     execution_minutes
#                 ),
#                 "reasons": reasons,
#             }
#         )

#     results.sort(
#         key=lambda row: (
#             _classification_order(row["classification"]),
#             -row["composite_score"],
#             row["test_case_id"],
#         )
#     )
#     log_event(
#     "BR_SEL_01_APPLIED",
#     agent="Decision Engine / Risk Scoring Agent",
#     rule_id="BR-SEL-01",
#     scored_tests=len(results),
#     )

#     # A2A-safe business rule enforcement happens inside the specialist after it
#     # has consumed the orchestrator-supplied Criticality output.
#     _enforce_criticality_coverage_floors(results, criticality)
#     log_event(
#     "BR_CRIT_03_APPLIED",
#     agent="Decision Engine / Risk Scoring Agent",
#     rule_id="BR-CRIT-03",
#     )  

#     results.sort(
#         key=lambda row: (
#             _classification_order(row["classification"]),
#             -row["composite_score"],
#             row["test_case_id"],
#         )
#     )

#     summary = _build_summary(
#         results
#     )
#     log_event(
#     "TEST_CLASSIFICATION_COMPLETED",
#     agent="Decision Engine / Risk Scoring Agent",
#     must_test=summary.get("MUST_TEST", 0),
#     recommended=summary.get("RECOMMENDED", 0),
#     optional=summary.get("OPTIONAL", 0),
#     exclude=summary.get("EXCLUDE", 0),
#     )
#     log_event(
#         "BR_SEL_02_APPLIED",
#         agent="Decision Engine / Risk Scoring Agent",
#         rule_id="BR-SEL-02",
#         protection_overrides=summary.get(
#             "protection_overrides",
#             0,
#         ),
#     )

#     classification_groups = {
#         classification: [
#             row["test_case_id"]
#             for row in results
#             if row["classification"]
#             == classification
#         ]
#         for classification in (
#             "MUST_TEST",
#             "RECOMMENDED",
#             "OPTIONAL",
#             "EXCLUDE",
#         )
#     }

#     result: dict[str, Any] = {
#         "weights": weights,
#         "thresholds": thresholds,
#         "release_type": release_type,
#         "release_risk_factor": (
#             release_factor
#         ),
#         "results": results,
#         "classification_groups": (
#             classification_groups
#         ),
#         "business_rules": {
#             "BR-SEL-01": "Weighted composite risk score combines change impact, criticality, historical value, and release risk.",
#             "BR-SEL-02": "Any non-negotiable protection signal forces MUST_TEST using OR logic.",
#             "BR-SEL-03": "Unchanged Tier 3/4 tests with reliable low-value history are candidates for Optional/Exclude.",
#             "BR-SEL-04": "Partial-change selection uses only the directly scoped sub-flow change impact.",
#             "BR-SEL-05": "Every classification carries factor-level rationale.",
#             "BR-CRIT-03": "Tier 1 = 100% coverage; Tier 2 >= 70% coverage.",
#             "GR-SEL-02": "Major/regulated releases require QA Lead sign-off before the recommended suite is finalized.",
#         },
#         "suite_finalization": (
#             "QA_LEAD_SIGNOFF_REQUIRED" if release_type in {"MAJOR", "REGULATED"} else "AUTO_FINALIZE_WITHIN_APPROVED_CAP"
#         ),
#         "summary": summary,

#         # Compact payload consumed by Governance.
#         "agent_output": {
#             "release_type": release_type,
#             "weights": weights,
#             "thresholds": thresholds,
#             "results": results,
#             "classification_groups": (
#                 classification_groups
#             ),
#             "summary": summary,
#             "suite_finalization": (
#                 "QA_LEAD_SIGNOFF_REQUIRED" if release_type in {"MAJOR", "REGULATED"} else "AUTO_FINALIZE_WITHIN_APPROVED_CAP"
#             ),
#             "governance_candidates": [
#                 {
#                     "test_case_id": (
#                         row["test_case_id"]
#                     ),
#                     "test_name": (
#                         row["test_name"]
#                     ),
#                     "module_id": (
#                         row["module_id"]
#                     ),
#                     "tier": row["tier"],
#                     "composite_score": (
#                         row[
#                             "composite_score"
#                         ]
#                     ),
#                     "classification": (
#                         row[
#                             "classification"
#                         ]
#                     ),
#                     "protection_flags": (
#                         row[
#                             "protection_flags"
#                         ]
#                     ),
#                     "reasons": row["reasons"],
#                 }
#                 for row in results
#                 if row["classification"]
#                 == "EXCLUDE"
#             ],
#         },
#     }

#     log_event(
#     "SCORING_COMPLETED",
#     agent="Decision Engine / Risk Scoring Agent",
#     stage="SCORING",
#     status="SUCCESS",
#     total_tests=len(results),
#     )

#     audit_event(
#         "SCORING_COMPLETED",
#         agent="Decision Engine / Risk Scoring Agent",
#         message=(
#             f"Scored {len(results)} test cases."
#         ),
#         details={
#             "must_test": summary.get("MUST_TEST", 0),
#             "recommended": summary.get("RECOMMENDED", 0),
#             "optional": summary.get("OPTIONAL", 0),
#             "exclude": summary.get("EXCLUDE", 0),
#             "execution_reduction_percentage": summary.get(
#                 "execution_reduction_percentage",
#                 0,
#             ),
#         },
#     )


#     result["markdown"] = (
#         format_scoring_dashboard(result)
#     )

#     return result



# def _validate_orchestrator_inputs(
#     source_data: dict[
#         str,
#         list[dict[str, Any]],
#     ],
#     change_impact: dict[str, Any],
#     criticality: dict[str, Any],
#     history: dict[str, Any],
#     policy: dict[str, Any],
# ) -> None:
#     """
#     Validate raw input rows and upstream agent outputs supplied by the
#     Master Orchestrator.
#     """

#     if not isinstance(
#         source_data,
#         dict,
#     ):
#         raise TypeError(
#             "source_data must be a dictionary "
#             "provided by the Master Orchestrator."
#         )

#     missing_inputs = [
#         input_name
#         for input_name in REQUIRED_INPUT_KEYS
#         if input_name not in source_data
#     ]

#     if missing_inputs:
#         raise ValueError(
#             "Scoring Agent is missing required "
#             "orchestrator inputs: "
#             f"{missing_inputs}"
#         )

#     invalid_inputs = [
#         input_name
#         for input_name in REQUIRED_INPUT_KEYS
#         if not isinstance(source_data[input_name], list)
#     ]

#     invalid_optional_inputs = [
#         input_name
#         for input_name in OPTIONAL_INPUT_KEYS
#         if input_name in source_data and not isinstance(source_data[input_name], list)
#     ]

#     if invalid_inputs:
#         raise TypeError(
#             "Scoring Agent expected required input rows as lists for: "
#             f"{invalid_inputs}"
#         )

#     if invalid_optional_inputs:
#         raise TypeError(
#             "Scoring Agent expected optional configuration blocks as lists for: "
#             f"{invalid_optional_inputs}"
#         )

#     upstream_inputs = {
#         "change_impact": change_impact,
#         "criticality": criticality,
#         "history": history,
#         "policy": policy,
#     }

#     invalid_inputs = [
#         name
#         for name, value
#         in upstream_inputs.items()
#         if not isinstance(
#             value,
#             dict,
#         )
#     ]

#     if invalid_inputs:
#         raise TypeError(
#             "Scoring Agent expected structured "
#             "dictionary outputs from the Master "
#             "Orchestrator for: "
#             f"{invalid_inputs}"
#         )

# def _protection_flags(
#     test_case_id: str,
#     tier: str,
#     release_type: str,
#     tag: dict[str, Any],
#     historical: dict[str, Any],
#     test_policy: dict[str, Any],
#     regulatory_test_ids: set[str],
#     mandatory_test_ids: set[str],
#     always_execute_test_ids: set[str],
#     exclusion_prohibited_test_ids: set[str],
#     new_feature_test_ids: set[str],
#     direct_test_ids: set[str],
# ) -> set[str]:
#     """
#     Build protection flags using explicit yes/true conversion.

#     Using bool(value) is unsafe for Excel-derived strings because
#     bool("NO") and bool("FALSE") are both True.
#     """

#     flags: set[str] = set()

#     if test_case_id in regulatory_test_ids:
#         flags.add(
#             "REGULATORY_ALWAYS_EXECUTE"
#         )

#     if (
#         test_case_id in mandatory_test_ids
#         or test_case_id
#         in always_execute_test_ids
#         or is_yes(
#             test_policy.get(
#                 "mandatory"
#             )
#         )
#         or is_yes(
#             test_policy.get(
#                 "always_execute"
#             )
#         )
#     ):
#         flags.add(
#             "POLICY_MANDATORY"
#         )

#     if (
#         test_case_id
#         in exclusion_prohibited_test_ids
#         or is_yes(
#             test_policy.get(
#                 "exclusion_prohibited"
#             )
#         )
#     ):
#         flags.add(
#             "POLICY_EXCLUSION_PROHIBITED"
#         )

#     if test_case_id in new_feature_test_ids:
#         flags.add(
#             "NEW_FEATURE_PROTECTION"
#         )

#     # Major releases require a regression floor for Tier-1 and Tier-2 modules.
#     # This is a release-posture safeguard, not a numeric score adjustment.
#     if release_type == "MAJOR" and tier in {"TIER_1", "TIER_2"}:
#         flags.add(
#             "MAJOR_RELEASE_TIER12_FLOOR"
#         )

#     # BR-HIST-01: active defect-catch protection must block score-only
#     # exclusion. Accept the explicit boolean flag and the protected-defect
#     # ID list as equivalent signals so downstream protection remains robust
#     # even when a compact history payload omits one representation.
#     if (
#         is_yes(historical.get("defect_catch_protection"))
#         or bool(_string_set(historical.get("protected_defect_ids", [])))
#     ):
#         flags.add(
#             "DEFECT_CATCH_PROTECTION"
#         )

#     if is_yes(
#         tag.get(
#             "tier_floor_protection"
#         )
#     ):
#         flags.add(
#             "TIER_1_FLOOR"
#         )

#     if is_yes(
#         historical.get(
#             "insufficient_history"
#         )
#     ):
#         flags.add(
#             "INSUFFICIENT_HISTORY_INCLUDE"
#         )

#     if (
#         is_yes(
#             historical.get(
#                 "flaky"
#             )
#         )
#         or is_yes(
#             historical.get(
#                 "flaky_remediation_protection"
#             )
#         )
#     ):
#         flags.add(
#             "FLAKY_REMEDIATE_NOT_EXCLUDE"
#         )

#     return flags


# def _apply_protection_rules(
#     base_classification: str,
#     protection_flags: set[str],
# ) -> str:
#     """
#     Apply hard and soft protections.

#     Hard protections always produce MUST_TEST.

#     Soft protections only prevent exclusion:
#     - OPTIONAL stays OPTIONAL
#     - EXCLUDE becomes OPTIONAL
#     - MUST_TEST and RECOMMENDED remain unchanged
#     """

#     if HARD_PROTECTIONS.intersection(
#         protection_flags
#     ):
#         return "MUST_TEST"

#     if SOFT_PROTECTIONS.intersection(
#         protection_flags
#     ):
#         if base_classification == "EXCLUDE":
#             return "OPTIONAL"

#         return base_classification

#     return base_classification


# def _build_reasons(
#     test_case_id: str,
#     tier: str,
#     change_factor: float,
#     historical_value_score: float,
#     release_type: str,
#     release_factor: float,
#     base_classification: str,
#     final_classification: str,
#     protection_flags: set[str],
#     direct_test_ids: set[str],
#     downstream_test_ids: set[str],
# ) -> list[str]:
#     reasons: list[str] = []

#     if test_case_id in direct_test_ids:
#         reasons.append(
#             "Directly mapped to a changed requirement"
#         )
#     elif test_case_id in downstream_test_ids:
#         reasons.append(
#             "Impacted through a dependent module"
#         )
#     else:
#         reasons.append(
#             "No mapped release change impact"
#         )

#     reasons.append(
#         f"Application criticality is {tier}"
#     )

#     reasons.append(
#         "Historical value score is "
#         f"{historical_value_score:.2f}"
#     )

#     reasons.append(
#         f"Release risk is {release_type} "
#         f"with factor {release_factor:.2f}"
#     )

#     reasons.append(
#         f"Numerical classification was "
#         f"{base_classification}"
#     )

#     for flag in sorted(
#         protection_flags
#     ):
#         reasons.append(flag)

#     if (
#         final_classification
#         != base_classification
#     ):
#         reasons.append(
#             "Final classification was elevated "
#             "by a protection rule"
#         )

#     return reasons


# def _enforce_criticality_coverage_floors(
#     results: list[dict[str, Any]],
#     criticality: dict[str, Any],
# ) -> None:
#     """Enforce BR-CRIT-03 without altering composite-score mathematics."""
#     criticality_payload = criticality.get("agent_output", criticality)
#     test_tags = criticality_payload.get("test_tags", criticality.get("test_tags", {}))
#     if not isinstance(test_tags, dict):
#         return

#     by_module: dict[str, list[dict[str, Any]]] = {}
#     for row in results:
#         module_id = str(row.get("module_id") or "").strip()
#         by_module.setdefault(module_id, []).append(row)

#     for module_id, rows in by_module.items():
#         tags = [tag for tag in test_tags.values() if str(tag.get("module_id") or "").strip() == module_id]
#         if not tags:
#             continue
#         tier = _normalize_tier(rows[0].get("tier"))
#         if tier not in {"TIER_1", "TIER_2"}:
#             continue
#         required = len(tags) if tier == "TIER_1" else int((0.70 * len(tags)) + 0.999999)
#         selected = [row for row in rows if row.get("classification") in {"MUST_TEST", "RECOMMENDED"}]
#         deficit = max(0, required - len(selected))
#         if not deficit:
#             continue
#         candidates = [row for row in rows if row.get("classification") != "MUST_TEST"]
#         candidates.sort(key=lambda row: (
#             {"EXCLUDE": 0, "OPTIONAL": 1, "RECOMMENDED": 2}.get(row.get("classification"), 0),
#             float(row.get("composite_score") or 0.0),
#             str(row.get("test_case_id") or ""),
#         ))
#         for row in candidates[:deficit]:
#             previous = row.get("classification") or "UNKNOWN"
#             row["classification"] = "MUST_TEST"
#             flags = set(row.get("protection_flags") or [])
#             flags.add("TIER_1_COVERAGE_FLOOR" if tier == "TIER_1" else "TIER_2_COVERAGE_FLOOR")
#             row["protection_flags"] = sorted(flags)
#             row.setdefault("reasons", []).append(
#                 f"BR-CRIT-03 coverage floor elevated classification from {previous} to MUST_TEST."
#             )
#             row["classification_overridden"] = True


# def _build_summary(
#     results: list[dict[str, Any]],
# ) -> dict[str, Any]:
#     classifications = (
#         "MUST_TEST",
#         "RECOMMENDED",
#         "OPTIONAL",
#         "EXCLUDE",
#     )

#     summary: dict[str, Any] = {
#         "total_tests": len(results),
#     }

#     for classification in classifications:
#         summary[classification] = sum(
#             1
#             for row in results
#             if row["classification"]
#             == classification
#         )

#     summary[
#         "base_must_test"
#     ] = sum(
#         1
#         for row in results
#         if row["base_classification"]
#         == "MUST_TEST"
#     )

#     summary[
#         "defect_protected_tests"
#     ] = sum(
#         1
#         for row in results
#         if "DEFECT_CATCH_PROTECTION" in row.get("protection_flags", [])
#     )

#     summary[
#         "insufficient_history_tests"
#     ] = sum(
#         1
#         for row in results
#         if "INSUFFICIENT_HISTORY_INCLUDE" in row.get("protection_flags", [])
#     )

#     summary[
#         "flaky_remediation_tests"
#     ] = sum(
#         1
#         for row in results
#         if "FLAKY_REMEDIATE_NOT_EXCLUDE" in row.get("protection_flags", [])
#     )

#     summary[
#         "consistent_pass_zero_defect_candidates"
#     ] = sum(
#         1
#         for row in results
#         if row.get("consistent_pass_zero_defect_candidate")
#     )

#     summary[
#         "consistent_pass_zero_defect_candidate_ids"
#     ] = [
#         row["test_case_id"]
#         for row in results
#         if row.get("consistent_pass_zero_defect_candidate")
#     ]

#     summary[
#         "protection_overrides"
#     ] = sum(
#         1
#         for row in results
#         if row[
#             "classification_overridden"
#         ]
#     )

#     summary[
#         "selected_execution_minutes"
#     ] = round(
#         sum(
#             row["execution_minutes"]
#             for row in results
#             if row["classification"]
#             in {
#                 "MUST_TEST",
#                 "RECOMMENDED",
#             }
#         ),
#         2,
#     )

#     summary[
#         "full_regression_minutes"
#     ] = round(
#         sum(
#             row["execution_minutes"]
#             for row in results
#         ),
#         2,
#     )

#     full_minutes = summary[
#         "full_regression_minutes"
#     ]

#     selected_minutes = summary[
#         "selected_execution_minutes"
#     ]

#     summary[
#         "execution_reduction_percentage"
#     ] = (
#         round(
#             (
#                 1
#                 - selected_minutes
#                 / full_minutes
#             )
#             * 100,
#             2,
#         )
#         if full_minutes
#         else 0.0
#     )

#     summary[
#         "must_test_percentage"
#     ] = (
#         round(
#             summary["MUST_TEST"]
#             / len(results)
#             * 100,
#             2,
#         )
#         if results
#         else 0.0
#     )

#     summary[
#         "recommended_percentage"
#     ] = (
#         round(
#             summary["RECOMMENDED"]
#             / len(results)
#             * 100,
#             2,
#         )
#         if results
#         else 0.0
#     )

#     summary[
#         "optional_percentage"
#     ] = (
#         round(
#             summary["OPTIONAL"]
#             / len(results)
#             * 100,
#             2,
#         )
#         if results
#         else 0.0
#     )

#     summary[
#         "exclude_percentage"
#     ] = (
#         round(
#             summary["EXCLUDE"]
#             / len(results)
#             * 100,
#             2,
#         )
#         if results
#         else 0.0
#     )

#     return summary


# def format_scoring_dashboard(
#     result: dict[str, Any],
# ) -> str:
#     """Create a user-facing Markdown dashboard for ADK."""

#     summary = result.get(
#         "summary",
#         {},
#     )

#     results = result.get(
#         "results",
#         [],
#     )

#     lines: list[str] = [
#         "# Decision Engine / Risk Scoring",
#         "",
#         "## Classification Dashboard",
#         "",
#         "| Classification | Count | Percentage |",
#         "|---|---:|---:|",
#         "| MUST_TEST | "
#         f"{summary.get('MUST_TEST', 0)} | "
#         f"{summary.get('must_test_percentage', 0):.2f}% |",
#         "| RECOMMENDED | "
#         f"{summary.get('RECOMMENDED', 0)} | "
#         f"{summary.get('recommended_percentage', 0):.2f}% |",
#         "| OPTIONAL | "
#         f"{summary.get('OPTIONAL', 0)} | "
#         f"{summary.get('optional_percentage', 0):.2f}% |",
#         "| EXCLUDE | "
#         f"{summary.get('EXCLUDE', 0)} | "
#         f"{summary.get('exclude_percentage', 0):.2f}% |",
#         "| **Total** | "
#         f"**{summary.get('total_tests', 0)}** | **100%** |",
#         "",
#         "> **Selected execution time:** "
#         f"{summary.get('selected_execution_minutes', 0):.2f} minutes",
#         ">",
#         "> **Full-regression time:** "
#         f"{summary.get('full_regression_minutes', 0):.2f} minutes",
#         ">",
#         "> **Estimated reduction:** "
#         f"{summary.get('execution_reduction_percentage', 0):.2f}%",
#         ">",
#         "> **Protection overrides:** "
#         f"{summary.get('protection_overrides', 0)}",
#         "",
#     ]

#     for classification in (
#         "MUST_TEST",
#         "RECOMMENDED",
#         "OPTIONAL",
#         "EXCLUDE",
#     ):
#         matching = [
#             row
#             for row in results
#             if row["classification"]
#             == classification
#         ]

#         lines.extend(
#             [
#                 "---",
#                 "",
#                 f"## {classification}",
#                 "",
#             ]
#         )

#         if not matching:
#             lines.extend(
#                 [
#                     f"> No {classification} test cases.",
#                     "",
#                 ]
#             )
#             continue

#         for row in matching:
#             flags = row.get(
#                 "protection_flags",
#                 [],
#             )

#             flag_text = (
#                 ", ".join(flags)
#                 if flags
#                 else "None"
#             )

#             reasons = row.get(
#                 "reasons",
#                 [],
#             )

#             reason_text = (
#                 "; ".join(
#                     reasons[:4]
#                 )
#                 if reasons
#                 else "No explanation available"
#             )

#             lines.extend(
#                 [
#                     f"> ### `{row['test_case_id']}` — "
#                     f"{_display(row.get('test_name'))}",
#                     ">",
#                     f"> **Module:** `{_display(row.get('module_id'))}`",
#                     ">",
#                     f"> **Tier:** `{row.get('tier', 'TIER_3')}`",
#                     ">",
#                     f"> **Score:** `{row.get('composite_score', 0):.2f}`",
#                     ">",
#                     f"> **Risk band:** `{row.get('risk_band', 'LOW')}`",
#                     ">",
#                     f"> **Protection:** {flag_text}",
#                     ">",
#                     f"> **Reason:** {reason_text}",
#                     "",
#                 ]
#             )

#     return "\n".join(lines)


# def _load_weights(
#     rows: list[dict[str, Any]],
# ) -> dict[str, float]:
#     configured: dict[str, float] = {}

#     for row in rows:
#         factor = _value(
#             row,
#             "Factor",
#             "Factor_Name",
#             "Scoring_Factor",
#         )

#         weight_value = _value(
#             row,
#             "Weight",
#             "Factor_Weight",
#         )

#         if not factor or weight_value is None:
#             continue

#         factor_name = _normalized(
#             factor
#         )

#         if factor_name not in DEFAULT_WEIGHTS:
#             continue

#         weight = _to_float(
#             weight_value
#         )

#         if weight > 1:
#             weight /= 100

#         if weight >= 0:
#             configured[
#                 factor_name
#             ] = weight

#     weights = DEFAULT_WEIGHTS.copy()
#     weights.update(configured)

#     total = sum(
#         weights.values()
#     )

#     if total <= 0:
#         return DEFAULT_WEIGHTS.copy()

#     return {
#         factor: weight / total
#         for factor, weight
#         in weights.items()
#     }


# def _load_thresholds(
#     rows: list[dict[str, Any]],
# ) -> dict[str, float]:
#     thresholds = (
#         DEFAULT_THRESHOLDS.copy()
#     )

#     for row in rows:
#         classification = _value(
#             row,
#             "Classification",
#             "Risk_Classification",
#             "Category",
#             "Decision",
#         )

#         minimum_score = _value(
#             row,
#             "Minimum_Score",
#             "Min_Score",
#             "Threshold",
#             "Lower_Bound",
#         )

#         if (
#             classification is None
#             or minimum_score is None
#         ):
#             continue

#         normalized_classification = (
#             _normalized(
#                 classification
#             )
#         )

#         if (
#             normalized_classification
#             not in thresholds
#         ):
#             continue

#         thresholds[
#             normalized_classification
#         ] = _to_float(
#             minimum_score,
#             default=thresholds[
#                 normalized_classification
#             ],
#         )

#     return thresholds


# def _classification_from_score(
#     score: float,
#     thresholds: dict[str, float],
# ) -> str:
#     for classification in (
#         "MUST_TEST",
#         "RECOMMENDED",
#         "OPTIONAL",
#         "EXCLUDE",
#     ):
#         minimum_score = thresholds.get(
#             classification,
#             DEFAULT_THRESHOLDS[
#                 classification
#             ],
#         )

#         if score >= minimum_score:
#             return classification

#     return "EXCLUDE"


# def _change_impact_factor(
#     test_case_id: str,
#     direct_test_ids: set[str],
#     downstream_test_ids: set[str],
# ) -> float:
#     if test_case_id in direct_test_ids:
#         return 1.00

#     if test_case_id in downstream_test_ids:
#         return 0.70

#     return 0.00


# def _risk_band(
#     score: float,
# ) -> str:
#     if score >= 80:
#         return "VERY_HIGH"

#     if score >= 60:
#         return "HIGH"

#     if score >= 40:
#         return "MEDIUM"

#     return "LOW"


# def _classification_order(
#     classification: str,
# ) -> int:
#     return {
#         "MUST_TEST": 0,
#         "RECOMMENDED": 1,
#         "OPTIONAL": 2,
#         "EXCLUDE": 3,
#     }.get(
#         classification,
#         99,
#     )


# def _normalize_tier(
#     value: Any,
# ) -> str:
#     normalized = _normalized(
#         value
#     )

#     return {
#         "1": "TIER_1",
#         "TIER1": "TIER_1",
#         "TIER_1": "TIER_1",
#         "2": "TIER_2",
#         "TIER2": "TIER_2",
#         "TIER_2": "TIER_2",
#         "3": "TIER_3",
#         "TIER3": "TIER_3",
#         "TIER_3": "TIER_3",
#         "4": "TIER_4",
#         "TIER4": "TIER_4",
#         "TIER_4": "TIER_4",
#     }.get(
#         normalized,
#         normalized or "TIER_3",
#     )


# def _string_set(
#     values: Any,
# ) -> set[str]:
#     if not values:
#         return set()

#     if isinstance(
#         values,
#         dict,
#     ):
#         values = values.keys()

#     if isinstance(
#         values,
#         str,
#     ):
#         values = [values]

#     return {
#         str(value).strip()
#         for value in values
#         if value is not None
#         and str(value).strip()
#     }


# def _value(
#     row: dict[str, Any],
#     *possible_names: str,
# ) -> Any:
#     if not row:
#         return None

#     normalized_row = {
#         _normalize_header(key): value
#         for key, value
#         in row.items()
#     }

#     for name in possible_names:
#         normalized_name = (
#             _normalize_header(name)
#         )

#         if normalized_name in normalized_row:
#             return normalized_row[
#                 normalized_name
#             ]

#     return None


# def _normalize_header(
#     value: Any,
# ) -> str:
#     return (
#         str(value)
#         .strip()
#         .lower()
#         .replace("_", "")
#         .replace("-", "")
#         .replace(" ", "")
#     )


# def _normalized(
#     value: Any,
# ) -> str:
#     return (
#         str(value or "")
#         .strip()
#         .upper()
#         .replace("-", "_")
#         .replace(" ", "_")
#     )


# def _first_non_empty(
#     *values: Any,
# ) -> Any:
#     for value in values:
#         if value is not None and value != "":
#             return value

#     return None


# def _display(
#     value: Any,
# ) -> str:
#     if value is None or value == "":
#         return "Not available"

#     return str(value)


# def _to_float(
#     value: Any,
#     default: float = 0.0,
# ) -> float:
#     try:
#         return float(value)
#     except (
#         TypeError,
#         ValueError,
#     ):
#         return default

# # A2A: Specialist boundary. The Master Orchestrator calls this handler with a
# # serializable A2A envelope. The specialist never owns Jira/Excel connectivity.
# def handle_a2a_request(request: A2ARequest) -> A2AResponse:

#     try:

#         data = validate_message(
#             request,
#             receiver='Decision Engine / Risk Scoring Agent',
#             message_types={
#                 'SCORING_REQUEST',
#                 "AGENT_QUERY",
#             },
#         )

#         if request.message_type == "AGENT_QUERY":
#             return make_response(
#                 request,
#                 sender='Decision Engine / Risk Scoring Agent',
#                 data=answer_agent_question(
#                     question=str(data.get("question") or ""),
#                     context=data.get(
#                         "agent_context",
#                         data,
#                     ),
#                 ),
#             )

#         result = calculate_test_selection(
#             source_data=data.get(
#                 "source_data",
#                 {},
#             ),
#             change_impact=data.get(
#                 "change_impact",
#                 {},
#             ),
#             criticality=data.get(
#                 "criticality",
#                 {},
#             ),
#             history=data.get(
#                 "history",
#                 {},
#             ),
#             policy=data.get(
#                 "policy",
#                 {},
#             ),
#         )

#         return make_response(
#             request,
#             sender='Decision Engine / Risk Scoring Agent',
#             data=result,
#         )

#     except Exception as exc:

#         trace_error(
#             "SCORING_AGENT_FAILED",
#             agent="Decision Engine / Risk Scoring Agent",
#             error=exc,
#             release_id=request.release_id,
#         )

#         raise

# def answer_agent_question(
#     question: str,
#     context: dict[str, Any],
# ) -> dict[str, Any]:
#     """Answer specialist questions only from orchestrator-supplied context.

#     A2A: No Jira, Excel, filesystem, or external-service reads are allowed here.
#     """
#     if not isinstance(context, dict):
#         raise TypeError("context must be the orchestrator-supplied agent context.")
#     question = str(question or "").strip()
#     if not question:
#         raise ValueError("question is required.")
#     log_event(
#     "SCORING_AGENT_QUERY",
#     agent="Decision Engine / Risk Scoring Agent",
#     stage="SCORING",
#     status="SUCCESS",
#     question=question,
#     )
#     return {
#         "status": "success",
#         "agent": 'Decision Engine / Risk Scoring Agent',
#         "question": question,
#         "context": context,
#         "markdown": _agent_question_markdown(question, context),
#     }


# def _agent_question_markdown(question: str, context: dict[str, Any]) -> str:
#     import json
#     output = context.get("agent_output", context)
#     return "\n".join([
#         f"# {'Decision Engine / Risk Scoring Agent'}",
#         "",
#         f"**Question:** {question}",
#         "",
#         "> Answer grounded in the Master Orchestrator's current specialist context.",
#         "",
#         "## Specialist Context",
#         "",
#         "```json",
#         json.dumps(output, indent=2, default=str),
#         "```",
#     ])



############################################################################################################################################################
############################################################################################################################################################
#----------------------------Updated code as per mcp server spider code-------------------



#old_scoring_agent/tools.py
from __future__ import annotations

from typing import Any
from app.observability.logger import (
    log_event,
    trace_error,
)

from app.observability.audit import audit_event

from app.models import A2ARequest, A2AResponse
from app.services.a2a import make_response, validate_message

from app.utils.helpers import is_yes, tier_factor


DEFAULT_WEIGHTS: dict[str, float] = {
    "CHANGE_IMPACT": 0.40,
    "CRITICALITY": 0.30,
    "HISTORICAL_VALUE": 0.20,
    "RELEASE_RISK": 0.10,
}


DEFAULT_THRESHOLDS: dict[str, float] = {
    "MUST_TEST": 80.0,
    "RECOMMENDED": 60.0,
    "OPTIONAL": 40.0,
    "EXCLUDE": 0.0,
}


RELEASE_RISK_FACTORS: dict[str, float] = {
    "MAJOR": 0.80,
    "MINOR": 0.60,
    "PATCH": 0.40,
    "HOTFIX": 0.70,
    "EMERGENCY": 1.00,
}


HARD_PROTECTIONS = {
    "REGULATORY_ALWAYS_EXECUTE",
    "POLICY_MANDATORY",
    "POLICY_EXCLUSION_PROHIBITED",
    "NEW_FEATURE_PROTECTION",
    "DEFECT_CATCH_PROTECTION",
    "TIER_1_FLOOR",
}


SOFT_PROTECTIONS = {
    "INSUFFICIENT_HISTORY_INCLUDE",
    "FLAKY_REMEDIATE_NOT_EXCLUDE",
}


REQUIRED_INPUT_KEYS: tuple[str, ...] = (
    "test_cases",
)

OPTIONAL_INPUT_KEYS: tuple[str, ...] = (
    "scoring_weights",
    "thresholds",
)


def calculate_test_selection(
    source_data: dict[
        str,
        list[dict[str, Any]],
    ],
    change_impact: dict[str, Any],
    criticality: dict[str, Any],
    history: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    """
    Calculate scores and final test classifications.

    The Master Orchestrator must provide all raw input rows through
    ``source_data`` and the structured outputs from the preceding agents.
    This agent does not open or read the Excel workbook.

    Required source_data keys:
    - test_cases

    Optional source_data keys:
    - scoring_weights
    - thresholds

    When optional configuration is absent, the documented internal defaults
    are used. The Master Orchestrator normally supplies these blocks explicitly.

    Agent inputs:
    - Feature / Epic Change Impact output
    - Application Criticality output
    - Historical Execution Intelligence output
    - Policy / Risk Appetite output

    Generated outputs:
    - Per-test scoring result
    - Classification summary
    - Compact agent-to-agent payload
    - Markdown dashboard

    This function does not read:
    - A5_Test_Scoring
    """
    log_event(
    "SCORING_STARTED",
    agent="Decision Engine / Risk Scoring Agent",
    stage="SCORING",
    status="STARTED",
    )

    _validate_orchestrator_inputs(
        source_data=source_data,
        change_impact=change_impact,
        criticality=criticality,
        history=history,
        policy=policy,
    )

    test_case_rows = source_data["test_cases"]
    log_event(
    "SCORING_INPUTS_LOADED",
    agent="Decision Engine / Risk Scoring Agent",
    stage="SCORING",
    status="SUCCESS",
    test_cases=len(test_case_rows),
    )


    scoring_weight_rows = source_data.get("scoring_weights", [])
    threshold_rows = source_data.get("thresholds", [])

    weights = (
        _load_weights(scoring_weight_rows)
        if scoring_weight_rows
        else DEFAULT_WEIGHTS.copy()
    )
    thresholds = (
        _load_thresholds(threshold_rows)
        if threshold_rows
        else DEFAULT_THRESHOLDS.copy()
    )

    # Test Status is a business field. Jira workflow Status (e.g. "To Do")
    # must never override it.
    active_tests = [
        row
        for row in test_case_rows
        if _normalized(
            _first_non_empty(
                _value(
                    row,
                    "Test_Status",
                    "Test Status",
                    "TestStatus",
                ),
                "ACTIVE",
            )
        )
        in {
            "ACTIVE",
            "ENABLED",
            "CURRENT",
            "APPROVED",
        }
    ]
    log_event(
    "ACTIVE_TESTS_FILTERED",
    agent="Decision Engine / Risk Scoring Agent",
    stage="SCORING",
    active_tests=len(active_tests),
    )


    # ---------------------------------------------------------
    # Read compact or full Feature Agent output
    # ---------------------------------------------------------
    change_payload = change_impact.get(
        "agent_output",
        change_impact,
    )

    direct_test_ids = _string_set(
        change_payload.get(
            "direct_test_ids",
            change_impact.get(
                "direct_test_ids",
                [],
            ),
        )
    )

    downstream_test_ids = _string_set(
        change_payload.get(
            "downstream_test_ids",
            change_impact.get(
                "downstream_test_ids",
                [],
            ),
        )
    )

    new_feature_test_ids = _string_set(
        change_payload.get(
            "new_feature_test_ids",
            change_impact.get(
                "new_feature_test_ids",
                [],
            ),
        )
    )

    # ---------------------------------------------------------
    # Read compact or full Criticality Agent output
    # ---------------------------------------------------------
    criticality_payload = criticality.get(
        "agent_output",
        criticality,
    )

    test_tags = criticality_payload.get(
        "test_tags",
        criticality.get(
            "test_tags",
            {},
        ),
    )

    # ---------------------------------------------------------
    # Read compact or full Historical Agent output
    # ---------------------------------------------------------
    history_payload = history.get(
        "agent_output",
        history,
    )

    historical_summaries = history_payload.get(
        "test_summaries",
        history.get(
            "test_summaries",
            {},
        ),
    )

    # ---------------------------------------------------------
    # Read compact or full Policy Agent output
    # ---------------------------------------------------------
    policy_payload = policy.get(
        "agent_output",
        policy,
    )

    release_type = _normalized(
        _first_non_empty(
            policy_payload.get(
                "release_type"
            ),
            policy.get(
                "release_type"
            ),
            "UNKNOWN",
        )
    )

    release_factor = RELEASE_RISK_FACTORS.get(
        release_type,
        0.60,
    )

    regulatory_test_ids = _string_set(
        _first_non_empty(
            policy_payload.get(
                "regulatory_test_ids"
            ),
            list(
                policy.get(
                    "regulatory_tests",
                    {},
                ).keys()
            ),
            [],
        )
    )

    mandatory_test_ids = _string_set(
        _first_non_empty(
            policy_payload.get(
                "mandatory_test_ids"
            ),
            policy.get(
                "mandatory_test_ids"
            ),
            [],
        )
    )

    always_execute_test_ids = _string_set(
        _first_non_empty(
            policy_payload.get(
                "always_execute_test_ids"
            ),
            policy.get(
                "always_execute_test_ids"
            ),
            [],
        )
    )

    exclusion_prohibited_test_ids = _string_set(
        _first_non_empty(
            policy_payload.get(
                "exclusion_prohibited_test_ids"
            ),
            policy.get(
                "exclusion_prohibited_test_ids"
            ),
            [],
        )
    )

    test_policy_decisions = (
        policy_payload.get(
            "test_policy_decisions"
        )
        or policy.get(
            "test_policy_decisions"
        )
        or {}
    )

    results: list[dict[str, Any]] = []

    # ---------------------------------------------------------
    # Score every active test
    # ---------------------------------------------------------
    for test_case in active_tests:
        test_case_id_value = _value(
            test_case,
            "Test_Case_ID",
            "Test Case ID",
            "TestCase_ID",
            "Test_ID",
            "TC_ID",
        )

        if not test_case_id_value:
            continue

        test_case_id = str(
            test_case_id_value
        ).strip()

        test_name = _value(
            test_case,
            "Test_Name",
            "Test Name",
            "Test_Case_Name",
            "Name",
            "Description",
        )

        module_id = _value(
            test_case,
            "Module_ID",
            "Module ID",
            "ModuleId",
        )

        tag = test_tags.get(
            test_case_id,
            {
                "tier": "TIER_3",
                "tier_floor_protection": False,
                "criticality_score": 2.50,
                "minimum_coverage": 0.50,
            },
        )

        historical = historical_summaries.get(
            test_case_id,
            {},
        )

        test_policy = test_policy_decisions.get(
            test_case_id,
            {},
        )

        change_factor = _change_impact_factor(
            test_case_id=test_case_id,
            direct_test_ids=direct_test_ids,
            downstream_test_ids=(
                downstream_test_ids
            ),
        )

        tier = _normalize_tier(
            tag.get(
                "tier",
                "TIER_3",
            )
        )

        criticality_factor = tier_factor(
            tier
        )

        historical_value_score = _to_float(
            historical.get(
                "Historical_Value_Score",
                0,
            ),
            default=0.0,
        )

        historical_factor = min(
            max(
                historical_value_score
                / 100.0,
                0.0,
            ),
            1.0,
        )

        weighted_components = {
            "CHANGE_IMPACT": (
                weights.get(
                    "CHANGE_IMPACT",
                    0.40,
                )
                * change_factor
            ),
            "CRITICALITY": (
                weights.get(
                    "CRITICALITY",
                    0.30,
                )
                * criticality_factor
            ),
            "HISTORICAL_VALUE": (
                weights.get(
                    "HISTORICAL_VALUE",
                    0.20,
                )
                * historical_factor
            ),
            "RELEASE_RISK": (
                weights.get(
                    "RELEASE_RISK",
                    0.10,
                )
                * release_factor
            ),
        }

        composite_score = 100.0 * sum(
            weighted_components.values()
        )

        protection_flags = _protection_flags(
            test_case_id=test_case_id,
            tag=tag,
            historical=historical,
            test_policy=test_policy,
            regulatory_test_ids=(
                regulatory_test_ids
            ),
            mandatory_test_ids=(
                mandatory_test_ids
            ),
            always_execute_test_ids=(
                always_execute_test_ids
            ),
            exclusion_prohibited_test_ids=(
                exclusion_prohibited_test_ids
            ),
            new_feature_test_ids=(
                new_feature_test_ids
            ),
        )

        base_classification = (
            _classification_from_score(
                score=composite_score,
                thresholds=thresholds,
            )
        )

        final_classification = (
            _apply_protection_rules(
                base_classification=(
                    base_classification
                ),
                protection_flags=(
                    protection_flags
                ),
            )
        )

        risk_band = _risk_band(
            composite_score
        )

        reasons = _build_reasons(
            test_case_id=test_case_id,
            tier=tier,
            change_factor=change_factor,
            historical_value_score=(
                historical_value_score
            ),
            release_type=release_type,
            release_factor=release_factor,
            base_classification=(
                base_classification
            ),
            final_classification=(
                final_classification
            ),
            protection_flags=(
                protection_flags
            ),
            direct_test_ids=(
                direct_test_ids
            ),
            downstream_test_ids=(
                downstream_test_ids
            ),
        )

        execution_minutes = _to_float(
            _value(
                test_case,
                "Execution_Minutes",
                "Execution Minutes",
                "Duration_Minutes",
                "Duration",
            ),
            default=0.0,
        )

        results.append(
            {
                "test_case_id": test_case_id,
                "test_name": test_name,
                "module_id": module_id,
                "tier": tier,
                "criticality_score": _to_float(
                    tag.get(
                        "criticality_score",
                        0,
                    )
                ),
                "change_impact_factor": round(
                    change_factor,
                    4,
                ),
                "criticality_factor": round(
                    criticality_factor,
                    4,
                ),
                "historical_value_score": round(
                    historical_value_score,
                    2,
                ),
                "historical_value_factor": round(
                    historical_factor,
                    4,
                ),
                "release_type": release_type,
                "release_risk_factor": round(
                    release_factor,
                    4,
                ),
                "score_components": {
                    factor: round(
                        contribution * 100,
                        2,
                    )
                    for factor, contribution
                    in weighted_components.items()
                },
                "composite_score": round(
                    composite_score,
                    2,
                ),
                "risk_band": risk_band,
                "protection_flags": sorted(
                    protection_flags
                ),
                "base_classification": (
                    base_classification
                ),
                "classification": (
                    final_classification
                ),
                "classification_overridden": (
                    base_classification
                    != final_classification
                ),
                "execution_minutes": (
                    execution_minutes
                ),
                "reasons": reasons,
            }
        )

    results.sort(
        key=lambda row: (
            _classification_order(row["classification"]),
            -row["composite_score"],
            row["test_case_id"],
        )
    )
    log_event(
        "BR_SEL_01_APPLIED",
        agent="Decision Engine / Risk Scoring Agent",
        rule_id="BR-SEL-01",
        scored_tests=len(results),
    )
    summary = _build_summary(
        results
    )
    log_event(
    "TEST_CLASSIFICATION_COMPLETED",
    agent="Decision Engine / Risk Scoring Agent",
    must_test=summary.get("MUST_TEST", 0),
    recommended=summary.get("RECOMMENDED", 0),
    optional=summary.get("OPTIONAL", 0),
    exclude=summary.get("EXCLUDE", 0),
    )
    log_event(
        "BR_SEL_02_APPLIED",
        agent="Decision Engine / Risk Scoring Agent",
        rule_id="BR-SEL-02",
        protection_overrides=summary.get(
            "protection_overrides",
            0,
        ),
    )

    classification_groups = {
        classification: [
            row["test_case_id"]
            for row in results
            if row["classification"]
            == classification
        ]
        for classification in (
            "MUST_TEST",
            "RECOMMENDED",
            "OPTIONAL",
            "EXCLUDE",
        )
    }

    result: dict[str, Any] = {
        "weights": weights,
        "thresholds": thresholds,
        "release_type": release_type,
        "release_risk_factor": (
            release_factor
        ),
        "results": results,
        "classification_groups": (
            classification_groups
        ),
        "summary": summary,

        # Compact payload consumed by Governance.
        "agent_output": {
            "release_type": release_type,
            "weights": weights,
            "thresholds": thresholds,
            "results": results,
            "classification_groups": (
                classification_groups
            ),
            "summary": summary,
            "governance_candidates": [
                {
                    "test_case_id": (
                        row["test_case_id"]
                    ),
                    "test_name": (
                        row["test_name"]
                    ),
                    "module_id": (
                        row["module_id"]
                    ),
                    "tier": row["tier"],
                    "composite_score": (
                        row[
                            "composite_score"
                        ]
                    ),
                    "classification": (
                        row[
                            "classification"
                        ]
                    ),
                    "protection_flags": (
                        row[
                            "protection_flags"
                        ]
                    ),
                    "reasons": row["reasons"],
                }
                for row in results
                if row["classification"]
                == "EXCLUDE"
            ],
        },
    }

    log_event(
    "SCORING_COMPLETED",
    agent="Decision Engine / Risk Scoring Agent",
    stage="SCORING",
    status="SUCCESS",
    total_tests=len(results),
    )

    audit_event(
        "SCORING_COMPLETED",
        agent="Decision Engine / Risk Scoring Agent",
        message=(
            f"Scored {len(results)} test cases."
        ),
        details={
            "must_test": summary.get("MUST_TEST", 0),
            "recommended": summary.get("RECOMMENDED", 0),
            "optional": summary.get("OPTIONAL", 0),
            "exclude": summary.get("EXCLUDE", 0),
            "execution_reduction_percentage": summary.get(
                "execution_reduction_percentage",
                0,
            ),
        },
    )


    result["markdown"] = (
        format_scoring_dashboard(result)
    )

    return result


def _validate_orchestrator_inputs(
    source_data: dict[
        str,
        list[dict[str, Any]],
    ],
    change_impact: dict[str, Any],
    criticality: dict[str, Any],
    history: dict[str, Any],
    policy: dict[str, Any],
) -> None:
    """
    Validate raw input rows and upstream agent outputs supplied by the
    Master Orchestrator.
    """

    if not isinstance(
        source_data,
        dict,
    ):
        raise TypeError(
            "source_data must be a dictionary "
            "provided by the Master Orchestrator."
        )

    missing_inputs = [
        input_name
        for input_name in REQUIRED_INPUT_KEYS
        if input_name not in source_data
    ]

    if missing_inputs:
        raise ValueError(
            "Scoring Agent is missing required "
            "orchestrator inputs: "
            f"{missing_inputs}"
        )

    invalid_inputs = [
        input_name
        for input_name in REQUIRED_INPUT_KEYS
        if not isinstance(source_data[input_name], list)
    ]

    invalid_optional_inputs = [
        input_name
        for input_name in OPTIONAL_INPUT_KEYS
        if input_name in source_data and not isinstance(source_data[input_name], list)
    ]

    if invalid_inputs:
        raise TypeError(
            "Scoring Agent expected required input rows as lists for: "
            f"{invalid_inputs}"
        )

    if invalid_optional_inputs:
        raise TypeError(
            "Scoring Agent expected optional configuration blocks as lists for: "
            f"{invalid_optional_inputs}"
        )

    upstream_inputs = {
        "change_impact": change_impact,
        "criticality": criticality,
        "history": history,
        "policy": policy,
    }

    invalid_inputs = [
        name
        for name, value
        in upstream_inputs.items()
        if not isinstance(
            value,
            dict,
        )
    ]

    if invalid_inputs:
        raise TypeError(
            "Scoring Agent expected structured "
            "dictionary outputs from the Master "
            "Orchestrator for: "
            f"{invalid_inputs}"
        )

def _protection_flags(
    test_case_id: str,
    tag: dict[str, Any],
    historical: dict[str, Any],
    test_policy: dict[str, Any],
    regulatory_test_ids: set[str],
    mandatory_test_ids: set[str],
    always_execute_test_ids: set[str],
    exclusion_prohibited_test_ids: set[str],
    new_feature_test_ids: set[str],
) -> set[str]:
    """
    Build protection flags using explicit yes/true conversion.

    Using bool(value) is unsafe for Excel-derived strings because
    bool("NO") and bool("FALSE") are both True.
    """

    flags: set[str] = set()

    if test_case_id in regulatory_test_ids:
        flags.add(
            "REGULATORY_ALWAYS_EXECUTE"
        )

    if (
        test_case_id in mandatory_test_ids
        or test_case_id
        in always_execute_test_ids
        or is_yes(
            test_policy.get(
                "mandatory"
            )
        )
        or is_yes(
            test_policy.get(
                "always_execute"
            )
        )
    ):
        flags.add(
            "POLICY_MANDATORY"
        )

    if (
        test_case_id
        in exclusion_prohibited_test_ids
        or is_yes(
            test_policy.get(
                "exclusion_prohibited"
            )
        )
    ):
        flags.add(
            "POLICY_EXCLUSION_PROHIBITED"
        )

    if test_case_id in new_feature_test_ids:
        flags.add(
            "NEW_FEATURE_PROTECTION"
        )

    if is_yes(
        historical.get(
            "defect_catch_protection"
        )
    ):
        flags.add(
            "DEFECT_CATCH_PROTECTION"
        )

    if is_yes(
        tag.get(
            "tier_floor_protection"
        )
    ):
        flags.add(
            "TIER_1_FLOOR"
        )

    if is_yes(
        historical.get(
            "insufficient_history"
        )
    ):
        flags.add(
            "INSUFFICIENT_HISTORY_INCLUDE"
        )

    if (
        is_yes(
            historical.get(
                "flaky"
            )
        )
        or is_yes(
            historical.get(
                "flaky_remediation_protection"
            )
        )
    ):
        flags.add(
            "FLAKY_REMEDIATE_NOT_EXCLUDE"
        )

    return flags


def _apply_protection_rules(
    base_classification: str,
    protection_flags: set[str],
) -> str:
    """
    Apply hard and soft protections.

    Hard protections always produce MUST_TEST.

    Soft protections only prevent exclusion:
    - OPTIONAL stays OPTIONAL
    - EXCLUDE becomes OPTIONAL
    - MUST_TEST and RECOMMENDED remain unchanged
    """

    if HARD_PROTECTIONS.intersection(
        protection_flags
    ):
        return "MUST_TEST"

    if SOFT_PROTECTIONS.intersection(
        protection_flags
    ):
        if base_classification == "EXCLUDE":
            return "OPTIONAL"

        return base_classification

    return base_classification


def _build_reasons(
    test_case_id: str,
    tier: str,
    change_factor: float,
    historical_value_score: float,
    release_type: str,
    release_factor: float,
    base_classification: str,
    final_classification: str,
    protection_flags: set[str],
    direct_test_ids: set[str],
    downstream_test_ids: set[str],
) -> list[str]:
    reasons: list[str] = []

    if test_case_id in direct_test_ids:
        reasons.append(
            "Directly mapped to a changed requirement"
        )
    elif test_case_id in downstream_test_ids:
        reasons.append(
            "Impacted through a dependent module"
        )
    else:
        reasons.append(
            "No mapped release change impact"
        )

    reasons.append(
        f"Application criticality is {tier}"
    )

    reasons.append(
        "Historical value score is "
        f"{historical_value_score:.2f}"
    )

    reasons.append(
        f"Release risk is {release_type} "
        f"with factor {release_factor:.2f}"
    )

    reasons.append(
        f"Numerical classification was "
        f"{base_classification}"
    )

    for flag in sorted(
        protection_flags
    ):
        reasons.append(flag)

    if (
        final_classification
        != base_classification
    ):
        reasons.append(
            "Final classification was elevated "
            "by a protection rule"
        )

    return reasons


def _build_summary(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    classifications = (
        "MUST_TEST",
        "RECOMMENDED",
        "OPTIONAL",
        "EXCLUDE",
    )

    summary: dict[str, Any] = {
        "total_tests": len(results),
    }

    for classification in classifications:
        summary[classification] = sum(
            1
            for row in results
            if row["classification"]
            == classification
        )

    summary[
        "base_must_test"
    ] = sum(
        1
        for row in results
        if row["base_classification"]
        == "MUST_TEST"
    )

    summary[
        "protection_overrides"
    ] = sum(
        1
        for row in results
        if row[
            "classification_overridden"
        ]
    )

    summary[
        "selected_execution_minutes"
    ] = round(
        sum(
            row["execution_minutes"]
            for row in results
            if row["classification"]
            in {
                "MUST_TEST",
                "RECOMMENDED",
            }
        ),
        2,
    )

    summary[
        "full_regression_minutes"
    ] = round(
        sum(
            row["execution_minutes"]
            for row in results
        ),
        2,
    )

    full_minutes = summary[
        "full_regression_minutes"
    ]

    selected_minutes = summary[
        "selected_execution_minutes"
    ]

    summary[
        "execution_reduction_percentage"
    ] = (
        round(
            (
                1
                - selected_minutes
                / full_minutes
            )
            * 100,
            2,
        )
        if full_minutes
        else 0.0
    )

    summary[
        "must_test_percentage"
    ] = (
        round(
            summary["MUST_TEST"]
            / len(results)
            * 100,
            2,
        )
        if results
        else 0.0
    )

    summary[
        "recommended_percentage"
    ] = (
        round(
            summary["RECOMMENDED"]
            / len(results)
            * 100,
            2,
        )
        if results
        else 0.0
    )

    summary[
        "optional_percentage"
    ] = (
        round(
            summary["OPTIONAL"]
            / len(results)
            * 100,
            2,
        )
        if results
        else 0.0
    )

    summary[
        "exclude_percentage"
    ] = (
        round(
            summary["EXCLUDE"]
            / len(results)
            * 100,
            2,
        )
        if results
        else 0.0
    )

    return summary


def format_scoring_dashboard(
    result: dict[str, Any],
) -> str:
    """Create a user-facing Markdown dashboard for ADK."""

    summary = result.get(
        "summary",
        {},
    )

    results = result.get(
        "results",
        [],
    )

    lines: list[str] = [
        "# Decision Engine / Risk Scoring",
        "",
        "## Classification Dashboard",
        "",
        "| Classification | Count | Percentage |",
        "|---|---:|---:|",
        "| MUST_TEST | "
        f"{summary.get('MUST_TEST', 0)} | "
        f"{summary.get('must_test_percentage', 0):.2f}% |",
        "| RECOMMENDED | "
        f"{summary.get('RECOMMENDED', 0)} | "
        f"{summary.get('recommended_percentage', 0):.2f}% |",
        "| OPTIONAL | "
        f"{summary.get('OPTIONAL', 0)} | "
        f"{summary.get('optional_percentage', 0):.2f}% |",
        "| EXCLUDE | "
        f"{summary.get('EXCLUDE', 0)} | "
        f"{summary.get('exclude_percentage', 0):.2f}% |",
        "| **Total** | "
        f"**{summary.get('total_tests', 0)}** | **100%** |",
        "",
        "> **Selected execution time:** "
        f"{summary.get('selected_execution_minutes', 0):.2f} minutes",
        ">",
        "> **Full-regression time:** "
        f"{summary.get('full_regression_minutes', 0):.2f} minutes",
        ">",
        "> **Estimated reduction:** "
        f"{summary.get('execution_reduction_percentage', 0):.2f}%",
        ">",
        "> **Protection overrides:** "
        f"{summary.get('protection_overrides', 0)}",
        "",
    ]

    for classification in (
        "MUST_TEST",
        "RECOMMENDED",
        "OPTIONAL",
        "EXCLUDE",
    ):
        matching = [
            row
            for row in results
            if row["classification"]
            == classification
        ]

        lines.extend(
            [
                "---",
                "",
                f"## {classification}",
                "",
            ]
        )

        if not matching:
            lines.extend(
                [
                    f"> No {classification} test cases.",
                    "",
                ]
            )
            continue

        for row in matching:
            flags = row.get(
                "protection_flags",
                [],
            )

            flag_text = (
                ", ".join(flags)
                if flags
                else "None"
            )

            reasons = row.get(
                "reasons",
                [],
            )

            reason_text = (
                "; ".join(
                    reasons[:4]
                )
                if reasons
                else "No explanation available"
            )

            lines.extend(
                [
                    f"> ### `{row['test_case_id']}` — "
                    f"{_display(row.get('test_name'))}",
                    ">",
                    f"> **Module:** `{_display(row.get('module_id'))}`",
                    ">",
                    f"> **Tier:** `{row.get('tier', 'TIER_3')}`",
                    ">",
                    f"> **Score:** `{row.get('composite_score', 0):.2f}`",
                    ">",
                    f"> **Risk band:** `{row.get('risk_band', 'LOW')}`",
                    ">",
                    f"> **Protection:** {flag_text}",
                    ">",
                    f"> **Reason:** {reason_text}",
                    "",
                ]
            )

    return "\n".join(lines)


def _load_weights(
    rows: list[dict[str, Any]],
) -> dict[str, float]:
    configured: dict[str, float] = {}

    for row in rows:
        factor = _value(
            row,
            "Factor",
            "Factor_Name",
            "Scoring_Factor",
        )

        weight_value = _value(
            row,
            "Weight",
            "Factor_Weight",
        )

        if not factor or weight_value is None:
            continue

        factor_name = _normalized(
            factor
        )

        if factor_name not in DEFAULT_WEIGHTS:
            continue

        weight = _to_float(
            weight_value
        )

        if weight > 1:
            weight /= 100

        if weight >= 0:
            configured[
                factor_name
            ] = weight

    weights = DEFAULT_WEIGHTS.copy()
    weights.update(configured)

    total = sum(
        weights.values()
    )

    if total <= 0:
        return DEFAULT_WEIGHTS.copy()

    return {
        factor: weight / total
        for factor, weight
        in weights.items()
    }


def _load_thresholds(
    rows: list[dict[str, Any]],
) -> dict[str, float]:
    thresholds = (
        DEFAULT_THRESHOLDS.copy()
    )

    for row in rows:
        classification = _value(
            row,
            "Classification",
            "Risk_Classification",
            "Category",
            "Decision",
        )

        minimum_score = _value(
            row,
            "Minimum_Score",
            "Min_Score",
            "Threshold",
            "Lower_Bound",
        )

        if (
            classification is None
            or minimum_score is None
        ):
            continue

        normalized_classification = (
            _normalized(
                classification
            )
        )

        if (
            normalized_classification
            not in thresholds
        ):
            continue

        thresholds[
            normalized_classification
        ] = _to_float(
            minimum_score,
            default=thresholds[
                normalized_classification
            ],
        )

    return thresholds


def _classification_from_score(
    score: float,
    thresholds: dict[str, float],
) -> str:
    for classification in (
        "MUST_TEST",
        "RECOMMENDED",
        "OPTIONAL",
        "EXCLUDE",
    ):
        minimum_score = thresholds.get(
            classification,
            DEFAULT_THRESHOLDS[
                classification
            ],
        )

        if score >= minimum_score:
            return classification

    return "EXCLUDE"


def _change_impact_factor(
    test_case_id: str,
    direct_test_ids: set[str],
    downstream_test_ids: set[str],
) -> float:
    if test_case_id in direct_test_ids:
        return 1.00

    if test_case_id in downstream_test_ids:
        return 0.70

    return 0.00


def _risk_band(
    score: float,
) -> str:
    if score >= 80:
        return "VERY_HIGH"

    if score >= 60:
        return "HIGH"

    if score >= 40:
        return "MEDIUM"

    return "LOW"


def _classification_order(
    classification: str,
) -> int:
    return {
        "MUST_TEST": 0,
        "RECOMMENDED": 1,
        "OPTIONAL": 2,
        "EXCLUDE": 3,
    }.get(
        classification,
        99,
    )


def _normalize_tier(
    value: Any,
) -> str:
    normalized = _normalized(
        value
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
        normalized or "TIER_3",
    )


def _string_set(
    values: Any,
) -> set[str]:
    if not values:
        return set()

    if isinstance(
        values,
        dict,
    ):
        values = values.keys()

    if isinstance(
        values,
        str,
    ):
        values = [values]

    return {
        str(value).strip()
        for value in values
        if value is not None
        and str(value).strip()
    }


def _value(
    row: dict[str, Any],
    *possible_names: str,
) -> Any:
    if not row:
        return None

    normalized_row = {
        _normalize_header(key): value
        for key, value
        in row.items()
    }

    for name in possible_names:
        normalized_name = (
            _normalize_header(name)
        )

        if normalized_name in normalized_row:
            return normalized_row[
                normalized_name
            ]

    return None


def _normalize_header(
    value: Any,
) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
    )


def _normalized(
    value: Any,
) -> str:
    return (
        str(value or "")
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )


def _first_non_empty(
    *values: Any,
) -> Any:
    for value in values:
        if value is not None and value != "":
            return value

    return None


def _display(
    value: Any,
) -> str:
    if value is None or value == "":
        return "Not available"

    return str(value)


def _to_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (
        TypeError,
        ValueError,
    ):
        return default

# A2A: Specialist boundary. The Master Orchestrator calls this handler with a
# serializable A2A envelope. The specialist never owns Jira/Excel connectivity.
def handle_a2a_request(request: A2ARequest) -> A2AResponse:

    try:

        data = validate_message(
            request,
            receiver='Decision Engine / Risk Scoring Agent',
            message_types={
                'SCORING_REQUEST',
                "AGENT_QUERY",
            },
        )

        if request.message_type == "AGENT_QUERY":
            return make_response(
                request,
                sender='Decision Engine / Risk Scoring Agent',
                data=answer_agent_question(
                    question=str(data.get("question") or ""),
                    context=data.get(
                        "agent_context",
                        data,
                    ),
                ),
            )

        result = calculate_test_selection(
            source_data=data.get(
                "source_data",
                {},
            ),
            change_impact=data.get(
                "change_impact",
                {},
            ),
            criticality=data.get(
                "criticality",
                {},
            ),
            history=data.get(
                "history",
                {},
            ),
            policy=data.get(
                "policy",
                {},
            ),
        )

        return make_response(
            request,
            sender='Decision Engine / Risk Scoring Agent',
            data=result,
        )

    except Exception as exc:

        trace_error(
            "SCORING_AGENT_FAILED",
            agent="Decision Engine / Risk Scoring Agent",
            error=exc,
            release_id=request.release_id,
        )

        raise

def answer_agent_question(
    question: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Answer specialist questions only from orchestrator-supplied context.

    A2A: No Jira, Excel, filesystem, or external-service reads are allowed here.
    """
    if not isinstance(context, dict):
        raise TypeError("context must be the orchestrator-supplied agent context.")
    question = str(question or "").strip()
    if not question:
        raise ValueError("question is required.")
    log_event(
    "SCORING_AGENT_QUERY",
    agent="Decision Engine / Risk Scoring Agent",
    stage="SCORING",
    status="SUCCESS",
    question=question,
    )
    return {
        "status": "success",
        "agent": 'Decision Engine / Risk Scoring Agent',
        "question": question,
        "context": context,
        "markdown": _agent_question_markdown(question, context),
    }


def _agent_question_markdown(question: str, context: dict[str, Any]) -> str:
    import json
    output = context.get("agent_output", context)
    return "\n".join([
        f"# {'Decision Engine / Risk Scoring Agent'}",
        "",
        f"**Question:** {question}",
        "",
        "> Answer grounded in the Master Orchestrator's current specialist context.",
        "",
        "## Specialist Context",
        "",
        "```json",
        json.dumps(output, indent=2, default=str),
        "```",
    ])
