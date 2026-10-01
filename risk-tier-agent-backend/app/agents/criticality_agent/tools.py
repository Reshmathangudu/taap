# #old_criticality_agent/tools.py
# from __future__ import annotations

# from app.observability.logger import (
#     log_event,
#     trace_error,
# )

# from app.observability.audit import audit_event

# from typing import Any

# from app.models import A2ARequest, A2AResponse
# from app.services.a2a import make_response, validate_message

# from app.utils.helpers import is_yes


# # Criticality factors are evaluated on a 1-to-5 scale.
# DEFAULT_FACTOR_WEIGHTS: dict[str, float] = {
#     "REGULATORY_SCORE": 0.30,
#     "FINANCIAL_SCORE": 0.25,
#     "CUSTOMER_SCORE": 0.20,
#     "SLA_SCORE": 0.15,
#     "INCIDENT_SCORE": 0.10,
# }


# # Minimum score required for each tier.
# # These thresholds produce the expected tier assignments in the current model:
# # TIER_1 >= 4.50, TIER_2 >= 3.25, TIER_3 >= 2.00.
# DEFAULT_TIER_THRESHOLDS: dict[str, float] = {
#     "TIER_1": 4.50,
#     "TIER_2": 3.25,
#     "TIER_3": 2.00,
#     "TIER_4": 0.00,
# }


# # Stored as fractions for downstream calculations.
# DEFAULT_MINIMUM_COVERAGE: dict[str, float] = {
#     "TIER_1": 1.00,
#     "TIER_2": 0.70,
#     "TIER_3": 0.50,
#     "TIER_4": 0.20,
# }


# # Logical inputs supplied by the Master Orchestrator.
# # Legacy workbook-style keys are accepted during transition.
# REQUIRED_INPUT_KEYS: tuple[str, ...] = (
#     "modules",
#     "test_cases",
# )

# OPTIONAL_INPUT_KEYS: tuple[str, ...] = (
#     "criticality_factors",
#     "tier_change_log",
# )

# INPUT_KEY_ALIASES: dict[str, tuple[str, ...]] = {
#     "modules": (
#         "modules",
#         "00_Modules",
#     ),
#     "test_cases": (
#         "test_cases",
#         "06_Test_Cases",
#     ),
#     "criticality_factors": (
#         "criticality_factors",
#         "A2_Criticality_Factors",
#     ),
#     "tier_change_log": (
#         "tier_change_log",
#         "A2_Tier_Change_Log",
#     ),
# }



# def _resolve_source_key(
#     source_data: dict[str, list[dict[str, Any]]],
#     logical_key: str,
# ) -> str:
#     """
#     Resolve a logical orchestrator input to the actual key present in source_data.

#     The logical keys are the preferred names. Legacy workbook-style keys are
#     accepted so the orchestrator can transition gradually.
#     """

#     for candidate in INPUT_KEY_ALIASES.get(
#         logical_key,
#         (logical_key,),
#     ):
#         if candidate in source_data:
#             return candidate

#     return ""


# def _rows(
#     source_data: dict[str, list[dict[str, Any]]],
#     input_name: str,
# ) -> list[dict[str, Any]]:
#     """Return input rows supplied by the Master Orchestrator."""
#     source_key = _resolve_source_key(
#         source_data,
#         input_name,
#     )

#     if not source_key:
#         raise KeyError(
#             f"Master Orchestrator did not provide required input "
#             f"{input_name!r}."
#         )

#     rows = source_data[source_key]

#     if not isinstance(rows, list):
#         raise TypeError(
#             f"Input {input_name!r} must be provided as a list of rows."
#         )

#     return rows


# def _optional_rows(
#     source_data: dict[str, list[dict[str, Any]]],
#     input_name: str,
# ) -> list[dict[str, Any]]:
#     """Return optional input rows, or an empty list when omitted."""
#     source_key = _resolve_source_key(
#         source_data,
#         input_name,
#     )

#     if not source_key:
#         return []

#     rows = source_data[source_key]

#     if not isinstance(rows, list):
#         raise TypeError(
#             f"Optional input {input_name!r} must be provided as a list of rows."
#         )

#     return rows




# def validate_criticality_business_rules(
#     context: dict[str, Any],
# ) -> dict[str, Any]:
#     """Validate BR-CRIT-01..04 using authoritative Criticality output.

#     BR-CRIT-01: weighted factor scoring determines a Tier 1-4 calculation.
#     BR-CRIT-02: every test inherits the final tier of its mapped module.
#     BR-CRIT-03: Tier 1 requires 100% coverage and Tier 2 at least 70%;
#                 Tier 3/4 coverage remains risk/configuration based.
#     BR-CRIT-04: qualifying production incidents escalate immediately;
#                 de-escalation requires an approved change record.
#     """
#     result = get_criticality_analysis(context)

#     assignments = result.get("module_assignments", {})
#     test_tags = result.get("test_tags", {})
#     tier_counts = result.get("agent_output", {}).get(
#         "tier_counts",
#         {},
#     )

#     br01_failures: list[str] = []
#     for module_id, assignment in assignments.items():
#         tier = _normalize_tier(assignment.get("Tier"))
#         score = assignment.get("Criticality_Score")
#         if tier not in {"TIER_1", "TIER_2", "TIER_3", "TIER_4"}:
#             br01_failures.append(
#                 f"{module_id}: invalid final tier {tier!r}"
#             )
#         if score is None:
#             br01_failures.append(
#                 f"{module_id}: missing weighted criticality score"
#             )

#     br02_failures: list[str] = []
#     for test_case_id, tag in test_tags.items():
#         module_id = str(tag.get("module_id") or "").strip()
#         inherited_tier = _normalize_tier(tag.get("tier"))
#         module_tier = _normalize_tier(
#             assignments.get(module_id, {}).get("Tier")
#         )
#         if not module_id or module_id not in assignments:
#             br02_failures.append(
#                 f"{test_case_id}: mapped module {module_id!r} not found"
#             )
#         elif inherited_tier != module_tier:
#             br02_failures.append(
#                 f"{test_case_id}: inherited {inherited_tier}, "
#                 f"module {module_id} is {module_tier}"
#             )

#     br03_failures: list[str] = []
#     for module_id, assignment in assignments.items():
#         tier = _normalize_tier(assignment.get("Tier"))
#         coverage = float(
#             assignment.get(
#                 "Minimum_Coverage",
#                 0.0,
#             )
#             or 0.0
#         )
#         if tier == "TIER_1" and coverage < 1.0:
#             br03_failures.append(
#                 f"{module_id}: Tier 1 coverage {coverage:.2%} < 100%"
#             )
#         elif tier == "TIER_2" and coverage < 0.70:
#             br03_failures.append(
#                 f"{module_id}: Tier 2 coverage {coverage:.2%} < 70%"
#             )

#     br04_failures: list[str] = []
#     for module_id, assignment in assignments.items():
#         source = str(
#             assignment.get("Tier_Source") or ""
#         ).strip().upper()
#         override = assignment.get("Tier_Change_Record") or {}
#         if source == "TIER_CHANGE_LOG_APPROVED_DEESCALATION":
#             status = _normalized(
#                 _first_non_empty(
#                     _value(override, "Approval_Status", "Approval Status"),
#                     _value(override, "Status"),
#                     "",
#                 )
#             )
#             if status != "APPROVED":
#                 br04_failures.append(
#                     f"{module_id}: de-escalation lacks APPROVED status"
#                 )

#     validation = {
#         "BR-CRIT-01": {
#             "status": "PASS" if not br01_failures else "FAIL",
#             "failures": br01_failures,
#         },
#         "BR-CRIT-02": {
#             "status": "PASS" if not br02_failures else "FAIL",
#             "failures": br02_failures,
#         },
#         "BR-CRIT-03": {
#             "status": "PASS" if not br03_failures else "FAIL",
#             "failures": br03_failures,
#         },
#         "BR-CRIT-04": {
#             "status": "PASS" if not br04_failures else "FAIL",
#             "failures": br04_failures,
#         },
#     }

#     lines = [
#         "# Criticality Business-Rule Validation",
#         "",
#         f"**Release:** `{str(release_id or '').strip().upper()}`",
#         "",
#         "| Rule | Status | Details |",
#         "|---|---|---|",
#     ]

#     rule_descriptions = {
#         "BR-CRIT-01": "Weighted factor scoring produces a valid Tier 1-4 assignment.",
#         "BR-CRIT-02": "Every test inherits its mapped module's final tier.",
#         "BR-CRIT-03": "Tier 1 = 100% coverage; Tier 2 >= 70%; Tier 3/4 are risk-based.",
#         "BR-CRIT-04": "Production-incident escalation is immediate; de-escalation requires approval.",
#     }

#     for rule_name, rule_result in validation.items():
#         details = rule_descriptions[rule_name]
#         if rule_result["failures"]:
#             details += " Failures: " + "; ".join(
#                 rule_result["failures"][:8]
#             )
#         lines.append(
#             f"| `{rule_name}` | **{rule_result['status']}** | {details} |"
#         )

#     lines.extend(
#         [
#             "",
#             "## Tier Summary",
#             "",
#             f"- Tier 1 modules: {tier_counts.get('TIER_1', 0)}",
#             f"- Tier 2 modules: {tier_counts.get('TIER_2', 0)}",
#             f"- Tier 3 modules: {tier_counts.get('TIER_3', 0)}",
#             f"- Tier 4 modules: {tier_counts.get('TIER_4', 0)}",
#         ]
#     )

#     output = dict(result)
#     output["validation"] = validation
#     output["validation_markdown"] = "\n".join(lines)
#     return output


# def classify_application_criticality(
#     source_data: dict[
#         str,
#         list[dict[str, Any]],
#     ],
# ) -> dict[str, Any]:

#     log_event(
#         "CRITICALITY_ANALYSIS_STARTED",
#         agent="Application Criticality Classification Agent",
#         stage="CRITICALITY",
#         status="STARTED",
#     )
    
#     """
#     Generate module tier assignments and inherited test-case tier tags.

#     The Master Orchestrator must supply all input rows through
#     ``source_data``. This agent does not open or read the orchestrator inputs directly.

#     Required source_data keys:
#     - modules
#     - test_cases

#     Optional compatibility keys:
#     - criticality_factors
#     - tier_change_log

#     In the Jira-first design, factor scores are read directly from the Module
#     work item fields. If optional legacy factor rows are supplied, they can
#     override/fill those values through the existing compatibility logic.
#     """

#     _validate_source_data(
#         source_data
#     )

#     modules = _rows(
#         source_data,
#         "modules",
#     )
#     test_cases = _rows(
#         source_data,
#         "test_cases",
#     )

#     log_event(
#     "CRITICALITY_INPUTS_LOADED",
#     agent="Application Criticality Classification Agent",
#     stage="CRITICALITY",
#     status="SUCCESS",
#     modules=len(modules),
#     test_cases=len(test_cases),
#     )
#     # Criticality scores now live directly on the Jira Module work items.
#     # Legacy criticality-factor rows are accepted when supplied, but are optional.
#     criticality_rows = _optional_rows(
#         source_data,
#         "criticality_factors",
#     )

#     # Tier-change history is optional in the Jira-first design. When it is not
#     # supplied, no manual tier override is applied and calculated tiers are used.
#     tier_change_log = _optional_rows(
#         source_data,
#         "tier_change_log",
#     )

#     module_lookup = {
#         str(module_id).strip(): row
#         for row in modules
#         if (
#             module_id := _value(
#                 row,
#                 "Module_ID",
#                 "Module ID",
#                 "ModuleId",
#             )
#         )
#     }

#     factor_weights = _load_factor_weights(
#         criticality_rows
#     )
#     tier_thresholds = _load_tier_thresholds(
#         criticality_rows
#     )
#     latest_tier_overrides = (
#         _load_latest_tier_overrides(
#             tier_change_log
#         )
#     )
#     factor_rows_by_module = (
#         _group_factor_rows_by_module(
#             criticality_rows
#         )
#     )

#     assignments: dict[str, dict[str, Any]] = {}

#     all_module_ids = set(module_lookup)
#     all_module_ids.update(factor_rows_by_module)

#     for module_id in sorted(all_module_ids):
#         module = module_lookup.get(module_id, {})
#         factor_row = factor_rows_by_module.get(
#             module_id,
#             {},
#         )

#         factor_scores = _extract_factor_scores(
#             module=module,
#             factor_row=factor_row,
#             factor_weights=factor_weights,
#         )

#         criticality_score = _calculate_weighted_score(
#             factor_scores=factor_scores,
#             factor_weights=factor_weights,
#         )

#         calculated_tier = _score_to_tier(
#             criticality_score,
#             tier_thresholds,
#         )

#         override = latest_tier_overrides.get(
#             module_id
#         )

#         final_tier = calculated_tier
#         tier_source = "CALCULATED"

#         # BR-CRIT-04: a qualifying production incident immediately escalates
#         # the module. In the Jira-first model, the highest incident score (5)
#         # is treated as the qualifying severe-production-incident signal.
#         # An explicit incident/severity flag is also accepted when present.
#         incident_escalation = _has_qualifying_production_incident(
#             module=module,
#             factor_row=factor_row,
#             factor_scores=factor_scores,
#         )

#         if incident_escalation:
#             final_tier = "TIER_1"
#             tier_source = "PRODUCTION_INCIDENT_ESCALATION"

#         if override:
#             override_tier = _value(
#                 override,
#                 "New_Tier",
#                 "Assigned_Tier",
#                 "Final_Tier",
#                 "Tier",
#             )

#             if override_tier:
#                 normalized_override = _normalize_tier(override_tier)
#                 approval_status = _normalized(
#                     _first_non_empty(
#                         _value(override, "Approval_Status", "Approval Status"),
#                         _value(override, "Status"),
#                         "",
#                     )
#                 )

#                 # Escalation may be applied immediately. De-escalation is
#                 # permitted only with an explicit approved governance record.
#                 if _tier_rank(normalized_override) < _tier_rank(final_tier):
#                     final_tier = normalized_override
#                     tier_source = "TIER_CHANGE_LOG_ESCALATION"
#                 elif (
#                     _tier_rank(normalized_override) > _tier_rank(final_tier)
#                     and approval_status == "APPROVED"
#                     and not incident_escalation
#                 ):
#                     final_tier = normalized_override
#                     tier_source = "TIER_CHANGE_LOG_APPROVED_DEESCALATION"

#         minimum_coverage = (
#             _minimum_coverage_for_tier(
#                 tier=final_tier,
#                 configuration=criticality_rows,
#             )
#         )

#         assignments[module_id] = {
#             "Module_ID": module_id,
#             "Module_Name": _value(
#                 module,
#                 "Module_Name",
#                 "Module Name",
#                 "Name",
#             ),
#             "Factor_Scores": factor_scores,
#             "Criticality_Score": round(
#                 criticality_score,
#                 2,
#             ),
#             "Calculated_Tier": calculated_tier,
#             "Tier": final_tier,
#             "Tier_Source": tier_source,
#             "Minimum_Coverage": minimum_coverage,
#             "Minimum_Coverage_Percent": round(
#                 minimum_coverage * 100,
#                 2,
#             ),
#             "Tier_Change_Record": override,
#             "Incident_Escalation_Window_Releases": 2 if incident_escalation else 0,
#             "Business_Rules": {
#                 "BR-CRIT-01": "Weighted regulatory/compliance, revenue, customer, SLA, and incident factors determine Tier 1-4.",
#                 "BR-CRIT-02": "Every test inherits its mapped module tier; a lower test tier is prohibited.",
#                 "BR-CRIT-03": "Tier 1 requires 100% regression coverage; Tier 2 requires at least 70%; Tier 3/4 remain risk-based.",
#                 "BR-CRIT-04": "Qualifying Sev-1/Sev-2 production incidents escalate immediately; de-escalation requires approved QA/Architecture Lead governance.",
#             },
#         }
#         log_event(
#                 "BR_CRIT_01_APPLIED",
#                 agent="Application Criticality Classification Agent",
#                 rule_id="BR-CRIT-01",
#                 classified_modules=len(assignments),
#         )

#     test_tags: dict[str, dict[str, Any]] = {}

#     for test_case in test_cases:
#         test_case_id = _value(
#             test_case,
#             "Test_Case_ID",
#             "Test Case ID",
#             "TestCase_ID",
#             "Test_ID",
#             "TC_ID",
#         )

#         if not test_case_id:
#             continue

#         module_id = _value(
#             test_case,
#             "Module_ID",
#             "Module ID",
#             "ModuleId",
#         )

#         normalized_test_case_id = str(
#             test_case_id
#         ).strip()
#         normalized_module_id = str(
#             module_id or ""
#         ).strip()

#         if not normalized_module_id or normalized_module_id not in assignments:
#             raise ValueError(
#                 f"BR-CRIT-02 violation: test case {normalized_test_case_id!r} "
#                 f"does not resolve to a classified module {normalized_module_id!r}."
#             )

#         module_assignment = assignments[normalized_module_id]

#         tier = module_assignment["Tier"]

#         explicit_floor = _first_non_empty(
#             _value(
#                 test_case,
#                 "Tier_Floor_Protection",
#                 "Tier Floor Protection",
#             ),
#             _value(
#                 test_case,
#                 "Critical_Test",
#                 "Critical Test",
#             ),
#             _value(
#                 test_case,
#                 "Always_Execute",
#                 "Always Execute",
#             ),
#             _value(
#                 test_case,
#                 "Mandatory",
#                 "Is_Mandatory",
#             ),
#         )

#         tier_floor_protection = (
#             is_yes(explicit_floor)
#             or tier == "TIER_1"
#         )

#         test_tags[normalized_test_case_id] = {
#             "test_case_id": normalized_test_case_id,
#             "test_name": _value(
#                 test_case,
#                 "Test_Name",
#                 "Test Name",
#                 "Test_Case_Name",
#                 "Name",
#             ),
#             "module_id": normalized_module_id,
#             "tier": tier,
#             "tier_floor_protection": (
#                 tier_floor_protection
#             ),
#             "minimum_coverage": (
#                 module_assignment.get(
#                     "Minimum_Coverage",
#                     0.50,
#                 )
#             ),
#             "minimum_coverage_percent": (
#                 module_assignment.get(
#                     "Minimum_Coverage_Percent",
#                     50.0,
#                 )
#             ),
#             "criticality_score": (
#                 module_assignment.get(
#                     "Criticality_Score",
#                     2.50,
#                 )
#             ),
#             "tier_source": (
#                 module_assignment.get(
#                     "Tier_Source",
#                     "DEFAULT",
#                 )
#             ),
#         }

#         log_event(
#             "BR_CRIT_02_APPLIED",
#             agent="Application Criticality Classification Agent",
#             rule_id="BR-CRIT-02",
#             classified_tests=len(test_tags),
#         )  
   
#     tier_counts = {
#         tier: sum(
#             1
#             for assignment in assignments.values()
#             if assignment.get("Tier") == tier
#         )
#         for tier in (
#             "TIER_1",
#             "TIER_2",
#             "TIER_3",
#             "TIER_4",
#         )
#     }

#     incident_escalations = sum(
#     1
#     for assignment in assignments.values()
#     if assignment.get("Tier_Source")
#     == "PRODUCTION_INCIDENT_ESCALATION"
#     )

#     log_event(
#         "BR_CRIT_04_APPLIED",
#         agent="Application Criticality Classification Agent",
#         rule_id="BR-CRIT-04",
#         escalated_modules=incident_escalations,
#     )

#     protected_test_ids = sorted(
#         test_case_id
#         for test_case_id, tag in test_tags.items()
#         if tag.get("tier_floor_protection")
#     )
#     log_event(
#     "BR_CRIT_03_APPLIED",
#     agent="Application Criticality Classification Agent",
#     rule_id="BR-CRIT-03",
#     protected_tests=len(protected_test_ids),
#     )

#     result: dict[str, Any] = {
#         "module_assignments": assignments,
#         "test_tags": test_tags,
#         "factor_weights": factor_weights,
#         "tier_thresholds": tier_thresholds,
#         "tier_change_log": tier_change_log,
#         "summary": {
#             "total_modules": len(assignments),
#             "total_test_cases": len(test_tags),
#             "tier_1_modules": tier_counts["TIER_1"],
#             "tier_2_modules": tier_counts["TIER_2"],
#             "tier_3_modules": tier_counts["TIER_3"],
#             "tier_4_modules": tier_counts["TIER_4"],
#             "tier_floor_protected_tests": len(
#                 protected_test_ids
#             ),
#             "tier_overrides_applied": sum(
#                 1
#                 for assignment
#                 in assignments.values()
#                 if assignment.get("Tier_Source")
#                 == "TIER_CHANGE_LOG"
#             ),
#         },
#         "agent_output": {
#             "module_assignments": assignments,
#             "test_tags": test_tags,
#             "protected_test_ids": protected_test_ids,
#             "tier_counts": tier_counts,
#         },
#     }

#     log_event(
#     "CRITICALITY_ANALYSIS_COMPLETED",
#     agent="Application Criticality Classification Agent",
#     stage="CRITICALITY",
#     status="SUCCESS",
#     total_modules=len(assignments),
#     total_tests=len(test_tags),
#     )

#     audit_event(
#         "CRITICALITY_ANALYSIS_COMPLETED",
#         agent="Application Criticality Classification Agent",
#         message=(
#             f"Classified {len(assignments)} modules and "
#             f"{len(test_tags)} test cases."
#         ),
#         details={
#             "tier_1": tier_counts["TIER_1"],
#             "tier_2": tier_counts["TIER_2"],
#             "tier_3": tier_counts["TIER_3"],
#             "tier_4": tier_counts["TIER_4"],
#         },
#     )

#     result["markdown"] = (
#         format_criticality_cards(result)
#     )

#     return result



# def _validate_source_data(
#     source_data: dict[
#         str,
#         list[dict[str, Any]],
#     ],
# ) -> None:
#     """
#     Validate that the orchestrator supplied the Jira-first required inputs.

#     ``modules`` and ``test_cases`` are required. ``criticality_factors`` and
#     ``tier_change_log`` are optional compatibility inputs.
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
#         if not _resolve_source_key(
#             source_data,
#             input_name,
#         )
#     ]

#     if missing_inputs:
#         raise ValueError(
#             "Criticality Agent is missing required "
#             "orchestrator inputs: "
#             f"{missing_inputs}"
#         )

#     invalid_inputs = []
#     for input_name in (*REQUIRED_INPUT_KEYS, *OPTIONAL_INPUT_KEYS):
#         source_key = _resolve_source_key(
#             source_data,
#             input_name,
#         )
#         if source_key and not isinstance(
#             source_data[source_key],
#             list,
#         ):
#             invalid_inputs.append(source_key)

#     if invalid_inputs:
#         raise TypeError(
#             "Criticality Agent expected input "
#             "rows as lists for: "
#             f"{invalid_inputs}"
#         )

# def _group_factor_rows_by_module(
#     rows: list[dict[str, Any]],
# ) -> dict[str, dict[str, Any]]:
#     grouped: dict[str, dict[str, Any]] = {}

#     for row in rows:
#         module_id = _value(
#             row,
#             "Module_ID",
#             "Module ID",
#             "ModuleId",
#         )

#         if module_id:
#             grouped[str(module_id).strip()] = row

#     return grouped


# def _extract_factor_scores(
#     module: dict[str, Any],
#     factor_row: dict[str, Any],
#     factor_weights: dict[str, float],
# ) -> dict[str, float]:
#     scores: dict[str, float] = {}

#     aliases: dict[str, tuple[str, ...]] = {
#         "REGULATORY_SCORE": (
#             "Regulatory_Score",
#             "Regulatory Score",
#             "Regulatory",
#             "Regulatory_Impact",
#         ),
#         "FINANCIAL_SCORE": (
#             "Financial_Score",
#             "Financial Score",
#             "Financial",
#             "Financial_Impact",
#             "Revenue_Impact",
#         ),
#         "CUSTOMER_SCORE": (
#             "Customer_Score",
#             "Customer Score",
#             "Customer",
#             "Customer_Impact",
#             "Customer_Exposure",
#         ),
#         "SLA_SCORE": (
#             "SLA_Score",
#             "SLA Score",
#             "SLA",
#             "SLA_Impact",
#             "Availability_Requirement",
#         ),
#         "INCIDENT_SCORE": (
#             "Incident_Score",
#             "Incident Score",
#             "Incident",
#             "Incident_Impact",
#             "Production_Incidents",
#         ),
#     }

#     for factor_name in factor_weights:
#         names = aliases.get(
#             factor_name,
#             (
#                 factor_name,
#                 _friendly_factor_name(
#                     factor_name
#                 ),
#             ),
#         )

#         raw_value = _value(
#             factor_row,
#             *names,
#         )

#         if raw_value is None:
#             raw_value = _value(
#                 module,
#                 *names,
#             )

#         scores[factor_name] = round(
#             _value_to_five_point_score(
#                 raw_value
#             ),
#             2,
#         )

#     return scores


# def _calculate_weighted_score(
#     factor_scores: dict[str, float],
#     factor_weights: dict[str, float],
# ) -> float:
#     total_weight = sum(
#         factor_weights.values()
#     )

#     if total_weight <= 0:
#         return 0.0

#     weighted_total = sum(
#         factor_scores.get(
#             factor_name,
#             0.0,
#         )
#         * weight
#         for factor_name, weight
#         in factor_weights.items()
#     )

#     return weighted_total / total_weight


# def _load_factor_weights(
#     rows: list[dict[str, Any]],
# ) -> dict[str, float]:
#     configured_weights: dict[str, float] = {}

#     for row in rows:
#         factor_name = _value(
#             row,
#             "Factor",
#             "Factor_Name",
#             "Criticality_Factor",
#         )
#         weight_value = _value(
#             row,
#             "Weight",
#             "Factor_Weight",
#         )

#         if not factor_name or weight_value is None:
#             continue

#         normalized_factor = _canonical_factor_name(
#             factor_name
#         )

#         if normalized_factor not in (
#             DEFAULT_FACTOR_WEIGHTS
#         ):
#             continue

#         weight = _to_float(
#             weight_value,
#             default=0.0,
#         )

#         if weight > 1:
#             weight /= 100

#         if weight > 0:
#             configured_weights[
#                 normalized_factor
#             ] = weight

#     weights = DEFAULT_FACTOR_WEIGHTS.copy()
#     weights.update(configured_weights)

#     total = sum(weights.values())

#     if total <= 0:
#         return DEFAULT_FACTOR_WEIGHTS.copy()

#     return {
#         factor: weight / total
#         for factor, weight
#         in weights.items()
#     }


# def _load_tier_thresholds(
#     rows: list[dict[str, Any]],
# ) -> dict[str, float]:
#     thresholds = (
#         DEFAULT_TIER_THRESHOLDS.copy()
#     )

#     for row in rows:
#         tier = _value(
#             row,
#             "Tier",
#             "Assigned_Tier",
#         )
#         minimum_score = _value(
#             row,
#             "Minimum_Score",
#             "Min_Score",
#             "Threshold",
#         )

#         if not tier or minimum_score is None:
#             continue

#         normalized_tier = _normalize_tier(
#             tier
#         )

#         if normalized_tier in thresholds:
#             thresholds[
#                 normalized_tier
#             ] = _to_float(
#                 minimum_score,
#                 default=thresholds[
#                     normalized_tier
#                 ],
#             )

#     return thresholds


# def _load_latest_tier_overrides(
#     change_log: list[dict[str, Any]],
# ) -> dict[str, dict[str, Any]]:
#     overrides: dict[str, dict[str, Any]] = {}

#     for row in change_log:
#         module_id = _value(
#             row,
#             "Module_ID",
#             "Module ID",
#             "ModuleId",
#         )

#         if not module_id:
#             continue

#         status = _normalized(
#             _first_non_empty(
#                 _value(
#                     row,
#                     "Approval_Status",
#                     "Approval Status",
#                 ),
#                 _value(
#                     row,
#                     "Status",
#                 ),
#                 "ACTIVE",
#             )
#         )

#         if status not in {
#             "ACTIVE",
#             "APPROVED",
#             "CURRENT",
#             "ENABLED",
#         }:
#             continue

#         overrides[str(module_id).strip()] = row

#     return overrides


# def _minimum_coverage_for_tier(
#     tier: str,
#     configuration: list[dict[str, Any]],
# ) -> float:
#     default_value = (
#         DEFAULT_MINIMUM_COVERAGE.get(
#             tier,
#             0.50,
#         )
#     )

#     for row in configuration:
#         row_tier = _value(
#             row,
#             "Tier",
#             "Assigned_Tier",
#         )

#         if not row_tier:
#             continue

#         if _normalize_tier(row_tier) != tier:
#             continue

#         coverage = _value(
#             row,
#             "Minimum_Coverage",
#             "Min_Coverage",
#             "Coverage_Floor",
#         )

#         if coverage is None:
#             continue

#         numeric_coverage = _to_float(
#             coverage,
#             default=default_value,
#         )

#         if numeric_coverage > 1:
#             numeric_coverage /= 100

#         return min(
#             max(numeric_coverage, 0.0),
#             1.0,
#         )

#     return default_value



# def _tier_rank(tier: str) -> int:
#     """Lower rank means higher criticality."""
#     return {
#         "TIER_1": 1,
#         "TIER_2": 2,
#         "TIER_3": 3,
#         "TIER_4": 4,
#     }.get(_normalize_tier(tier), 99)


# def _has_qualifying_production_incident(
#     module: dict[str, Any],
#     factor_row: dict[str, Any],
#     factor_scores: dict[str, float],
# ) -> bool:
#     """Implement BR-CRIT-04 immediate escalation for severe production incidents."""
#     explicit = _first_non_empty(
#         _value(module, "Qualifying_Production_Incident", "Qualifying Production Incident",
#                "Sev1_Production_Incident", "Sev-1 Production Incident"),
#         _value(factor_row, "Qualifying_Production_Incident", "Qualifying Production Incident",
#                "Sev1_Production_Incident", "Sev-1 Production Incident"),
#     )
#     if explicit is not None:
#         return is_yes(explicit)

#     severity = _normalized(_first_non_empty(
#         _value(module, "Incident_Severity", "Incident Severity", "Production_Incident_Severity"),
#         _value(factor_row, "Incident_Severity", "Incident Severity", "Production_Incident_Severity"),
#         "",
#     ))
#     if severity in {"SEV_1", "SEV1", "SEV_2", "SEV2", "P1", "P2", "CRITICAL"}:
#         return True

#     return float(factor_scores.get("INCIDENT_SCORE", 0.0)) >= 5.0

# def _score_to_tier(
#     score: float,
#     thresholds: dict[str, float],
# ) -> str:
#     for tier in (
#         "TIER_1",
#         "TIER_2",
#         "TIER_3",
#         "TIER_4",
#     ):
#         if score >= thresholds.get(
#             tier,
#             DEFAULT_TIER_THRESHOLDS[tier],
#         ):
#             return tier

#     return "TIER_4"


# def _value_to_five_point_score(
#     value: Any,
# ) -> float:
#     """
#     Convert numeric or categorical criticality values to a 1-to-5 score.

#     Important: integer 1 is already a valid 1-to-5 score. It must not
#     be treated as the fraction 1.0 and converted to 5.0.
#     """

#     if value is None or value == "":
#         return 0.0

#     if isinstance(value, bool):
#         return 5.0 if value else 1.0

#     if isinstance(value, (int, float)):
#         numeric = float(value)

#         # Values from 1 through 5 are already on the 1-to-5 scale.
#         if 1 <= numeric <= 5:
#             return numeric

#         # Fractions are strictly below 1.0.
#         if 0 <= numeric < 1:
#             return numeric * 5

#         if 5 < numeric <= 100:
#             return numeric / 20

#         return min(
#             max(numeric, 0.0),
#             5.0,
#         )

#     normalized = _normalized(value)

#     categorical_scores = {
#         "CRITICAL": 5.0,
#         "VERY_HIGH": 5.0,
#         "HIGH": 4.0,
#         "MEDIUM": 3.0,
#         "MODERATE": 3.0,
#         "LOW": 2.0,
#         "VERY_LOW": 1.0,
#         "YES": 5.0,
#         "Y": 5.0,
#         "TRUE": 5.0,
#         "NO": 1.0,
#         "N": 1.0,
#         "FALSE": 1.0,
#     }

#     if normalized in categorical_scores:
#         return categorical_scores[
#             normalized
#         ]

#     try:
#         return _value_to_five_point_score(
#             float(str(value).strip())
#         )
#     except (TypeError, ValueError):
#         return 0.0


# def _canonical_factor_name(
#     value: Any,
# ) -> str:
#     normalized = _normalize_key(value)

#     aliases = {
#         "REGULATORY": "REGULATORY_SCORE",
#         "REGULATORY_IMPACT": "REGULATORY_SCORE",
#         "REGULATORY_SCORE": "REGULATORY_SCORE",
#         "FINANCIAL": "FINANCIAL_SCORE",
#         "FINANCIAL_IMPACT": "FINANCIAL_SCORE",
#         "FINANCIAL_SCORE": "FINANCIAL_SCORE",
#         "REVENUE_IMPACT": "FINANCIAL_SCORE",
#         "CUSTOMER": "CUSTOMER_SCORE",
#         "CUSTOMER_IMPACT": "CUSTOMER_SCORE",
#         "CUSTOMER_SCORE": "CUSTOMER_SCORE",
#         "CUSTOMER_EXPOSURE": "CUSTOMER_SCORE",
#         "SLA": "SLA_SCORE",
#         "SLA_IMPACT": "SLA_SCORE",
#         "SLA_SCORE": "SLA_SCORE",
#         "AVAILABILITY_REQUIREMENT": "SLA_SCORE",
#         "INCIDENT": "INCIDENT_SCORE",
#         "INCIDENT_IMPACT": "INCIDENT_SCORE",
#         "INCIDENT_SCORE": "INCIDENT_SCORE",
#         "PRODUCTION_INCIDENTS": "INCIDENT_SCORE",
#         "BUSINESS_CRITICALITY": "FINANCIAL_SCORE",
#     }

#     return aliases.get(
#         normalized,
#         normalized,
#     )


# def _friendly_factor_name(
#     factor_name: str,
# ) -> str:
#     return factor_name.replace(
#         "_",
#         " ",
#     ).title()


# def _normalize_tier(value: Any) -> str:
#     normalized = _normalized(value)

#     aliases = {
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
#     }

#     return aliases.get(
#         normalized,
#         normalized,
#     )


# def format_criticality_cards(
#     result: dict[str, Any],
# ) -> str:
#     assignments = result.get(
#         "module_assignments",
#         {},
#     )
#     test_tags = result.get(
#         "test_tags",
#         {},
#     )
#     summary = result.get(
#         "summary",
#         {},
#     )

#     lines: list[str] = [
#         "# Application Criticality Classification",
#         "",
#         "## Summary",
#         "",
#         "| Metric | Count |",
#         "|---|---:|",
#         f"| Total modules | {summary.get('total_modules', 0)} |",
#         f"| Total test cases | {summary.get('total_test_cases', 0)} |",
#         f"| Tier 1 modules | {summary.get('tier_1_modules', 0)} |",
#         f"| Tier 2 modules | {summary.get('tier_2_modules', 0)} |",
#         f"| Tier 3 modules | {summary.get('tier_3_modules', 0)} |",
#         f"| Tier 4 modules | {summary.get('tier_4_modules', 0)} |",
#         "| Tier-floor protected tests | "
#         f"{summary.get('tier_floor_protected_tests', 0)} |",
#         "| Tier overrides applied | "
#         f"{summary.get('tier_overrides_applied', 0)} |",
#         "",
#         "---",
#         "",
#         "## Module Tier Assignments",
#         "",
#     ]

#     if assignments:
#         for module_id, assignment in sorted(
#             assignments.items()
#         ):
#             factor_scores = assignment.get(
#                 "Factor_Scores",
#                 {},
#             )

#             lines.extend(
#                 [
#                     f"> ### `{module_id}` — "
#                     f"{_display(assignment.get('Module_Name'))}",
#                     ">",
#                     "> **Criticality score:** "
#                     f"`{assignment.get('Criticality_Score', 0):.2f}` / 5",
#                     ">",
#                     "> **Calculated tier:** "
#                     f"`{assignment.get('Calculated_Tier', 'TIER_4')}`",
#                     ">",
#                     "> **Final tier:** "
#                     f"`{assignment.get('Tier', 'TIER_4')}`",
#                     ">",
#                     "> **Tier source:** "
#                     f"`{assignment.get('Tier_Source', 'CALCULATED')}`",
#                     ">",
#                     "> **Minimum coverage:** "
#                     f"`{assignment.get('Minimum_Coverage_Percent', 0):.0f}%`",
#                     ">",
#                     "> **Factors:** "
#                     + ", ".join(
#                         f"{name}={score:.2f}"
#                         for name, score
#                         in factor_scores.items()
#                     ),
#                     "",
#                 ]
#             )
#     else:
#         lines.extend(
#             [
#                 "> No module assignments were generated.",
#                 "",
#             ]
#         )

#     lines.extend(
#         [
#             "---",
#             "",
#             "## Test Tier Tags",
#             "",
#             "| Test Case | Module | Tier | Score | Protected |",
#             "|---|---|---|---:|---|",
#         ]
#     )

#     for test_case_id, tag in sorted(
#         test_tags.items()
#     ):
#         protected = (
#             "Yes"
#             if tag.get("tier_floor_protection")
#             else "No"
#         )

#         lines.append(
#             f"| `{test_case_id}` "
#             f"| `{tag.get('module_id', '')}` "
#             f"| `{tag.get('tier', 'TIER_3')}` "
#             f"| {tag.get('criticality_score', 0):.2f} "
#             f"| {protected} |"
#         )

#     return "\n".join(lines)


# def _value(
#     row: dict[str, Any],
#     *possible_names: str,
# ) -> Any:
#     if not row:
#         return None

#     normalized_row = {
#         _normalize_header(key): value
#         for key, value in row.items()
#     }

#     for possible_name in possible_names:
#         normalized_name = _normalize_header(
#             possible_name
#         )

#         if normalized_name in normalized_row:
#             return normalized_row[
#                 normalized_name
#             ]

#     return None


# def _normalize_header(value: Any) -> str:
#     return (
#         str(value)
#         .strip()
#         .lower()
#         .replace("_", "")
#         .replace("-", "")
#         .replace(" ", "")
#     )


# def _normalize_key(value: Any) -> str:
#     return (
#         str(value)
#         .strip()
#         .upper()
#         .replace(" ", "_")
#         .replace("-", "_")
#     )


# def _normalized(value: Any) -> str:
#     return _normalize_key(value)


# def _first_non_empty(
#     *values: Any,
# ) -> Any:
#     for value in values:
#         if value is not None and value != "":
#             return value

#     return None


# def _display(value: Any) -> str:
#     if value is None or value == "":
#         return "Not available"

#     return str(value)


# def _to_float(
#     value: Any,
#     default: float = 0.0,
# ) -> float:
#     try:
#         return float(value)
#     except (TypeError, ValueError):
#         return default

# # A2A: Specialist boundary. The Master Orchestrator calls this handler with a
# # serializable A2A envelope. The specialist never owns Jira/Excel connectivity.
# def handle_a2a_request(request: A2ARequest) -> A2AResponse:

#     try:

#         data = validate_message(
#             request,
#             receiver='Application Criticality Classification Agent',
#             message_types={
#                 'CRITICALITY_REQUEST',
#                 "AGENT_QUERY",
#             },
#         )

#         release_id = request.release_id

#         if request.message_type == "AGENT_QUERY":
#             return make_response(
#                 request,
#                 sender='Application Criticality Classification Agent',
#                 data=answer_agent_question(
#                     question=str(data.get("question") or ""),
#                     context=data.get("agent_context", data),
#                 ),
#             )

#         result = classify_application_criticality(
#             source_data=data.get(
#                 "source_data",
#                 {},
#             ),
#         )

#         return make_response(
#             request,
#             sender='Application Criticality Classification Agent',
#             data=result,
#         )

#     except Exception as exc:

#         trace_error(
#             "CRITICALITY_AGENT_FAILED",
#             agent="Application Criticality Classification Agent",
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
#     "CRITICALITY_AGENT_QUERY",
#     agent="Application Criticality Classification Agent",
#     stage="CRITICALITY",
#     status="SUCCESS",
#     question=question,
#     )
#     return {
#         "status": "success",
#         "agent": 'Application Criticality Classification Agent',
#         "question": question,
#         "context": context,
#         "markdown": _agent_question_markdown(question, context),
#     }


# def _agent_question_markdown(question: str, context: dict[str, Any]) -> str:
#     import json
#     output = context.get("agent_output", context)
#     log_event(
#     "CRITICALITY_AGENT_QUERY",
#     agent="Application Criticality Classification Agent",
#     stage="CRITICALITY",
#     status="SUCCESS",
#     question=question,
#     )
#     return "\n".join([
#         f"# {'Application Criticality Classification Agent'}",
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


# # A2A: Conversational entry point must receive the same orchestrator-supplied
# # modules/test_cases block used by the pipeline; it never creates its own Jira client.
# def get_criticality_analysis(context: dict[str, Any]) -> dict[str, Any]:
#     if not isinstance(context, dict):
#         raise TypeError("context must be a dictionary supplied by the Master Orchestrator.")
#     source_data = context.get("source_data", context)
#     if not isinstance(source_data, dict):
#         raise TypeError("Criticality source_data must be a dictionary.")
#     return classify_application_criticality(source_data)


###################################################################################################################################################################
###################################################################################################################################################################
#----------------------------Updated code as per mcp server spider code-------------------



#criticality_agent/tools.py

from __future__ import annotations

from typing import Any

from app.observability.logger import (
    log_event,
    trace_error,
)
from app.observability.audit import audit_event

from app.models import A2ARequest, A2AResponse
from app.services.a2a import make_response, validate_message

from app.utils.helpers import is_yes


# Criticality factors are evaluated on a 1-to-5 scale.
DEFAULT_FACTOR_WEIGHTS: dict[str, float] = {
    "FINANCIAL_SCORE": 0.30,
    "REGULATORY_SCORE": 0.25,
    "CUSTOMER_SCORE": 0.20,
    "SLA_SCORE": 0.15,
    "INCIDENT_SCORE": 0.10,
}


# Minimum score required for each tier.
# These thresholds produce the expected tier assignments in the current model:
# TIER_1 >= 4.50, TIER_2 >= 3.25, TIER_3 >= 2.00.
DEFAULT_TIER_THRESHOLDS: dict[str, float] = {
    "TIER_1": 4.50,
    "TIER_2": 3.25,
    "TIER_3": 2.00,
    "TIER_4": 0.00,
}


# Stored as fractions for downstream calculations.
DEFAULT_MINIMUM_COVERAGE: dict[str, float] = {
    "TIER_1": 1.00,
    "TIER_2": 0.80,
    "TIER_3": 0.50,
    "TIER_4": 0.20,
}


# Logical inputs supplied by the Master Orchestrator.
# Legacy workbook-style keys are accepted during transition.
REQUIRED_INPUT_KEYS: tuple[str, ...] = (
    "modules",
    "test_cases",
)

OPTIONAL_INPUT_KEYS: tuple[str, ...] = (
    "criticality_factors",
    "tier_change_log",
)

INPUT_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "modules": (
        "modules",
        "00_Modules",
    ),
    "test_cases": (
        "test_cases",
        "06_Test_Cases",
    ),
    "criticality_factors": (
        "criticality_factors",
        "A2_Criticality_Factors",
    ),
    "tier_change_log": (
        "tier_change_log",
        "A2_Tier_Change_Log",
    ),
}



def _resolve_source_key(
    source_data: dict[str, list[dict[str, Any]]],
    logical_key: str,
) -> str:
    """
    Resolve a logical orchestrator input to the actual key present in source_data.

    The logical keys are the preferred names. Legacy workbook-style keys are
    accepted so the orchestrator can transition gradually.
    """

    for candidate in INPUT_KEY_ALIASES.get(
        logical_key,
        (logical_key,),
    ):
        if candidate in source_data:
            return candidate

    return ""


def _rows(
    source_data: dict[str, list[dict[str, Any]]],
    input_name: str,
) -> list[dict[str, Any]]:
    """Return input rows supplied by the Master Orchestrator."""
    source_key = _resolve_source_key(
        source_data,
        input_name,
    )

    if not source_key:
        raise KeyError(
            f"Master Orchestrator did not provide required input "
            f"{input_name!r}."
        )

    rows = source_data[source_key]

    if not isinstance(rows, list):
        raise TypeError(
            f"Input {input_name!r} must be provided as a list of rows."
        )

    return rows


def _optional_rows(
    source_data: dict[str, list[dict[str, Any]]],
    input_name: str,
) -> list[dict[str, Any]]:
    """Return optional input rows, or an empty list when omitted."""
    source_key = _resolve_source_key(
        source_data,
        input_name,
    )

    if not source_key:
        return []

    rows = source_data[source_key]

    if not isinstance(rows, list):
        raise TypeError(
            f"Optional input {input_name!r} must be provided as a list of rows."
        )

    return rows


def classify_application_criticality(
    source_data: dict[
        str,
        list[dict[str, Any]],
    ],
) -> dict[str, Any]:
    """
    Generate module tier assignments and inherited test-case tier tags.

    The Master Orchestrator must supply all input rows through
    ``source_data``. This agent does not open or read the orchestrator inputs directly.

    Required source_data keys:
    - modules
    - test_cases

    Optional compatibility keys:
    - criticality_factors
    - tier_change_log

    In the Jira-first design, factor scores are read directly from the Module
    work item fields. If optional legacy factor rows are supplied, they can
    override/fill those values through the existing compatibility logic.
    """
    try:
        log_event(
            "CRITICALITY_ANALYSIS_STARTED",
            agent="Application Criticality Classification Agent",
            stage="CRITICALITY",
            status="STARTED",
        )

        _validate_source_data(
            source_data
        )

        modules = _rows(
            source_data,
            "modules",
        )
        test_cases = _rows(
            source_data,
            "test_cases",
        )
        # Criticality scores now live directly on the Jira Module work items.
        # Legacy criticality-factor rows are accepted when supplied, but are optional.
        criticality_rows = _optional_rows(
            source_data,
            "criticality_factors",
        )

        # Tier-change history is optional in the Jira-first design. When it is not
        # supplied, no manual tier override is applied and calculated tiers are used.
        tier_change_log = _optional_rows(
            source_data,
            "tier_change_log",
        )
        log_event(
            "CRITICALITY_INPUTS_LOADED",
            agent="Application Criticality Classification Agent",
            stage="CRITICALITY",
            status="SUCCESS",
            modules=len(modules),
            test_cases=len(test_cases),
        )

        module_lookup = {
            str(module_id).strip(): row
            for row in modules
            if (
                module_id := _value(
                    row,
                    "Module_ID",
                    "Module ID",
                    "ModuleId",
                )
            )
        }

        factor_weights = _load_factor_weights(
            criticality_rows
        )
        tier_thresholds = _load_tier_thresholds(
            criticality_rows
        )
        latest_tier_overrides = (
            _load_latest_tier_overrides(
                tier_change_log
            )
        )
        factor_rows_by_module = (
            _group_factor_rows_by_module(
                criticality_rows
            )
        )

        assignments: dict[str, dict[str, Any]] = {}

        all_module_ids = set(module_lookup)
        all_module_ids.update(factor_rows_by_module)

        for module_id in sorted(all_module_ids):
            module = module_lookup.get(module_id, {})
            factor_row = factor_rows_by_module.get(
                module_id,
                {},
            )

            factor_scores = _extract_factor_scores(
                module=module,
                factor_row=factor_row,
                factor_weights=factor_weights,
            )

            criticality_score = _calculate_weighted_score(
                factor_scores=factor_scores,
                factor_weights=factor_weights,
            )

            calculated_tier = _score_to_tier(
                criticality_score,
                tier_thresholds,
            )

            override = latest_tier_overrides.get(
                module_id
            )

            final_tier = calculated_tier
            tier_source = "CALCULATED"

            if override:
                override_tier = _value(
                    override,
                    "New_Tier",
                    "Assigned_Tier",
                    "Final_Tier",
                    "Tier",
                )

                if override_tier:
                    final_tier = _normalize_tier(
                        override_tier
                    )
                    tier_source = "TIER_CHANGE_LOG"

            minimum_coverage = (
                _minimum_coverage_for_tier(
                    tier=final_tier,
                    configuration=criticality_rows,
                )
            )

            assignments[module_id] = {
                "Module_ID": module_id,
                "Module_Name": _value(
                    module,
                    "Module_Name",
                    "Module Name",
                    "Name",
                ),
                "Factor_Scores": factor_scores,
                "Criticality_Score": round(
                    criticality_score,
                    2,
                ),
                "Calculated_Tier": calculated_tier,
                "Tier": final_tier,
                "Tier_Source": tier_source,
                "Minimum_Coverage": minimum_coverage,
                "Minimum_Coverage_Percent": round(
                    minimum_coverage * 100,
                    2,
                ),
                "Tier_Change_Record": override,
            }
            log_event(
                "BR_CRIT_01_APPLIED",
                agent="Application Criticality Classification Agent",
                rule_id="BR-CRIT-01",
                classified_modules=len(assignments),
            )

        test_tags: dict[str, dict[str, Any]] = {}

        for test_case in test_cases:
            test_case_id = _value(
                test_case,
                "Test_Case_ID",
                "Test Case ID",
                "TestCase_ID",
                "Test_ID",
                "TC_ID",
            )

            if not test_case_id:
                continue

            module_id = _value(
                test_case,
                "Module_ID",
                "Module ID",
                "ModuleId",
            )

            normalized_test_case_id = str(
                test_case_id
            ).strip()
            normalized_module_id = str(
                module_id or ""
            ).strip()

            module_assignment = assignments.get(
                normalized_module_id,
                {
                    "Tier": "TIER_3",
                    "Criticality_Score": 2.50,
                    "Minimum_Coverage": 0.50,
                    "Minimum_Coverage_Percent": 50.0,
                    "Tier_Source": "DEFAULT",
                },
            )

            tier = module_assignment["Tier"]

            explicit_floor = _first_non_empty(
                _value(
                    test_case,
                    "Tier_Floor_Protection",
                    "Tier Floor Protection",
                ),
                _value(
                    test_case,
                    "Critical_Test",
                    "Critical Test",
                ),
                _value(
                    test_case,
                    "Always_Execute",
                    "Always Execute",
                ),
                _value(
                    test_case,
                    "Mandatory",
                    "Is_Mandatory",
                ),
            )

            tier_floor_protection = (
                is_yes(explicit_floor)
                or tier == "TIER_1"
            )

            test_tags[normalized_test_case_id] = {
                "test_case_id": normalized_test_case_id,
                "test_name": _value(
                    test_case,
                    "Test_Name",
                    "Test Name",
                    "Test_Case_Name",
                    "Name",
                ),
                "module_id": normalized_module_id,
                "tier": tier,
                "tier_floor_protection": (
                    tier_floor_protection
                ),
                "minimum_coverage": (
                    module_assignment.get(
                        "Minimum_Coverage",
                        0.50,
                    )
                ),
                "minimum_coverage_percent": (
                    module_assignment.get(
                        "Minimum_Coverage_Percent",
                        50.0,
                    )
                ),
                "criticality_score": (
                    module_assignment.get(
                        "Criticality_Score",
                        2.50,
                    )
                ),
                "tier_source": (
                    module_assignment.get(
                        "Tier_Source",
                        "DEFAULT",
                    )
                ),
            }
            log_event(
                "BR_CRIT_02_APPLIED",
                agent="Application Criticality Classification Agent",
                rule_id="BR-CRIT-02",
                classified_tests=len(test_tags),
            )

        tier_counts = {
            tier: sum(
                1
                for assignment in assignments.values()
                if assignment.get("Tier") == tier
            )
            for tier in (
                "TIER_1",
                "TIER_2",
                "TIER_3",
                "TIER_4",
            )
        }

        protected_test_ids = sorted(
            test_case_id
            for test_case_id, tag in test_tags.items()
            if tag.get("tier_floor_protection")
        )
        log_event(
            "BR_CRIT_04_APPLIED",
            agent="Application Criticality Classification Agent",
            rule_id="BR-CRIT-04",
            escalated_modules=0,
        )
        log_event(
            "BR_CRIT_03_APPLIED",
            agent="Application Criticality Classification Agent",
            rule_id="BR-CRIT-03",
            protected_tests=len(protected_test_ids),
        )

        result: dict[str, Any] = {
            "module_assignments": assignments,
            "test_tags": test_tags,
            "factor_weights": factor_weights,
            "tier_thresholds": tier_thresholds,
            "tier_change_log": tier_change_log,
            "summary": {
                "total_modules": len(assignments),
                "total_test_cases": len(test_tags),
                "tier_1_modules": tier_counts["TIER_1"],
                "tier_2_modules": tier_counts["TIER_2"],
                "tier_3_modules": tier_counts["TIER_3"],
                "tier_4_modules": tier_counts["TIER_4"],
                "tier_floor_protected_tests": len(
                    protected_test_ids
                ),
                "tier_overrides_applied": sum(
                    1
                    for assignment
                    in assignments.values()
                    if assignment.get("Tier_Source")
                    == "TIER_CHANGE_LOG"
                ),
            },
            "agent_output": {
                "module_assignments": assignments,
                "test_tags": test_tags,
                "protected_test_ids": protected_test_ids,
                "tier_counts": tier_counts,
            },
        }

        result["markdown"] = (
            format_criticality_cards(result)
        )
        log_event(
            "CRITICALITY_ANALYSIS_COMPLETED",
            agent="Application Criticality Classification Agent",
            stage="CRITICALITY",
            status="SUCCESS",
            total_modules=len(assignments),
            total_tests=len(test_tags),
        )

        audit_event(
            "CRITICALITY_ANALYSIS_COMPLETED",
            agent="Application Criticality Classification Agent",
            message=(
                f"Classified {len(assignments)} modules and "
                f"{len(test_tags)} test cases."
            ),
            details={
                "tier_1": tier_counts["TIER_1"],
                "tier_2": tier_counts["TIER_2"],
                "tier_3": tier_counts["TIER_3"],
                "tier_4": tier_counts["TIER_4"],
            },
        )

        return result

    except Exception as exc:
        trace_error(
            "CRITICALITY_AGENT_FAILED",
            agent="Application Criticality Classification Agent",
            error=exc,
        )
        raise



def _validate_source_data(
    source_data: dict[
        str,
        list[dict[str, Any]],
    ],
) -> None:
    """
    Validate that the orchestrator supplied the Jira-first required inputs.

    ``modules`` and ``test_cases`` are required. ``criticality_factors`` and
    ``tier_change_log`` are optional compatibility inputs.
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
        if not _resolve_source_key(
            source_data,
            input_name,
        )
    ]

    if missing_inputs:
        raise ValueError(
            "Criticality Agent is missing required "
            "orchestrator inputs: "
            f"{missing_inputs}"
        )

    invalid_inputs = []
    for input_name in (*REQUIRED_INPUT_KEYS, *OPTIONAL_INPUT_KEYS):
        source_key = _resolve_source_key(
            source_data,
            input_name,
        )
        if source_key and not isinstance(
            source_data[source_key],
            list,
        ):
            invalid_inputs.append(source_key)

    if invalid_inputs:
        raise TypeError(
            "Criticality Agent expected input "
            "rows as lists for: "
            f"{invalid_inputs}"
        )

def _group_factor_rows_by_module(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}

    for row in rows:
        module_id = _value(
            row,
            "Module_ID",
            "Module ID",
            "ModuleId",
        )

        if module_id:
            grouped[str(module_id).strip()] = row

    return grouped


def _extract_factor_scores(
    module: dict[str, Any],
    factor_row: dict[str, Any],
    factor_weights: dict[str, float],
) -> dict[str, float]:
    scores: dict[str, float] = {}

    aliases: dict[str, tuple[str, ...]] = {
        "REGULATORY_SCORE": (
            "Regulatory_Score",
            "Regulatory Score",
            "Regulatory",
            "Regulatory_Impact",
        ),
        "FINANCIAL_SCORE": (
            "Financial_Score",
            "Financial Score",
            "Financial",
            "Financial_Impact",
            "Revenue_Impact",
        ),
        "CUSTOMER_SCORE": (
            "Customer_Score",
            "Customer Score",
            "Customer",
            "Customer_Impact",
            "Customer_Exposure",
        ),
        "SLA_SCORE": (
            "SLA_Score",
            "SLA Score",
            "SLA",
            "SLA_Impact",
            "Availability_Requirement",
        ),
        "INCIDENT_SCORE": (
            "Incident_Score",
            "Incident Score",
            "Incident",
            "Incident_Impact",
            "Production_Incidents",
        ),
    }

    for factor_name in factor_weights:
        names = aliases.get(
            factor_name,
            (
                factor_name,
                _friendly_factor_name(
                    factor_name
                ),
            ),
        )

        raw_value = _value(
            factor_row,
            *names,
        )

        if raw_value is None:
            raw_value = _value(
                module,
                *names,
            )

        scores[factor_name] = round(
            _value_to_five_point_score(
                raw_value
            ),
            2,
        )

    return scores


def _calculate_weighted_score(
    factor_scores: dict[str, float],
    factor_weights: dict[str, float],
) -> float:
    total_weight = sum(
        factor_weights.values()
    )

    if total_weight <= 0:
        return 0.0

    weighted_total = sum(
        factor_scores.get(
            factor_name,
            0.0,
        )
        * weight
        for factor_name, weight
        in factor_weights.items()
    )

    return weighted_total / total_weight


def _load_factor_weights(
    rows: list[dict[str, Any]],
) -> dict[str, float]:
    configured_weights: dict[str, float] = {}

    for row in rows:
        factor_name = _value(
            row,
            "Factor",
            "Factor_Name",
            "Criticality_Factor",
        )
        weight_value = _value(
            row,
            "Weight",
            "Factor_Weight",
        )

        if not factor_name or weight_value is None:
            continue

        normalized_factor = _canonical_factor_name(
            factor_name
        )

        if normalized_factor not in (
            DEFAULT_FACTOR_WEIGHTS
        ):
            continue

        weight = _to_float(
            weight_value,
            default=0.0,
        )

        if weight > 1:
            weight /= 100

        if weight > 0:
            configured_weights[
                normalized_factor
            ] = weight

    weights = DEFAULT_FACTOR_WEIGHTS.copy()
    weights.update(configured_weights)

    total = sum(weights.values())

    if total <= 0:
        return DEFAULT_FACTOR_WEIGHTS.copy()

    return {
        factor: weight / total
        for factor, weight
        in weights.items()
    }


def _load_tier_thresholds(
    rows: list[dict[str, Any]],
) -> dict[str, float]:
    thresholds = (
        DEFAULT_TIER_THRESHOLDS.copy()
    )

    for row in rows:
        tier = _value(
            row,
            "Tier",
            "Assigned_Tier",
        )
        minimum_score = _value(
            row,
            "Minimum_Score",
            "Min_Score",
            "Threshold",
        )

        if not tier or minimum_score is None:
            continue

        normalized_tier = _normalize_tier(
            tier
        )

        if normalized_tier in thresholds:
            thresholds[
                normalized_tier
            ] = _to_float(
                minimum_score,
                default=thresholds[
                    normalized_tier
                ],
            )

    return thresholds


def _load_latest_tier_overrides(
    change_log: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    overrides: dict[str, dict[str, Any]] = {}

    for row in change_log:
        module_id = _value(
            row,
            "Module_ID",
            "Module ID",
            "ModuleId",
        )

        if not module_id:
            continue

        status = _normalized(
            _first_non_empty(
                _value(
                    row,
                    "Approval_Status",
                    "Approval Status",
                ),
                _value(
                    row,
                    "Status",
                ),
                "ACTIVE",
            )
        )

        if status not in {
            "ACTIVE",
            "APPROVED",
            "CURRENT",
            "ENABLED",
        }:
            continue

        overrides[str(module_id).strip()] = row

    return overrides


def _minimum_coverage_for_tier(
    tier: str,
    configuration: list[dict[str, Any]],
) -> float:
    default_value = (
        DEFAULT_MINIMUM_COVERAGE.get(
            tier,
            0.50,
        )
    )

    for row in configuration:
        row_tier = _value(
            row,
            "Tier",
            "Assigned_Tier",
        )

        if not row_tier:
            continue

        if _normalize_tier(row_tier) != tier:
            continue

        coverage = _value(
            row,
            "Minimum_Coverage",
            "Min_Coverage",
            "Coverage_Floor",
        )

        if coverage is None:
            continue

        numeric_coverage = _to_float(
            coverage,
            default=default_value,
        )

        if numeric_coverage > 1:
            numeric_coverage /= 100

        return min(
            max(numeric_coverage, 0.0),
            1.0,
        )

    return default_value


def _score_to_tier(
    score: float,
    thresholds: dict[str, float],
) -> str:
    for tier in (
        "TIER_1",
        "TIER_2",
        "TIER_3",
        "TIER_4",
    ):
        if score >= thresholds.get(
            tier,
            DEFAULT_TIER_THRESHOLDS[tier],
        ):
            return tier

    return "TIER_4"


def _value_to_five_point_score(
    value: Any,
) -> float:
    """
    Convert numeric or categorical criticality values to a 1-to-5 score.

    Important: integer 1 is already a valid 1-to-5 score. It must not
    be treated as the fraction 1.0 and converted to 5.0.
    """

    if value is None or value == "":
        return 0.0

    if isinstance(value, bool):
        return 5.0 if value else 1.0

    if isinstance(value, (int, float)):
        numeric = float(value)

        # Values from 1 through 5 are already on the 1-to-5 scale.
        if 1 <= numeric <= 5:
            return numeric

        # Fractions are strictly below 1.0.
        if 0 <= numeric < 1:
            return numeric * 5

        if 5 < numeric <= 100:
            return numeric / 20

        return min(
            max(numeric, 0.0),
            5.0,
        )

    normalized = _normalized(value)

    categorical_scores = {
        "CRITICAL": 5.0,
        "VERY_HIGH": 5.0,
        "HIGH": 4.0,
        "MEDIUM": 3.0,
        "MODERATE": 3.0,
        "LOW": 2.0,
        "VERY_LOW": 1.0,
        "YES": 5.0,
        "Y": 5.0,
        "TRUE": 5.0,
        "NO": 1.0,
        "N": 1.0,
        "FALSE": 1.0,
    }

    if normalized in categorical_scores:
        return categorical_scores[
            normalized
        ]

    try:
        return _value_to_five_point_score(
            float(str(value).strip())
        )
    except (TypeError, ValueError):
        return 0.0


def _canonical_factor_name(
    value: Any,
) -> str:
    normalized = _normalize_key(value)

    aliases = {
        "REGULATORY": "REGULATORY_SCORE",
        "REGULATORY_IMPACT": "REGULATORY_SCORE",
        "REGULATORY_SCORE": "REGULATORY_SCORE",
        "FINANCIAL": "FINANCIAL_SCORE",
        "FINANCIAL_IMPACT": "FINANCIAL_SCORE",
        "FINANCIAL_SCORE": "FINANCIAL_SCORE",
        "REVENUE_IMPACT": "FINANCIAL_SCORE",
        "CUSTOMER": "CUSTOMER_SCORE",
        "CUSTOMER_IMPACT": "CUSTOMER_SCORE",
        "CUSTOMER_SCORE": "CUSTOMER_SCORE",
        "CUSTOMER_EXPOSURE": "CUSTOMER_SCORE",
        "SLA": "SLA_SCORE",
        "SLA_IMPACT": "SLA_SCORE",
        "SLA_SCORE": "SLA_SCORE",
        "AVAILABILITY_REQUIREMENT": "SLA_SCORE",
        "INCIDENT": "INCIDENT_SCORE",
        "INCIDENT_IMPACT": "INCIDENT_SCORE",
        "INCIDENT_SCORE": "INCIDENT_SCORE",
        "PRODUCTION_INCIDENTS": "INCIDENT_SCORE",
        "BUSINESS_CRITICALITY": "FINANCIAL_SCORE",
    }

    return aliases.get(
        normalized,
        normalized,
    )


def _friendly_factor_name(
    factor_name: str,
) -> str:
    return factor_name.replace(
        "_",
        " ",
    ).title()


def _normalize_tier(value: Any) -> str:
    normalized = _normalized(value)

    aliases = {
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
    }

    return aliases.get(
        normalized,
        normalized,
    )


def format_criticality_cards(
    result: dict[str, Any],
) -> str:
    assignments = result.get(
        "module_assignments",
        {},
    )
    test_tags = result.get(
        "test_tags",
        {},
    )
    summary = result.get(
        "summary",
        {},
    )

    lines: list[str] = [
        "# Application Criticality Classification",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| Total modules | {summary.get('total_modules', 0)} |",
        f"| Total test cases | {summary.get('total_test_cases', 0)} |",
        f"| Tier 1 modules | {summary.get('tier_1_modules', 0)} |",
        f"| Tier 2 modules | {summary.get('tier_2_modules', 0)} |",
        f"| Tier 3 modules | {summary.get('tier_3_modules', 0)} |",
        f"| Tier 4 modules | {summary.get('tier_4_modules', 0)} |",
        "| Tier-floor protected tests | "
        f"{summary.get('tier_floor_protected_tests', 0)} |",
        "| Tier overrides applied | "
        f"{summary.get('tier_overrides_applied', 0)} |",
        "",
        "---",
        "",
        "## Module Tier Assignments",
        "",
    ]

    if assignments:
        for module_id, assignment in sorted(
            assignments.items()
        ):
            factor_scores = assignment.get(
                "Factor_Scores",
                {},
            )

            lines.extend(
                [
                    f"> ### `{module_id}` — "
                    f"{_display(assignment.get('Module_Name'))}",
                    ">",
                    "> **Criticality score:** "
                    f"`{assignment.get('Criticality_Score', 0):.2f}` / 5",
                    ">",
                    "> **Calculated tier:** "
                    f"`{assignment.get('Calculated_Tier', 'TIER_4')}`",
                    ">",
                    "> **Final tier:** "
                    f"`{assignment.get('Tier', 'TIER_4')}`",
                    ">",
                    "> **Tier source:** "
                    f"`{assignment.get('Tier_Source', 'CALCULATED')}`",
                    ">",
                    "> **Minimum coverage:** "
                    f"`{assignment.get('Minimum_Coverage_Percent', 0):.0f}%`",
                    ">",
                    "> **Factors:** "
                    + ", ".join(
                        f"{name}={score:.2f}"
                        for name, score
                        in factor_scores.items()
                    ),
                    "",
                ]
            )
    else:
        lines.extend(
            [
                "> No module assignments were generated.",
                "",
            ]
        )

    lines.extend(
        [
            "---",
            "",
            "## Test Tier Tags",
            "",
            "| Test Case | Module | Tier | Score | Protected |",
            "|---|---|---|---:|---|",
        ]
    )

    for test_case_id, tag in sorted(
        test_tags.items()
    ):
        protected = (
            "Yes"
            if tag.get("tier_floor_protection")
            else "No"
        )

        lines.append(
            f"| `{test_case_id}` "
            f"| `{tag.get('module_id', '')}` "
            f"| `{tag.get('tier', 'TIER_3')}` "
            f"| {tag.get('criticality_score', 0):.2f} "
            f"| {protected} |"
        )

    return "\n".join(lines)


def _value(
    row: dict[str, Any],
    *possible_names: str,
) -> Any:
    if not row:
        return None

    normalized_row = {
        _normalize_header(key): value
        for key, value in row.items()
    }

    for possible_name in possible_names:
        normalized_name = _normalize_header(
            possible_name
        )

        if normalized_name in normalized_row:
            return normalized_row[
                normalized_name
            ]

    return None


def _normalize_header(value: Any) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
    )


def _normalize_key(value: Any) -> str:
    return (
        str(value)
        .strip()
        .upper()
        .replace(" ", "_")
        .replace("-", "_")
    )


def _normalized(value: Any) -> str:
    return _normalize_key(value)


def _first_non_empty(
    *values: Any,
) -> Any:
    for value in values:
        if value is not None and value != "":
            return value

    return None


def _display(value: Any) -> str:
    if value is None or value == "":
        return "Not available"

    return str(value)


def _to_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# A2A: Specialist boundary. The Master Orchestrator calls this handler with a
# serializable A2A envelope. The specialist never owns Jira/Excel connectivity.
def handle_a2a_request(request: A2ARequest) -> A2AResponse:

    try:

        data = validate_message(
            request,
            receiver='Application Criticality Classification Agent',
            message_types={
                'CRITICALITY_REQUEST',
                "AGENT_QUERY",
            },
        )

        release_id = request.release_id

        if request.message_type == "AGENT_QUERY":
            return make_response(
                request,
                sender='Application Criticality Classification Agent',
                data=answer_agent_question(
                    question=str(data.get("question") or ""),
                    context=data.get("agent_context", data),
                ),
            )

        result = classify_application_criticality(
            source_data=data.get(
                "source_data",
                {},
            ),
        )

        return make_response(
            request,
            sender='Application Criticality Classification Agent',
            data=result,
        )

    except Exception as exc:

        trace_error(
            "CRITICALITY_AGENT_FAILED",
            agent="Application Criticality Classification Agent",
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
    "CRITICALITY_AGENT_QUERY",
    agent="Application Criticality Classification Agent",
    stage="CRITICALITY",
    status="SUCCESS",
    question=question,
    )
    return {
        "status": "success",
        "agent": 'Application Criticality Classification Agent',
        "question": question,
        "context": context,
        "markdown": _agent_question_markdown(question, context),
    }


def _agent_question_markdown(question: str, context: dict[str, Any]) -> str:
    import json
    output = context.get("agent_output", context)
    log_event(
    "CRITICALITY_AGENT_QUERY",
    agent="Application Criticality Classification Agent",
    stage="CRITICALITY",
    status="SUCCESS",
    question=question,
    )
    return "\n".join([
        f"# {'Application Criticality Classification Agent'}",
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


# A2A: Conversational entry point must receive the same orchestrator-supplied
# modules/test_cases block used by the pipeline; it never creates its own Jira client.
def get_criticality_analysis(context: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(context, dict):
        raise TypeError("context must be a dictionary supplied by the Master Orchestrator.")
    source_data = context.get("source_data", context)
    if not isinstance(source_data, dict):
        raise TypeError("Criticality source_data must be a dictionary.")
    return classify_application_criticality(source_data)
