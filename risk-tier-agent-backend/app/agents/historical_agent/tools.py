# #old_historical_agent/tools.py
# from __future__ import annotations

# from collections import defaultdict
# from datetime import datetime, timezone
# import re
# from typing import Any

# from app.observability.logger import (
#     log_event,
#     trace_error,
# )

# from app.observability.audit import audit_event

# from app.models import A2ARequest, A2AResponse
# from app.services.a2a import make_response, validate_message

# from app.utils.helpers import is_yes


# SEVERITY_SCORES: dict[str, float] = {
#     "CRITICAL": 100.0,
#     "BLOCKER": 100.0,
#     "HIGH": 80.0,
#     "MAJOR": 70.0,
#     "MEDIUM": 50.0,
#     "MINOR": 30.0,
#     "LOW": 20.0,
#     "TRIVIAL": 10.0,
# }


# REQUIRED_INPUTS: tuple[str, ...] = (
#     "test_cases",
#     "executions",
#     "defects",
#     "flaky_tests",
# )

# DEFAULT_DEFECT_PROTECTION_RELEASES = 6
# DEFAULT_CONSISTENT_PASS_EXECUTIONS = 10
# DEFAULT_MINIMUM_EXECUTIONS = 3
# DEFAULT_DECAY_HALF_LIFE_RELEASES = 8.0
# DEFAULT_DECAY_HALF_LIFE_DAYS = 365.0

# PASS_STATUSES = {"PASS", "PASSED", "SUCCESS"}
# FAIL_STATUSES = {"FAIL", "FAILED", "ERROR", "BLOCKED"}
# SKIP_STATUSES = {"SKIP", "SKIPPED", "NOT_EXECUTED", "NOT_RUN"}


# def analyze_historical_execution(
#     source_data: dict[
#         str,
#         list[dict[str, Any]],
#     ],
#     release_id: str | None = None,
# ) -> dict[str, Any]:
#     log_event(
#         "HISTORICAL_ANALYSIS_STARTED",
#         agent="Historical Execution Intelligence Agent",
#         stage="HISTORICAL",
#         status="STARTED",
#         release_id=release_id,
#     )
#     """
#     Generate historical intelligence from orchestrator-supplied data.

#     The Master Orchestrator must provide all raw rows through
#     ``source_data``. This agent does not open or read source workbooks directly.

#     Required source_data keys:
#     - test_cases
#     - executions
#     - defects
#     - flaky_tests

#     Generated outputs:
#     - Per-test historical summaries
#     - Defect-catch protection
#     - Flaky-test protection
#     - Aggregate historical metrics
#     - Compact agent-to-agent output
#     - Markdown dashboard

#     This function does not read:
#     - historical_summary
#     """

#     _validate_source_data(
#         source_data
#     )

#     test_cases = source_data[
#         "test_cases"
#     ]
#     executions = source_data[
#         "executions"
#     ]
#     defect_rows = source_data[
#         "defects"
#     ]
#     flaky_rows = source_data[
#         "flaky_tests"
#     ]
#     log_event(
#     "HISTORICAL_INPUTS_LOADED",
#     agent="Historical Execution Intelligence Agent",
#     stage="HISTORICAL",
#     status="SUCCESS",
#     test_cases=len(test_cases),
#     executions=len(executions),
#     defects=len(defect_rows),
#     flaky_tests=len(flaky_rows),
#     )

#     normalized_release_id = (
#         str(release_id).strip().upper()
#         if release_id is not None
#         else None
#     )

#     config = _historical_config(source_data)
#     defect_protection_releases = config["defect_protection_releases"]
#     consistent_pass_executions = config["consistent_pass_executions"]
#     minimum_executions = config["minimum_executions"]
#     decay_half_life_releases = config["decay_half_life_releases"]
#     decay_half_life_days = config["decay_half_life_days"]

#     observed_release_ids = _ordered_release_ids(
#         executions=executions,
#         defects=defect_rows,
#         flaky_rows=flaky_rows,
#     )

#     if normalized_release_id:
#         current_release_key = _release_key(normalized_release_id)
#         if current_release_key not in observed_release_ids:
#             observed_release_ids.append(current_release_key)
#         observed_release_ids.sort(key=_release_sort_key)
#     release_position = {
#         release_key: index
#         for index, release_key in enumerate(observed_release_ids)
#     }
#     current_release_index = (
#         release_position.get(normalized_release_id)
#         if normalized_release_id
#         else None
#     )
#     current_date = _resolve_current_history_date(
#         executions=executions,
#         defects=defect_rows,
#     )

#     test_case_lookup: dict[str, dict[str, Any]] = {}
#     for row in test_cases:
#         test_case_id = (
#             _value(
#                 row,
#                 "Test_Case_ID",
#                 "Test Case ID",
#                 "TestCase_ID",
#                 "Test_ID",
#                 "TC_ID",
#             )
#             or _extract_tc_id_from_record(row)
#         )
#         if not test_case_id:
#             continue
#         test_case_lookup[str(test_case_id).strip().upper()] = row

#     execution_groups: dict[
#         str,
#         list[dict[str, Any]],
#     ] = defaultdict(list)

#     defect_groups: dict[
#         str,
#         list[dict[str, Any]],
#     ] = defaultdict(list)

#     flaky_tests: dict[
#         str,
#         dict[str, Any],
#     ] = {}
#     log_event(
#     "HISTORICAL_DATA_GROUPED",
#     agent="Historical Execution Intelligence Agent",
#     stage="HISTORICAL",
#     execution_groups=len(execution_groups),
#     defect_groups=len(defect_groups),
#     flaky_records=len(flaky_tests),
#     )

#     known_test_ids = set(
#         test_case_lookup.keys()
#     )

#     # ---------------------------------------------------------
#     # Group historical execution records
#     # ---------------------------------------------------------
#     for row in executions:
#         test_case_id = (
#             _value(
#                 row,
#                 "Test_Case_ID",
#                 "Test Case ID",
#                 "TestCase_ID",
#                 "Test_ID",
#                 "TC_ID",
#             )
#             or _extract_tc_id_from_record(row)
#         )

#         if not test_case_id:
#             continue

#         normalized_test_case_id = str(
#             test_case_id
#         ).strip().upper()

#         execution_groups[
#             normalized_test_case_id
#         ].append(row)

#     # ---------------------------------------------------------
#     # Group defect records
#     # ---------------------------------------------------------
#     for row in defect_rows:
#         test_case_id = _value(
#             row,
#             "Test_Case_ID",
#             "Test Case ID",
#             "TestCase_ID",
#             "Test_ID",
#             "TC_ID",
#         ) or _extract_tc_id_from_record(row)

#         if not test_case_id:
#             continue

#         normalized_test_case_id = str(
#             test_case_id
#         ).strip().upper()

#         defect_groups[
#             normalized_test_case_id
#         ].append(row)

#     # ---------------------------------------------------------
#     # Group flaky-test records
#     # ---------------------------------------------------------
#     for row in flaky_rows:
#         test_case_id = _value(
#             row,
#             "Test_Case_ID",
#             "Test Case ID",
#             "TestCase_ID",
#             "Test_ID",
#             "TC_ID",
#         ) or _extract_tc_id_from_record(row)

#         if not test_case_id:
#             continue

#         normalized_test_case_id = str(
#             test_case_id
#         ).strip().upper()

#         flaky_tests[
#             normalized_test_case_id
#         ] = row

#     summaries: dict[
#         str,
#         dict[str, Any],
#     ] = {}

#     # ---------------------------------------------------------
#     # Generate one historical summary per test case
#     # ---------------------------------------------------------
#     for test_case_id in sorted(
#         known_test_ids
#     ):
#         test_case = test_case_lookup.get(
#             test_case_id,
#             {},
#         )

#         test_executions = (
#             execution_groups.get(
#                 test_case_id,
#                 [],
#             )
#         )

#         linked_defects = defect_groups.get(
#             test_case_id,
#             [],
#         )

#         flaky_record = dict(
#             flaky_tests.get(
#                 test_case_id,
#                 {},
#             )
#         )

#         # If Jira has no separate flaky record for this test, accept an
#         # execution-level flaky signal as a fallback.
#         if not flaky_record:
#             for execution in test_executions:
#                 if is_yes(
#                     _value(
#                         execution,
#                         "Is_Flaky",
#                         "Is Flaky",
#                         "Flaky",
#                     )
#                 ):
#                     flaky_record = execution
#                     break
#                 execution_flaky_status = _normalized(
#                     _value(
#                         execution,
#                         "Flaky_Status",
#                         "Flaky Status",
#                     )
#                 )
#                 if execution_flaky_status in {"FLAKY", "ACTIVE"}:
#                     flaky_record = execution
#                     break

#         execution_count = len(
#             test_executions
#         )

#         passed_count = sum(
#             1
#             for row in test_executions
#             if _execution_status(row)
#             in {
#                 "PASS",
#                 "PASSED",
#                 "SUCCESS",
#             }
#         )

#         failed_count = sum(
#             1
#             for row in test_executions
#             if _execution_status(row)
#             in {
#                 "FAIL",
#                 "FAILED",
#                 "ERROR",
#                 "BLOCKED",
#             }
#         )

#         skipped_count = sum(
#             1
#             for row in test_executions
#             if _execution_status(row)
#             in {
#                 "SKIP",
#                 "SKIPPED",
#                 "NOT_EXECUTED",
#                 "NOT_RUN",
#             }
#         )

#         pass_rate = (
#             passed_count / execution_count
#             if execution_count
#             else 0.0
#         )

#         failure_rate = (
#             failed_count / execution_count
#             if execution_count
#             else 0.0
#         )

#         confirmed_defects = [
#             defect
#             for defect in linked_defects
#             if _is_confirmed_defect(defect)
#         ]

#         confirmed_defect_count = len(
#             confirmed_defects
#         )

#         production_defect_count = sum(
#             1
#             for defect in confirmed_defects
#             if _is_production_escape(defect)
#         )

#         highest_defect_severity = (
#             _highest_severity(
#                 confirmed_defects
#             )
#         )

#         defect_severity_score = (
#             _defect_severity_score(
#                 confirmed_defects
#             )
#         )

#         flaky = _is_flaky(
#             flaky_record
#         )

#         flaky_failure_count = _flaky_failure_count(
#             flaky_record
#         )

#         insufficient_history = (
#             execution_count < minimum_executions
#         )

#         # -----------------------------------------------------
#         # Historical protection and recency-aware value
#         # -----------------------------------------------------
#         protected_defects = [
#             defect
#             for defect in confirmed_defects
#             if _defect_is_within_protection_window(
#                 defect=defect,
#                 test_executions=test_executions,
#                 observed_release_ids=observed_release_ids,
#                 release_position=release_position,
#                 current_release_index=current_release_index,
#                 protection_releases=defect_protection_releases,
#             )
#         ]

#         defect_catch_protection = bool(protected_defects)

#         # BR-HIST-03: flakiness is a remediation/protection signal only.
#         # It must NOT modify Historical_Value_Score directly.
#         flaky_remediation_protection = flaky or flaky_failure_count > 0

#         # BR-HIST-02 historical component: identify the raw consistent-pass /
#         # zero-defect candidate signal here. The business rule is based on the
#         # LAST N executions, not on every execution in the test's full history.
#         # Tier 3/4 criticality is applied by the Decision / Risk Scoring Agent
#         # because the Historical Agent's required input contract does not include
#         # criticality data.
#         ordered_test_executions = sorted(
#             test_executions,
#             key=lambda record: (
#                 _parse_date(
#                     _value(
#                         record,
#                         "Execution_Date",
#                         "Execution Date",
#                         "Date",
#                     )
#                 ) or datetime.min.replace(tzinfo=timezone.utc)
#             ),
#         )
#         recent_execution_window = ordered_test_executions[-consistent_pass_executions:]

#         recent_execution_window_is_consistent_pass = (
#             len(recent_execution_window) == consistent_pass_executions
#             and all(
#                 _execution_status(record) in PASS_STATUSES
#                 for record in recent_execution_window
#             )
#         )

#         consistent_pass_zero_defect_eligible = (
#             execution_count >= consistent_pass_executions
#             and recent_execution_window_is_consistent_pass
#             and confirmed_defect_count == 0
#         )

#         weighted_failure_points = sum(
#             6.0 * _recency_weight(
#                 record=row,
#                 release_position=release_position,
#                 current_release_index=current_release_index,
#                 current_date=current_date,
#                 half_life_releases=decay_half_life_releases,
#                 half_life_days=decay_half_life_days,
#             )
#             for row in test_executions
#             if _execution_status(row) in FAIL_STATUSES
#         )

#         weighted_defect_points = sum(
#             20.0 * _recency_weight(
#                 record=defect,
#                 release_position=release_position,
#                 current_release_index=current_release_index,
#                 current_date=current_date,
#                 half_life_releases=decay_half_life_releases,
#                 half_life_days=decay_half_life_days,
#             )
#             for defect in confirmed_defects
#         )

#         weighted_production_points = sum(
#             10.0 * _recency_weight(
#                 record=defect,
#                 release_position=release_position,
#                 current_release_index=current_release_index,
#                 current_date=current_date,
#                 half_life_releases=decay_half_life_releases,
#                 half_life_days=decay_half_life_days,
#             )
#             for defect in confirmed_defects
#             if _is_production_escape(defect)
#         )

#         historical_value_score = min(
#             max(
#                 weighted_failure_points
#                 + weighted_defect_points
#                 + weighted_production_points,
#                 0.0,
#             ),
#             100.0,
#         )

#         # Store the actual protected defect IDs so downstream consumers can
#         # distinguish current-window protection from old confirmed defects.
#         protected_defect_ids = sorted(
#             {
#                 str(defect_id).strip()
#                 for defect in protected_defects
#                 if (
#                     defect_id := _value(
#                         defect,
#                         "Defect_ID",
#                         "Defect ID",
#                         "Bug_ID",
#                         "Bug ID",
#                     )
#                 )
#             }
#         )

#         category = _historical_category(
#             historical_value_score=(
#                 historical_value_score
#             ),
#             defect_catch_protection=(
#                 defect_catch_protection
#             ),
#             flaky=flaky,
#             insufficient_history=(
#                 insufficient_history
#             ),
#         )

#         linked_defect_ids = sorted(
#             {
#                 str(defect_id).strip()
#                 for defect
#                 in linked_defects
#                 if (
#                     defect_id := _value(
#                         defect,
#                         "Defect_ID",
#                         "Defect ID",
#                         "Bug_ID",
#                         "Bug ID",
#                     )
#                 )
#             }
#         )

#         summaries[test_case_id] = {
#             "Test_Case_ID": test_case_id,
#             "Test_Name": _value(
#                 test_case,
#                 "Test_Name",
#                 "Test Name",
#                 "Test_Case_Name",
#                 "Name",
#             ),
#             "Module_ID": _value(
#                 test_case,
#                 "Module_ID",
#                 "Module ID",
#                 "ModuleId",
#             ),
#             "Execution_Count": (
#                 execution_count
#             ),
#             "Passed_Count": passed_count,
#             "Failed_Count": failed_count,
#             "Failure_Count": failed_count,
#             "Skipped_Count": skipped_count,
#             "Pass_Rate": round(
#                 pass_rate,
#                 4,
#             ),
#             "Failure_Rate": round(
#                 failure_rate,
#                 4,
#             ),
#             "Confirmed_Defects": (
#                 confirmed_defect_count
#             ),
#             "Production_Defects": (
#                 production_defect_count
#             ),
#             "Highest_Defect_Severity": (
#                 highest_defect_severity
#             ),
#             "Defect_Severity_Score": round(
#                 defect_severity_score,
#                 2,
#             ),
#             "Flaky_Failures": (
#                 flaky_failure_count
#             ),
#             "Historical_Value_Score": round(
#                 historical_value_score,
#                 2,
#             ),
#             "Category": category,
#             "insufficient_history": insufficient_history,
#             "consistent_pass_zero_defect_eligible": (
#                 consistent_pass_zero_defect_eligible
#             ),
#             "defect_protection_window_active": defect_catch_protection,
#             "protected_defect_ids": protected_defect_ids,
#             "flaky": flaky,
#             "flaky_remediation_protection": (
#                 flaky_remediation_protection
#             ),
#             "defect_catch_protection": (
#                 defect_catch_protection
#             ),
#             "linked_defect_ids": (
#                 linked_defect_ids
#             ),
#             "linked_defects": linked_defects,
#             "executions": test_executions,
#         }

#     # ---------------------------------------------------------
#     # Aggregate summary
#     # ---------------------------------------------------------
#     total_execution_records = sum(
#         len(records)
#         for records
#         in execution_groups.values()
#     )

#     tests_with_failures = sum(
#         1
#         for row in summaries.values()
#         if row["Failed_Count"] > 0
#     )

#     tests_with_confirmed_defects = sum(
#         1
#         for row in summaries.values()
#         if row["Confirmed_Defects"] > 0
#     )

#     defect_protected_test_ids = sorted(
#         test_case_id
#         for test_case_id, row
#         in summaries.items()
#         if row[
#             "defect_catch_protection"
#         ]
#     )
#     log_event(
#     "BR_HIST_01_APPLIED",
#     agent="Historical Execution Intelligence Agent",
#     rule_id="BR-HIST-01",
#     protected_tests=len(defect_protected_test_ids),
#     )

#     flaky_test_ids = sorted(
#         test_case_id
#         for test_case_id, row
#         in summaries.items()
#         if row["flaky"]
#     )
#     log_event(
#     "BR_HIST_03_APPLIED",
#     agent="Historical Execution Intelligence Agent",
#     rule_id="BR-HIST-03",
#     flaky_tests=len(flaky_test_ids),
#     )

#     insufficient_history_test_ids = sorted(
#         test_case_id
#         for test_case_id, row in summaries.items()
#         if row["insufficient_history"]
#     )
#     log_event(
#         "BR_HIST_05_APPLIED",
#         agent="Historical Execution Intelligence Agent",
#         rule_id="BR-HIST-05",
#         insufficient_history=len(
#             insufficient_history_test_ids
#         ),
#     )

#     consistent_pass_zero_defect_test_ids = sorted(
#         test_case_id
#         for test_case_id, row in summaries.items()
#         if row["consistent_pass_zero_defect_eligible"]
#     )
#     log_event(
#         "BR_HIST_02_APPLIED",
#         agent="Historical Execution Intelligence Agent",
#         rule_id="BR-HIST-02",
#         eligible_tests=len(
#             consistent_pass_zero_defect_test_ids
#         ),
#     )

#     summary = {
#         "total_test_cases": len(
#             summaries
#         ),
#         "total_execution_records": (
#             total_execution_records
#         ),
#         "passed_executions": sum(
#             row["Passed_Count"]
#             for row in summaries.values()
#         ),
#         "failed_executions": sum(
#             row["Failed_Count"]
#             for row in summaries.values()
#         ),
#         "skipped_executions": sum(
#             row["Skipped_Count"]
#             for row in summaries.values()
#         ),
#         "tests_with_failures": (
#             tests_with_failures
#         ),
#         "confirmed_defects": sum(
#             row["Confirmed_Defects"]
#             for row in summaries.values()
#         ),
#         "production_defects": sum(
#             row["Production_Defects"]
#             for row in summaries.values()
#         ),
#         "tests_with_confirmed_defects": (
#             tests_with_confirmed_defects
#         ),
#         "tests_with_insufficient_history": (
#             len(
#                 insufficient_history_test_ids
#             )
#         ),
#         "flaky_test_count": len(
#             flaky_test_ids
#         ),
#         "defect_protected_tests": len(defect_protected_test_ids),
#         "consistent_pass_zero_defect_eligible_tests": len(
#             consistent_pass_zero_defect_test_ids
#         ),
#         "defect_protection_window_releases": defect_protection_releases,
#         "consistent_pass_execution_window": consistent_pass_executions,
#         "minimum_history_executions": minimum_executions,
#         "recency_decay_half_life_releases": decay_half_life_releases,
#         "recency_decay_half_life_days": decay_half_life_days,
#     }

#     result: dict[str, Any] = {
#         "release_id": (
#             normalized_release_id
#         ),
#         "test_summaries": summaries,
#         "flaky_tests": flaky_tests,
#         "defects": dict(
#             defect_groups
#         ),
#         "execution_records": dict(
#             execution_groups
#         ),
#         "summary": summary,

#         # Compact output intended for downstream scoring.
#         "agent_output": {
#             "release_id": (
#                 normalized_release_id
#             ),
#             "business_rules": {
#                 "BR-HIST-01": "Confirmed defect catches within the last 6 releases remain protected from exclusion.",
#                 "BR-HIST-02": "100% pass over the last 10 executions, zero defects, and Tier 3/4 criticality creates an exclusion candidate.",
#                 "BR-HIST-03": "Flakiness routes to remediation and cannot justify exclusion by itself.",
#                 "BR-HIST-04": "Historical influence decays with age using the configured release/date half-life.",
#                 "BR-HIST-05": "Fewer than 3 executions is insufficient history and defaults to inclusion.",
#             },
#             "test_summaries": {
#                 test_case_id: {
#                     "Historical_Value_Score": (
#                         row[
#                             "Historical_Value_Score"
#                         ]
#                     ),
#                     "insufficient_history": (
#                         row[
#                             "insufficient_history"
#                         ]
#                     ),
#                     "flaky": row["flaky"],
#                     "flaky_remediation_protection": (
#                         row[
#                             "flaky_remediation_protection"
#                         ]
#                     ),
#                     "defect_catch_protection": row["defect_catch_protection"],
#                     "consistent_pass_zero_defect_eligible": (
#                         row["consistent_pass_zero_defect_eligible"]
#                     ),
#                     "defect_protection_window_active": row["defect_protection_window_active"],
#                     "protected_defect_ids": row["protected_defect_ids"],
#                     "Confirmed_Defects": (
#                         row[
#                             "Confirmed_Defects"
#                         ]
#                     ),
#                     "Production_Defects": (
#                         row[
#                             "Production_Defects"
#                         ]
#                     ),
#                     "Failed_Count": (
#                         row["Failed_Count"]
#                     ),
#                     "Category": (
#                         row["Category"]
#                     ),
#                 }
#                 for test_case_id, row
#                 in summaries.items()
#             },
#             "defect_protected_test_ids": (
#                 defect_protected_test_ids
#             ),
#             "flaky_test_ids": (
#                 flaky_test_ids
#             ),
#             "insufficient_history_test_ids": insufficient_history_test_ids,
#             "consistent_pass_zero_defect_test_ids": consistent_pass_zero_defect_test_ids,
#             "defect_protection_window_releases": defect_protection_releases,
#             "consistent_pass_execution_window": consistent_pass_executions,
#             "minimum_history_executions": minimum_executions,
#             "recency_decay_half_life_releases": decay_half_life_releases,
#             "recency_decay_half_life_days": decay_half_life_days,
#         },
#     }
#     log_event(
#         "HISTORICAL_ANALYSIS_COMPLETED",
#         agent="Historical Execution Intelligence Agent",
#         stage="HISTORICAL",
#         status="SUCCESS",
#         total_tests=len(summaries),
#         total_executions=total_execution_records,
#     )

#     audit_event(
#         "HISTORICAL_ANALYSIS_COMPLETED",
#         agent="Historical Execution Intelligence Agent",
#         message=(
#             f"Analyzed {len(summaries)} tests "
#             f"across {total_execution_records} executions."
#         ),
#         details={
#             "defect_protected_tests": len(
#                 defect_protected_test_ids
#             ),
#             "flaky_tests": len(
#                 flaky_test_ids
#             ),
#             "insufficient_history_tests": len(
#                 insufficient_history_test_ids
#             ),
#             "consistent_pass_tests": len(
#                 consistent_pass_zero_defect_test_ids
#             ),
#         },
#     )

#     result["markdown"] = (
#         format_historical_cards(result)
#     )

#     return result



# def _validate_source_data(
#     source_data: dict[
#         str,
#         list[dict[str, Any]],
#     ],
# ) -> None:
#     """
#     Validate raw rows supplied by the Master Orchestrator.
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
#         for input_name in REQUIRED_INPUTS
#         if input_name not in source_data
#     ]

#     if missing_inputs:
#         raise ValueError(
#             "Historical Agent is missing required "
#             "orchestrator inputs: "
#             f"{missing_inputs}"
#         )

#     invalid_inputs = [
#         input_name
#         for input_name in REQUIRED_INPUTS
#         if not isinstance(
#             source_data[
#                 input_name
#             ],
#             list,
#         )
#     ]

#     if invalid_inputs:
#         raise TypeError(
#             "Historical Agent expected input "
#             "rows as lists for: "
#             f"{invalid_inputs}"
#         )

# def format_historical_cards(
#     result: dict[str, Any],
# ) -> str:
#     """
#     Build a user-facing Markdown dashboard for ADK.
#     """

#     summaries = result.get(
#         "test_summaries",
#         {},
#     )

#     summary = result.get(
#         "summary",
#         {},
#     )

#     lines: list[str] = [
#         "# Historical Execution Intelligence",
#         "",
#         "## Summary",
#         "",
#         "| Metric | Count |",
#         "|---|---:|",
#         "| Test cases analyzed | "
#         f"{summary.get('total_test_cases', 0)} |",
#         "| Historical executions | "
#         f"{summary.get('total_execution_records', 0)} |",
#         "| Passed executions | "
#         f"{summary.get('passed_executions', 0)} |",
#         "| Failed executions | "
#         f"{summary.get('failed_executions', 0)} |",
#         "| Skipped executions | "
#         f"{summary.get('skipped_executions', 0)} |",
#         "| Confirmed defects | "
#         f"{summary.get('confirmed_defects', 0)} |",
#         "| Production defects | "
#         f"{summary.get('production_defects', 0)} |",
#         "| Tests with confirmed defects | "
#         f"{summary.get('tests_with_confirmed_defects', 0)} |",
#         "| Flaky tests | "
#         f"{summary.get('flaky_test_count', 0)} |",
#         "| Insufficient-history tests | "
#         f"{summary.get('tests_with_insufficient_history', 0)} |",
#         "| Defect-protected tests | "
#         f"{summary.get('defect_protected_tests', 0)} |",
#         "| Consistent-pass / zero-defect eligible tests | "
#         f"{summary.get('consistent_pass_zero_defect_eligible_tests', 0)} |",
#         "",
#         "---",
#         "",
#         "## Test History",
#         "",
#     ]

#     if not summaries:
#         lines.extend(
#             [
#                 "> No historical test records were generated.",
#                 "",
#             ]
#         )

#         return "\n".join(lines)

#     for test_case_id, record in sorted(
#         summaries.items()
#     ):
#         protection_labels: list[str] = []

#         if record.get(
#             "defect_catch_protection"
#         ):
#             protection_labels.append(
#                 "Defect-catch protection"
#             )

#         if record.get("flaky"):
#             protection_labels.append(
#                 "Flaky remediation"
#             )

#         if record.get(
#             "insufficient_history"
#         ):
#             protection_labels.append(
#                 "Insufficient history"
#             )

#         protection_text = (
#             ", ".join(
#                 protection_labels
#             )
#             if protection_labels
#             else "None"
#         )

#         linked_defects = record.get(
#             "linked_defect_ids",
#             [],
#         )

#         linked_defect_text = (
#             ", ".join(linked_defects)
#             if linked_defects
#             else "None"
#         )

#         lines.extend(
#             [
#                 f"> ### `{test_case_id}` — "
#                 f"{_display(record.get('Test_Name'))}",
#                 ">",
#                 "> **Module:** "
#                 f"`{_display(record.get('Module_ID'))}`",
#                 ">",
#                 "> **Executions:** "
#                 f"{record.get('Execution_Count', 0)}",
#                 ">",
#                 "> **Pass / Fail / Skip:** "
#                 f"{record.get('Passed_Count', 0)} / "
#                 f"{record.get('Failed_Count', 0)} / "
#                 f"{record.get('Skipped_Count', 0)}",
#                 ">",
#                 "> **Pass rate:** "
#                 f"{record.get('Pass_Rate', 0) * 100:.1f}%",
#                 ">",
#                 "> **Confirmed defects:** "
#                 f"{record.get('Confirmed_Defects', 0)}",
#                 ">",
#                 "> **Highest severity:** "
#                 f"`{_display(record.get('Highest_Defect_Severity'))}`",
#                 ">",
#                 "> **Historical value score:** "
#                 f"`{record.get('Historical_Value_Score', 0):.2f}`",
#                 ">",
#                 "> **Category:** "
#                 f"`{record.get('Category', 'STABLE')}`",
#                 ">",
#                 "> **Consistent-pass / zero-defect eligible:** "
#                 f"`{record.get('consistent_pass_zero_defect_eligible', False)}`",
#                 ">",
#                 "> **Protection:** "
#                 f"{protection_text}",
#                 ">",
#                 "> **Linked defects:** "
#                 f"{linked_defect_text}",
#                 "",
#             ]
#         )

#     return "\n".join(lines)


# def _historical_config(source_data: dict[str, list[dict[str, Any]]]) -> dict[str, float | int]:
#     """Read optional historical configuration; defaults come from the spec."""
#     raw = source_data.get("historical_config")
#     if isinstance(raw, list) and raw and isinstance(raw[0], dict):
#         raw_map = raw[0]
#     elif isinstance(raw, dict):
#         raw_map = raw
#     else:
#         raw_map = {}

#     def number(keys: tuple[str, ...], default: float) -> float:
#         value = _value(raw_map, *keys) if raw_map else None
#         try:
#             return float(value) if value not in (None, "") else default
#         except (TypeError, ValueError):
#             return default

#     return {
#         "defect_protection_releases": max(1, int(round(number((
#             "Defect_Protection_Releases",
#             "Defect Protection Releases",
#             "Protection Window Releases",
#         ), DEFAULT_DEFECT_PROTECTION_RELEASES)))),
#         "consistent_pass_executions": max(1, int(round(number((
#             "Consistent_Pass_Executions",
#             "Consistent Pass Executions",
#             "Pass Window Executions",
#         ), DEFAULT_CONSISTENT_PASS_EXECUTIONS)))),
#         "minimum_executions": max(1, int(round(number((
#             "Minimum_History_Executions",
#             "Minimum History Executions",
#         ), DEFAULT_MINIMUM_EXECUTIONS)))),
#         "decay_half_life_releases": max(0.1, number((
#             "Decay_Half_Life_Releases",
#             "Decay Half Life Releases",
#         ), DEFAULT_DECAY_HALF_LIFE_RELEASES)),
#         "decay_half_life_days": max(1.0, number((
#             "Decay_Half_Life_Days",
#             "Decay Half Life Days",
#         ), DEFAULT_DECAY_HALF_LIFE_DAYS)),
#     }


# def _release_key(value: Any) -> str:
#     return str(value or "").strip().upper()


# def _release_sort_key(value: Any) -> tuple[int, int, str]:
#     text = _release_key(value)
#     match = re.search(r"([A-Z]+)[-_]?(\d+)\.(\d+)", text)
#     if match:
#         return int(match.group(2)), int(match.group(3)), text
#     numbers = re.findall(r"\d+", text)
#     return (int(numbers[0]) if numbers else -1, int(numbers[1]) if len(numbers) > 1 else -1, text)


# # The helper intentionally has no current_release_id parameter. The current
# # release is added by analyze_historical_execution after collecting release IDs.
# # This keeps the helper signature stable and prevents caller/signature drift.
# def _ordered_release_ids(
#     executions: list[dict[str, Any]],
#     defects: list[dict[str, Any]],
#     flaky_rows: list[dict[str, Any]],
# ) -> list[str]:
#     ids: set[str] = set()
#     for rows in (executions, defects, flaky_rows):
#         for row in rows:
#             rid = _value(row, "Release_ID", "Release ID", "release_id", "Release")
#             if rid:
#                 ids.add(_release_key(rid))
#     return sorted(ids, key=_release_sort_key)


# def _parse_date(value: Any) -> datetime | None:
#     if not value:
#         return None
#     text = str(value).strip()
#     if not text:
#         return None
#     try:
#         parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
#         if parsed.tzinfo is None:
#             parsed = parsed.replace(tzinfo=timezone.utc)
#         return parsed.astimezone(timezone.utc)
#     except ValueError:
#         for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%b %d, %Y", "%d/%m/%Y"):
#             try:
#                 return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
#             except ValueError:
#                 pass
#     return None


# def _resolve_current_history_date(
#     executions: list[dict[str, Any]],
#     defects: list[dict[str, Any]],
# ) -> datetime:
#     candidates: list[datetime] = []
#     for row in executions + defects:
#         value = _value(
#             row,
#             "Execution_Date",
#             "Execution Date",
#             "Detected_Date",
#             "Detected Date",
#             "Date",
#         )
#         parsed = _parse_date(value)
#         if parsed:
#             candidates.append(parsed)
#     return max(candidates) if candidates else datetime.now(timezone.utc)


# def _record_release_id(row: dict[str, Any]) -> str:
#     return _release_key(_value(row, "Release_ID", "Release ID", "release_id", "Release"))


# def _release_age(
#     record: dict[str, Any],
#     release_position: dict[str, int],
#     current_release_index: int | None,
# ) -> int | None:
#     record_release = _record_release_id(record)
#     if not record_release or current_release_index is None:
#         return None
#     record_index = release_position.get(record_release)
#     if record_index is None:
#         return None
#     return max(0, current_release_index - record_index)


# def _recency_weight(
#     record: dict[str, Any],
#     release_position: dict[str, int],
#     current_release_index: int | None,
#     current_date: datetime,
#     half_life_releases: float,
#     half_life_days: float,
# ) -> float:
#     weights: list[float] = []
#     age_releases = _release_age(record, release_position, current_release_index)
#     if age_releases is not None:
#         weights.append(0.5 ** (age_releases / half_life_releases))

#     date_value = _value(
#         record,
#         "Execution_Date",
#         "Execution Date",
#         "Detected_Date",
#         "Detected Date",
#         "Date",
#     )
#     record_date = _parse_date(date_value)
#     if record_date is not None:
#         age_days = max(0.0, (current_date - record_date).total_seconds() / 86400.0)
#         weights.append(0.5 ** (age_days / half_life_days))

#     if not weights:
#         return 1.0
#     return max(0.0, min(1.0, sum(weights) / len(weights)))


# def _defect_is_within_protection_window(
#     defect: dict[str, Any],
#     test_executions: list[dict[str, Any]],
#     observed_release_ids: list[str],
#     release_position: dict[str, int],
#     current_release_index: int | None,
#     protection_releases: int,
# ) -> bool:
#     """Determine whether a confirmed defect is within the release protection window.

#     The Jira defect records in this project may not carry Release_ID. In that case
#     the release is derived from the same test case's historical execution timeline
#     using Detected_Date, rather than treating missing release metadata as old/stale.
#     """
#     explicit_age = _release_age(defect, release_position, current_release_index)
#     if explicit_age is not None:
#         return explicit_age < protection_releases

#     inferred_release_id = _infer_defect_release_from_executions(
#         defect=defect,
#         test_executions=test_executions,
#     )
#     if inferred_release_id:
#         inferred_release_key = _release_key(inferred_release_id)
#         inferred_index = release_position.get(inferred_release_key)
#         if inferred_index is not None and current_release_index is not None:
#             return max(0, current_release_index - inferred_index) < protection_releases

#     # Preserve an explicit source-system protection flag as the final fallback.
#     return is_yes(_value(defect, "Defect_Catch_Protection", "Defect Catch Protection"))


# def _infer_defect_release_from_executions(
#     defect: dict[str, Any],
#     test_executions: list[dict[str, Any]],
# ) -> str:
#     """Infer a defect's historical release from dated executions for the same test.

#     Preferred match: latest execution on or before the defect detection date.
#     If no execution precedes the defect, use the earliest execution after it.
#     """
#     detected_value = _value(
#         defect,
#         "Detected_Date",
#         "Detected Date",
#         "Date",
#     )
#     detected_date = _parse_date(detected_value)

#     candidates: list[tuple[datetime, str]] = []
#     for execution in test_executions:
#         release_id = _value(
#             execution,
#             "Release_ID",
#             "Release ID",
#             "release_id",
#             "Release",
#         )
#         execution_date = _parse_date(
#             _value(
#                 execution,
#                 "Execution_Date",
#                 "Execution Date",
#                 "Date",
#             )
#         )
#         if not release_id or execution_date is None:
#             continue
#         candidates.append((_parse_date_value_or_min(execution_date), str(release_id).strip()))

#     if not candidates:
#         return ""

#     candidates.sort(key=lambda item: item[0])

#     if detected_date is None:
#         return candidates[-1][1]

#     prior = [item for item in candidates if item[0] <= detected_date]
#     if prior:
#         return prior[-1][1]

#     return candidates[0][1]


# def _parse_date_value_or_min(value: datetime) -> datetime:
#     """Small helper used to keep inferred-release candidates strongly typed."""
#     return value


# def _historical_category(
#     historical_value_score: float,
#     defect_catch_protection: bool,
#     flaky: bool,
#     insufficient_history: bool,
# ) -> str:
#     if defect_catch_protection:
#         return "HIGH_VALUE_DEFECT_CATCH"

#     if flaky:
#         return "FLAKY_REMEDIATE"

#     if insufficient_history:
#         return "INSUFFICIENT_HISTORY"

#     if historical_value_score >= 40:
#         return "HIGH_VALUE"

#     if historical_value_score >= 20:
#         return "MEDIUM_VALUE"

#     if historical_value_score > 0:
#         return "LOW_VALUE"

#     return "STABLE"


# def _execution_status(
#     row: dict[str, Any],
# ) -> str:
#     value = _value(
#         row,
#         "Execution_Status",
#         "Execution Status",
#         "Status",
#         "Result",
#     )

#     return _normalized(value)


# def _is_confirmed_defect(
#     row: dict[str, Any],
# ) -> bool:
#     confirmed_value = _value(
#         row,
#         "Confirmed",
#         "Is_Confirmed",
#         "Confirmed_Defect",
#         "Confirmed Defect",
#     )

#     if confirmed_value is not None:
#         return _normalized(
#             confirmed_value
#         ) in {
#             "YES",
#             "Y",
#             "TRUE",
#             "1",
#             "CONFIRMED",
#         }

#     # In this Jira model the Bug records are already defect records. If the
#     # business Confirmed field was not resolved, treat an ordinary Bug as
#     # confirmed unless an explicit rejecting state is present.
#     status = _normalized(
#         _value(
#             row,
#             "Status",
#             "Defect_Status",
#             "Defect Status",
#         )
#         or "CONFIRMED"
#     )

#     rejected_statuses = {
#         "REJECTED",
#         "DUPLICATE",
#         "INVALID",
#         "CANCELLED",
#         "CLOSED_NOT_A_DEFECT",
#         "NOT_A_DEFECT",
#     }

#     return (
#         status
#         not in rejected_statuses
#     )


# def _is_production_escape(
#     row: dict[str, Any],
# ) -> bool:
#     value = _value(
#         row,
#         "Production_Escape",
#         "Production Escape",
#         "Prod_Escape",
#         "Escaped_To_Production",
#     )

#     return _normalized(
#         value
#     ) in {
#         "YES",
#         "Y",
#         "TRUE",
#         "1",
#         "PRODUCTION",
#     }


# def _is_flaky(
#     row: dict[str, Any],
# ) -> bool:
#     if not row:
#         return False

#     status = _normalized(
#         _value(
#             row,
#             "Flaky_Status",
#             "Flaky Status",
#             "Status",
#         )
#     )
#     if status in {"FLAKY", "ACTIVE", "YES", "Y", "TRUE", "1"}:
#         return True

#     if is_yes(
#         _value(
#             row,
#             "Is_Flaky",
#             "Is Flaky",
#             "Flaky",
#         )
#     ):
#         return True

#     if _flaky_failure_count(row) > 0:
#         return True

#     flaky_rate_value = _value(
#         row,
#         "Flaky_Rate",
#         "Flaky Rate",
#         "FlakyRate",
#     )
#     try:
#         return float(flaky_rate_value or 0) > 0.0
#     except (TypeError, ValueError):
#         return False

# def _flaky_failure_count(
#     row: dict[str, Any],
# ) -> int:
#     value = _value(
#         row,
#         "Flaky_Failures",
#         "Flaky Failures",
#         "Failure_Count",
#         "Failure Count",
#     )

#     try:
#         return int(
#             float(value or 0)
#         )
#     except (
#         TypeError,
#         ValueError,
#     ):
#         return 0


# def _highest_severity(
#     defects: list[dict[str, Any]],
# ) -> str | None:
#     if not defects:
#         return None

#     severities = [
#         _normalized(
#             _value(
#                 defect,
#                 "Severity",
#                 "Defect_Severity",
#                 "Defect Severity",
#             )
#             or "LOW"
#         )
#         for defect in defects
#     ]

#     return max(
#         severities,
#         key=lambda value: (
#             SEVERITY_SCORES.get(
#                 value,
#                 0,
#             )
#         ),
#     )


# def _defect_severity_score(
#     defects: list[dict[str, Any]],
# ) -> float:
#     if not defects:
#         return 0.0

#     scores = []

#     for defect in defects:
#         severity = _normalized(
#             _value(
#                 defect,
#                 "Severity",
#                 "Defect_Severity",
#                 "Defect Severity",
#             )
#             or "LOW"
#         )

#         scores.append(
#             SEVERITY_SCORES.get(
#                 severity,
#                 20.0,
#             )
#         )

#     return max(scores)


# def _value(
#     row: dict[str, Any],
#     *possible_names: str,
# ) -> Any:
#     """
#     Return a value using normalized Excel-header matching.
#     """

#     if not row:
#         return None

#     normalized_row = {
#         _normalize_header(key): value
#         for key, value in row.items()
#     }

#     for possible_name in possible_names:
#         normalized_name = (
#             _normalize_header(
#                 possible_name
#             )
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


# def _extract_tc_id_from_record(row: dict[str, Any]) -> str:
#     """Recover a Test Case ID from common Jira text fields when the custom
#     Test Case ID field was not populated/resolved."""
#     import re

#     for field_name in (
#         "summary",
#         "Summary",
#         "description",
#         "Description",
#         "Policy_Reason",
#         "Reason",
#     ):
#         value = row.get(field_name)
#         if value is None:
#             continue
#         match = re.search(r"\bTC-\d+\b", str(value), re.IGNORECASE)
#         if match:
#             return match.group(0).upper()
#     return ""


# def _display(
#     value: Any,
# ) -> str:
#     if value is None or value == "":
#         return "Not available"

#     return str(value)

# # A2A: Specialist boundary. The Master Orchestrator calls this handler with a
# # serializable A2A envelope. The specialist never owns Jira/Excel connectivity.
# def handle_a2a_request(request: A2ARequest) -> A2AResponse:

#     try:

#         data = validate_message(
#             request,
#             receiver='Historical Execution Intelligence Agent',
#             message_types={
#                 'HISTORICAL_REQUEST',
#                 "AGENT_QUERY",
#             },
#         )

#         release_id = request.release_id

#         if request.message_type == "AGENT_QUERY":
#             return make_response(
#                 request,
#                 sender='Historical Execution Intelligence Agent',
#                 data=answer_agent_question(
#                     question=str(data.get("question") or ""),
#                     context=data.get(
#                         "agent_context",
#                         data,
#                     ),
#                 ),
#             )

#         result = analyze_historical_execution(
#             source_data=data.get(
#                 "source_data",
#                 {},
#             ),
#             release_id=release_id,
#         )

#         return make_response(
#             request,
#             sender='Historical Execution Intelligence Agent',
#             data=result,
#         )

#     except Exception as exc:

#         trace_error(
#             "HISTORICAL_AGENT_FAILED",
#             agent="Historical Execution Intelligence Agent",
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
#     "HISTORICAL_AGENT_QUERY",
#     agent="Historical Execution Intelligence Agent",
#     stage="HISTORICAL",
#     status="SUCCESS",
#     question=question,
#     )
#     return {
#         "status": "success",
#         "agent": 'Historical Execution Intelligence Agent',
#         "question": question,
#         "context": context,
#         "markdown": _agent_question_markdown(question, context),
#     }


# def _agent_question_markdown(question: str, context: dict[str, Any]) -> str:
#     import json
#     output = context.get("agent_output", context)
#     return "\n".join([
#         f"# {'Historical Execution Intelligence Agent'}",
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



#updated_historical_agent/tools.py
from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.observability.logger import (
    log_event,
    trace_error,
)
from app.observability.audit import audit_event
from app.models import A2ARequest, A2AResponse
from app.services.a2a import make_response, validate_message
from app.utils.helpers import is_yes



SEVERITY_SCORES: dict[str, float] = {
    "CRITICAL": 100.0,
    "BLOCKER": 100.0,
    "HIGH": 80.0,
    "MAJOR": 70.0,
    "MEDIUM": 50.0,
    "MINOR": 30.0,
    "LOW": 20.0,
    "TRIVIAL": 10.0,
}


REQUIRED_INPUTS: tuple[str, ...] = (
    "test_cases",
    "executions",
    "defects",
    "flaky_tests",
)


def analyze_historical_execution(
    source_data: dict[
        str,
        list[dict[str, Any]],
    ],
    release_id: str | None = None,
) -> dict[str, Any]:
    """
    Generate historical intelligence from orchestrator-supplied data.

    The Master Orchestrator must provide all raw rows through
    ``source_data``. This agent does not open or read source workbooks directly.

    Required source_data keys:
    - test_cases
    - executions
    - defects
    - flaky_tests

    Generated outputs:
    - Per-test historical summaries
    - Defect-catch protection
    - Flaky-test protection
    - Aggregate historical metrics
    - Compact agent-to-agent output
    - Markdown dashboard

    This function does not read:
    - historical_summary
    """
    try:
        log_event(
            "HISTORICAL_ANALYSIS_STARTED",
            agent="Historical Execution Intelligence Agent",
            stage="HISTORICAL",
            status="STARTED",
            release_id=release_id,
        )

        _validate_source_data(
            source_data
        )

        test_cases = source_data[
            "test_cases"
        ]
        executions = source_data[
            "executions"
        ]
        defect_rows = source_data[
            "defects"
        ]
        flaky_rows = source_data[
            "flaky_tests"
        ]

        normalized_release_id = (
            str(release_id).strip()
            if release_id is not None
            else None
        )

        log_event(
            "HISTORICAL_INPUTS_LOADED",
            agent="Historical Execution Intelligence Agent",
            stage="HISTORICAL",
            status="SUCCESS",
            test_cases=len(test_cases),
            executions=len(executions),
            defects=len(defect_rows),
            flaky_tests=len(flaky_rows),
        )

        test_case_lookup: dict[str, dict[str, Any]] = {}
        for row in test_cases:
            test_case_id = (
                _value(
                    row,
                    "Test_Case_ID",
                    "Test Case ID",
                    "TestCase_ID",
                    "Test_ID",
                    "TC_ID",
                )
                or _extract_tc_id_from_record(row)
            )
            if not test_case_id:
                continue
            test_case_lookup[str(test_case_id).strip().upper()] = row

        execution_groups: dict[
            str,
            list[dict[str, Any]],
        ] = defaultdict(list)

        defect_groups: dict[
            str,
            list[dict[str, Any]],
        ] = defaultdict(list)

        flaky_tests: dict[
            str,
            dict[str, Any],
        ] = {}

        known_test_ids = set(
            test_case_lookup.keys()
        )

        # ---------------------------------------------------------
        # Group historical execution records
        # ---------------------------------------------------------
        for row in executions:
            test_case_id = (
                _value(
                    row,
                    "Test_Case_ID",
                    "Test Case ID",
                    "TestCase_ID",
                    "Test_ID",
                    "TC_ID",
                )
                or _extract_tc_id_from_record(row)
            )

            if not test_case_id:
                continue

            normalized_test_case_id = str(
                test_case_id
            ).strip().upper()

            execution_groups[
                normalized_test_case_id
            ].append(row)

            known_test_ids.add(
                normalized_test_case_id
            )

        # ---------------------------------------------------------
        # Group defect records
        # ---------------------------------------------------------
        for row in defect_rows:
            test_case_id = _value(
                row,
                "Test_Case_ID",
                "Test Case ID",
                "TestCase_ID",
                "Test_ID",
                "TC_ID",
            ) or _extract_tc_id_from_record(row)

            if not test_case_id:
                continue

            normalized_test_case_id = str(
                test_case_id
            ).strip().upper()

            defect_groups[
                normalized_test_case_id
            ].append(row)

            known_test_ids.add(
                normalized_test_case_id
            )

        # ---------------------------------------------------------
        # Group flaky-test records
        # ---------------------------------------------------------
        for row in flaky_rows:
            test_case_id = _value(
                row,
                "Test_Case_ID",
                "Test Case ID",
                "TestCase_ID",
                "Test_ID",
                "TC_ID",
            ) or _extract_tc_id_from_record(row)

            if not test_case_id:
                continue

            normalized_test_case_id = str(
                test_case_id
            ).strip().upper()

            flaky_tests[
                normalized_test_case_id
            ] = row

            known_test_ids.add(
                normalized_test_case_id
            )

        summaries: dict[
            str,
            dict[str, Any],
        ] = {}


        # ---------------------------------------------------------
        # Generate one historical summary per test case
        # ---------------------------------------------------------
        for test_case_id in sorted(
            known_test_ids
        ):
            test_case = test_case_lookup.get(
                test_case_id,
                {},
            )

            test_executions = (
                execution_groups.get(
                    test_case_id,
                    [],
                )
            )

            linked_defects = defect_groups.get(
                test_case_id,
                [],
            )

            flaky_record = dict(
                flaky_tests.get(
                    test_case_id,
                    {},
                )
            )

            # If Jira has no separate flaky record for this test, accept an
            # execution-level flaky signal as a fallback.
            if not flaky_record:
                for execution in test_executions:
                    if is_yes(
                        _value(
                            execution,
                            "Is_Flaky",
                            "Is Flaky",
                            "Flaky",
                        )
                    ):
                        flaky_record = execution
                        break
                    execution_flaky_status = _normalized(
                        _value(
                            execution,
                            "Flaky_Status",
                            "Flaky Status",
                        )
                    )
                    if execution_flaky_status in {"FLAKY", "ACTIVE"}:
                        flaky_record = execution
                        break

            execution_count = len(
                test_executions
            )

            passed_count = sum(
                1
                for row in test_executions
                if _execution_status(row)
                in {
                    "PASS",
                    "PASSED",
                    "SUCCESS",
                }
            )

            failed_count = sum(
                1
                for row in test_executions
                if _execution_status(row)
                in {
                    "FAIL",
                    "FAILED",
                    "ERROR",
                    "BLOCKED",
                }
            )

            skipped_count = sum(
                1
                for row in test_executions
                if _execution_status(row)
                in {
                    "SKIP",
                    "SKIPPED",
                    "NOT_EXECUTED",
                    "NOT_RUN",
                }
            )

            pass_rate = (
                passed_count / execution_count
                if execution_count
                else 0.0
            )

            failure_rate = (
                failed_count / execution_count
                if execution_count
                else 0.0
            )

            confirmed_defects = [
                defect
                for defect in linked_defects
                if _is_confirmed_defect(defect)
            ]

            confirmed_defect_count = len(
                confirmed_defects
            )

            production_defect_count = sum(
                1
                for defect in confirmed_defects
                if _is_production_escape(defect)
            )

            highest_defect_severity = (
                _highest_severity(
                    confirmed_defects
                )
            )

            defect_severity_score = (
                _defect_severity_score(
                    confirmed_defects
                )
            )

            flaky = _is_flaky(
                flaky_record
            )

            flaky_failure_count = _flaky_failure_count(
                flaky_record
            )

            insufficient_history = (
                execution_count < 3
            )

            # -----------------------------------------------------
            # Historical value score
            # -----------------------------------------------------
            #
            # This score is intentionally aligned to the expected workbook:
            #
            # - Each historical failure contributes 6 points.
            # - Each confirmed defect contributes 20 points.
            # - Each production escape contributes 10 additional points.
            #
            # Examples:
            # - no failures, no defects => 0
            # - one failure => 6
            # - one confirmed defect => 20
            # - one failure + one confirmed defect => 26
            # -----------------------------------------------------
            historical_value_score = (
                failed_count * 6
                + confirmed_defect_count * 20
                + production_defect_count * 10
            )

            historical_value_score = min(
                max(
                    float(
                        historical_value_score
                    ),
                    0.0,
                ),
                100.0,
            )

            defect_catch_protection = (
                confirmed_defect_count > 0
                or any(
                    is_yes(
                        _value(
                            defect,
                            "Defect_Catch_Protection",
                            "Defect Catch Protection",
                        )
                    )
                    for defect
                    in confirmed_defects
                )
            )

            flaky_remediation_protection = (
                flaky
                or flaky_failure_count > 0
            )

            category = _historical_category(
                historical_value_score=(
                    historical_value_score
                ),
                defect_catch_protection=(
                    defect_catch_protection
                ),
                flaky=flaky,
                insufficient_history=(
                    insufficient_history
                ),
            )

            linked_defect_ids = sorted(
                {
                    str(defect_id).strip()
                    for defect
                    in linked_defects
                    if (
                        defect_id := _value(
                            defect,
                            "Defect_ID",
                            "Defect ID",
                            "Bug_ID",
                            "Bug ID",
                        )
                    )
                }
            )

            summaries[test_case_id] = {
                "Test_Case_ID": test_case_id,
                "Test_Name": _value(
                    test_case,
                    "Test_Name",
                    "Test Name",
                    "Test_Case_Name",
                    "Name",
                ),
                "Module_ID": _value(
                    test_case,
                    "Module_ID",
                    "Module ID",
                    "ModuleId",
                ),
                "Execution_Count": (
                    execution_count
                ),
                "Passed_Count": passed_count,
                "Failed_Count": failed_count,
                "Failure_Count": failed_count,
                "Skipped_Count": skipped_count,
                "Pass_Rate": round(
                    pass_rate,
                    4,
                ),
                "Failure_Rate": round(
                    failure_rate,
                    4,
                ),
                "Confirmed_Defects": (
                    confirmed_defect_count
                ),
                "Production_Defects": (
                    production_defect_count
                ),
                "Highest_Defect_Severity": (
                    highest_defect_severity
                ),
                "Defect_Severity_Score": round(
                    defect_severity_score,
                    2,
                ),
                "Flaky_Failures": (
                    flaky_failure_count
                ),
                "Historical_Value_Score": round(
                    historical_value_score,
                    2,
                ),
                "Category": category,
                "insufficient_history": (
                    insufficient_history
                ),
                "flaky": flaky,
                "flaky_remediation_protection": (
                    flaky_remediation_protection
                ),
                "defect_catch_protection": (
                    defect_catch_protection
                ),
                "linked_defect_ids": (
                    linked_defect_ids
                ),
                "linked_defects": linked_defects,
                "executions": test_executions,
            }

        # ---------------------------------------------------------
        # Aggregate summary
        # ---------------------------------------------------------
        total_execution_records = sum(
            len(records)
            for records
            in execution_groups.values()
        )

        tests_with_failures = sum(
            1
            for row in summaries.values()
            if row["Failed_Count"] > 0
        )

        tests_with_confirmed_defects = sum(
            1
            for row in summaries.values()
            if row["Confirmed_Defects"] > 0
        )

        defect_protected_test_ids = sorted(
            test_case_id
            for test_case_id, row
            in summaries.items()
            if row[
                "defect_catch_protection"
            ]
        )

        flaky_test_ids = sorted(
            test_case_id
            for test_case_id, row
            in summaries.items()
            if row["flaky"]
        )

        insufficient_history_test_ids = sorted(
            test_case_id
            for test_case_id, row
            in summaries.items()
            if row["insufficient_history"]
        )

        summary = {
            "total_test_cases": len(
                summaries
            ),
            "total_execution_records": (
                total_execution_records
            ),
            "passed_executions": sum(
                row["Passed_Count"]
                for row in summaries.values()
            ),
            "failed_executions": sum(
                row["Failed_Count"]
                for row in summaries.values()
            ),
            "skipped_executions": sum(
                row["Skipped_Count"]
                for row in summaries.values()
            ),
            "tests_with_failures": (
                tests_with_failures
            ),
            "confirmed_defects": sum(
                row["Confirmed_Defects"]
                for row in summaries.values()
            ),
            "production_defects": sum(
                row["Production_Defects"]
                for row in summaries.values()
            ),
            "tests_with_confirmed_defects": (
                tests_with_confirmed_defects
            ),
            "tests_with_insufficient_history": (
                len(
                    insufficient_history_test_ids
                )
            ),
            "flaky_test_count": len(
                flaky_test_ids
            ),
            "defect_protected_tests": len(
                defect_protected_test_ids
            ),
        }


        result: dict[str, Any] = {
            "release_id": (
                normalized_release_id
            ),
            "test_summaries": summaries,
            "flaky_tests": flaky_tests,
            "defects": dict(
                defect_groups
            ),
            "execution_records": dict(
                execution_groups
            ),
            "summary": summary,

            # Compact output intended for downstream scoring.
            "agent_output": {
                "release_id": (
                    normalized_release_id
                ),
                "test_summaries": {
                    test_case_id: {
                        "Historical_Value_Score": (
                            row[
                                "Historical_Value_Score"
                            ]
                        ),
                        "insufficient_history": (
                            row[
                                "insufficient_history"
                            ]
                        ),
                        "flaky": row["flaky"],
                        "flaky_remediation_protection": (
                            row[
                                "flaky_remediation_protection"
                            ]
                        ),
                        "defect_catch_protection": (
                            row[
                                "defect_catch_protection"
                            ]
                        ),
                        "Confirmed_Defects": (
                            row[
                                "Confirmed_Defects"
                            ]
                        ),
                        "Production_Defects": (
                            row[
                                "Production_Defects"
                            ]
                        ),
                        "Failed_Count": (
                            row["Failed_Count"]
                        ),
                        "Category": (
                            row["Category"]
                        ),
                    }
                    for test_case_id, row
                    in summaries.items()
                },
                "defect_protected_test_ids": (
                    defect_protected_test_ids
                ),
                "flaky_test_ids": (
                    flaky_test_ids
                ),
                "insufficient_history_test_ids": (
                    insufficient_history_test_ids
                ),
            },
        }


        result["markdown"] = (
            format_historical_cards(result)
        )

        log_event(
            "HISTORICAL_ANALYSIS_COMPLETED",
            agent="Historical Execution Intelligence Agent",
            stage="HISTORICAL",
            status="SUCCESS",
            total_tests=summary.get("total_test_cases", 0),
            total_executions=summary.get("total_execution_records", 0),
            flaky_tests=summary.get("flaky_test_count", 0),
            defect_protected_tests=summary.get("defect_protected_tests", 0),
            insufficient_history_tests=summary.get("tests_with_insufficient_history", 0),
        )

        audit_event(
            "HISTORICAL_ANALYSIS_COMPLETED",
            agent="Historical Execution Intelligence Agent",
            release_id=normalized_release_id,
            message=(
                f"Analyzed {summary.get('total_test_cases', 0)} tests "
                f"across {summary.get('total_execution_records', 0)} executions."
            ),
            details={
                "defect_protected_tests": summary.get("defect_protected_tests", 0),
                "flaky_tests": summary.get("flaky_test_count", 0),
                "insufficient_history_tests": summary.get("tests_with_insufficient_history", 0),
            },
        )

        return result

    except Exception as exc:
        trace_error(
            "HISTORICAL_AGENT_FAILED",
            agent="Historical Execution Intelligence Agent",
            error=exc,
            release_id=release_id,
        )
        raise



def _validate_source_data(
    source_data: dict[
        str,
        list[dict[str, Any]],
    ],
) -> None:
    """
    Validate raw rows supplied by the Master Orchestrator.
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
        for input_name in REQUIRED_INPUTS
        if input_name not in source_data
    ]

    if missing_inputs:
        raise ValueError(
            "Historical Agent is missing required "
            "orchestrator inputs: "
            f"{missing_inputs}"
        )

    invalid_inputs = [
        input_name
        for input_name in REQUIRED_INPUTS
        if not isinstance(
            source_data[
                input_name
            ],
            list,
        )
    ]

    if invalid_inputs:
        raise TypeError(
            "Historical Agent expected input "
            "rows as lists for: "
            f"{invalid_inputs}"
        )

def format_historical_cards(
    result: dict[str, Any],
) -> str:
    """
    Build a user-facing Markdown dashboard for ADK.
    """

    summaries = result.get(
        "test_summaries",
        {},
    )

    summary = result.get(
        "summary",
        {},
    )

    lines: list[str] = [
        "# Historical Execution Intelligence",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|---|---:|",
        "| Test cases analyzed | "
        f"{summary.get('total_test_cases', 0)} |",
        "| Historical executions | "
        f"{summary.get('total_execution_records', 0)} |",
        "| Passed executions | "
        f"{summary.get('passed_executions', 0)} |",
        "| Failed executions | "
        f"{summary.get('failed_executions', 0)} |",
        "| Skipped executions | "
        f"{summary.get('skipped_executions', 0)} |",
        "| Confirmed defects | "
        f"{summary.get('confirmed_defects', 0)} |",
        "| Production defects | "
        f"{summary.get('production_defects', 0)} |",
        "| Tests with confirmed defects | "
        f"{summary.get('tests_with_confirmed_defects', 0)} |",
        "| Flaky tests | "
        f"{summary.get('flaky_test_count', 0)} |",
        "| Insufficient-history tests | "
        f"{summary.get('tests_with_insufficient_history', 0)} |",
        "| Defect-protected tests | "
        f"{summary.get('defect_protected_tests', 0)} |",
        "",
        "---",
        "",
        "## Test History",
        "",
    ]

    if not summaries:
        lines.extend(
            [
                "> No historical test records were generated.",
                "",
            ]
        )

        return "\n".join(lines)

    for test_case_id, record in sorted(
        summaries.items()
    ):
        protection_labels: list[str] = []

        if record.get(
            "defect_catch_protection"
        ):
            protection_labels.append(
                "Defect-catch protection"
            )

        if record.get("flaky"):
            protection_labels.append(
                "Flaky remediation"
            )

        if record.get(
            "insufficient_history"
        ):
            protection_labels.append(
                "Insufficient history"
            )

        protection_text = (
            ", ".join(
                protection_labels
            )
            if protection_labels
            else "None"
        )

        linked_defects = record.get(
            "linked_defect_ids",
            [],
        )

        linked_defect_text = (
            ", ".join(linked_defects)
            if linked_defects
            else "None"
        )

        lines.extend(
            [
                f"> ### `{test_case_id}` — "
                f"{_display(record.get('Test_Name'))}",
                ">",
                "> **Module:** "
                f"`{_display(record.get('Module_ID'))}`",
                ">",
                "> **Executions:** "
                f"{record.get('Execution_Count', 0)}",
                ">",
                "> **Pass / Fail / Skip:** "
                f"{record.get('Passed_Count', 0)} / "
                f"{record.get('Failed_Count', 0)} / "
                f"{record.get('Skipped_Count', 0)}",
                ">",
                "> **Pass rate:** "
                f"{record.get('Pass_Rate', 0) * 100:.1f}%",
                ">",
                "> **Confirmed defects:** "
                f"{record.get('Confirmed_Defects', 0)}",
                ">",
                "> **Highest severity:** "
                f"`{_display(record.get('Highest_Defect_Severity'))}`",
                ">",
                "> **Historical value score:** "
                f"`{record.get('Historical_Value_Score', 0):.2f}`",
                ">",
                "> **Category:** "
                f"`{record.get('Category', 'STABLE')}`",
                ">",
                "> **Protection:** "
                f"{protection_text}",
                ">",
                "> **Linked defects:** "
                f"{linked_defect_text}",
                "",
            ]
        )

    return "\n".join(lines)


def _historical_category(
    historical_value_score: float,
    defect_catch_protection: bool,
    flaky: bool,
    insufficient_history: bool,
) -> str:
    if defect_catch_protection:
        return "HIGH_VALUE_DEFECT_CATCH"

    if flaky:
        return "FLAKY_REMEDIATE"

    if insufficient_history:
        return "INSUFFICIENT_HISTORY"

    if historical_value_score >= 40:
        return "HIGH_VALUE"

    if historical_value_score >= 20:
        return "MEDIUM_VALUE"

    if historical_value_score > 0:
        return "LOW_VALUE"

    return "STABLE"


def _execution_status(
    row: dict[str, Any],
) -> str:
    value = _value(
        row,
        "Execution_Status",
        "Execution Status",
        "Status",
        "Result",
    )

    return _normalized(value)


def _is_confirmed_defect(
    row: dict[str, Any],
) -> bool:
    confirmed_value = _value(
        row,
        "Confirmed",
        "Is_Confirmed",
        "Confirmed_Defect",
        "Confirmed Defect",
    )

    if confirmed_value is not None:
        return _normalized(
            confirmed_value
        ) in {
            "YES",
            "Y",
            "TRUE",
            "1",
            "CONFIRMED",
        }

    # In this Jira model the Bug records are already defect records. If the
    # business Confirmed field was not resolved, treat an ordinary Bug as
    # confirmed unless an explicit rejecting state is present.
    status = _normalized(
        _value(
            row,
            "Status",
            "Defect_Status",
            "Defect Status",
        )
        or "CONFIRMED"
    )

    rejected_statuses = {
        "REJECTED",
        "DUPLICATE",
        "INVALID",
        "CANCELLED",
        "CLOSED_NOT_A_DEFECT",
        "NOT_A_DEFECT",
    }

    return (
        status
        not in rejected_statuses
    )


def _is_production_escape(
    row: dict[str, Any],
) -> bool:
    value = _value(
        row,
        "Production_Escape",
        "Production Escape",
        "Prod_Escape",
        "Escaped_To_Production",
    )

    return _normalized(
        value
    ) in {
        "YES",
        "Y",
        "TRUE",
        "1",
        "PRODUCTION",
    }


def _is_flaky(
    row: dict[str, Any],
) -> bool:
    if not row:
        return False

    status = _normalized(
        _value(
            row,
            "Flaky_Status",
            "Flaky Status",
            "Status",
        )
    )
    if status in {"FLAKY", "ACTIVE", "YES", "Y", "TRUE", "1"}:
        return True

    if is_yes(
        _value(
            row,
            "Is_Flaky",
            "Is Flaky",
            "Flaky",
        )
    ):
        return True

    if _flaky_failure_count(row) > 0:
        return True

    flaky_rate_value = _value(
        row,
        "Flaky_Rate",
        "Flaky Rate",
        "FlakyRate",
    )
    try:
        return float(flaky_rate_value or 0) > 0.0
    except (TypeError, ValueError):
        return False

def _flaky_failure_count(
    row: dict[str, Any],
) -> int:
    value = _value(
        row,
        "Flaky_Failures",
        "Flaky Failures",
        "Failure_Count",
        "Failure Count",
    )

    try:
        return int(
            float(value or 0)
        )
    except (
        TypeError,
        ValueError,
    ):
        return 0


def _highest_severity(
    defects: list[dict[str, Any]],
) -> str | None:
    if not defects:
        return None

    severities = [
        _normalized(
            _value(
                defect,
                "Severity",
                "Defect_Severity",
                "Defect Severity",
            )
            or "LOW"
        )
        for defect in defects
    ]

    return max(
        severities,
        key=lambda value: (
            SEVERITY_SCORES.get(
                value,
                0,
            )
        ),
    )


def _defect_severity_score(
    defects: list[dict[str, Any]],
) -> float:
    if not defects:
        return 0.0

    scores = []

    for defect in defects:
        severity = _normalized(
            _value(
                defect,
                "Severity",
                "Defect_Severity",
                "Defect Severity",
            )
            or "LOW"
        )

        scores.append(
            SEVERITY_SCORES.get(
                severity,
                20.0,
            )
        )

    return max(scores)


def _value(
    row: dict[str, Any],
    *possible_names: str,
) -> Any:
    """
    Return a value using normalized Excel-header matching.
    """

    if not row:
        return None

    normalized_row = {
        _normalize_header(key): value
        for key, value in row.items()
    }

    for possible_name in possible_names:
        normalized_name = (
            _normalize_header(
                possible_name
            )
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


def _extract_tc_id_from_record(row: dict[str, Any]) -> str:
    """Recover a Test Case ID from common Jira text fields when the custom
    Test Case ID field was not populated/resolved."""
    import re

    for field_name in (
        "summary",
        "Summary",
        "description",
        "Description",
        "Policy_Reason",
        "Reason",
    ):
        value = row.get(field_name)
        if value is None:
            continue
        match = re.search(r"\bTC-\d+\b", str(value), re.IGNORECASE)
        if match:
            return match.group(0).upper()
    return ""


def _display(
    value: Any,
) -> str:
    if value is None or value == "":
        return "Not available"

    return str(value)


# A2A: Specialist boundary. The Master Orchestrator calls this handler with a
# serializable A2A envelope. The specialist never owns Jira/Excel connectivity.
def handle_a2a_request(request: A2ARequest) -> A2AResponse:

    try:

        data = validate_message(
            request,
            receiver='Historical Execution Intelligence Agent',
            message_types={
                'HISTORICAL_REQUEST',
                "AGENT_QUERY",
            },
        )

        release_id = request.release_id

        if request.message_type == "AGENT_QUERY":
            return make_response(
                request,
                sender='Historical Execution Intelligence Agent',
                data=answer_agent_question(
                    question=str(data.get("question") or ""),
                    context=data.get(
                        "agent_context",
                        data,
                    ),
                ),
            )

        result = analyze_historical_execution(
            source_data=data.get(
                "source_data",
                {},
            ),
            release_id=release_id,
        )

        return make_response(
            request,
            sender='Historical Execution Intelligence Agent',
            data=result,
        )

    except Exception as exc:

        trace_error(
            "HISTORICAL_AGENT_FAILED",
            agent="Historical Execution Intelligence Agent",
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
    "HISTORICAL_AGENT_QUERY",
    agent="Historical Execution Intelligence Agent",
    stage="HISTORICAL",
    status="SUCCESS",
    question=question,
    )
    return {
        "status": "success",
        "agent": 'Historical Execution Intelligence Agent',
        "question": question,
        "context": context,
        "markdown": _agent_question_markdown(question, context),
    }


def _agent_question_markdown(question: str, context: dict[str, Any]) -> str:
    import json
    output = context.get("agent_output", context)
    return "\n".join([
        f"# {'Historical Execution Intelligence Agent'}",
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


