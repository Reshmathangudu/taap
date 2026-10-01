# #old_policy_agent/tools.py
# from __future__ import annotations

# from typing import Any

# from app.observability.logger import (
#     log_event,
#     trace_error,
# )

# from app.observability.audit import audit_event

# from app.models import A2ARequest, A2AResponse
# from app.services.a2a import make_response, validate_message



# MANDATORY_RULE_TYPES = {
#     "MANDATORY_TEST",
#     "ALWAYS_EXECUTE",
#     "MUST_TEST",
#     "REGULATORY_MANDATORY",
#     "DO_NOT_EXCLUDE",
#     "EXCLUSION_PROHIBITED",
# }

# EXCLUSION_PROHIBITION_RULE_TYPES = {
#     "DO_NOT_EXCLUDE",
#     "EXCLUSION_PROHIBITED",
#     "MANDATORY_TEST",
#     "ALWAYS_EXECUTE",
#     "REGULATORY_MANDATORY",
# }


# REQUIRED_INPUT_KEYS: tuple[str, ...] = (
#     "policies",
#     "regulatory_tests",
#     "release_rules",
# )


# def calibrate_risk_policy(
#     source_data: dict[
#         str,
#         list[dict[str, Any]],
#     ],
#     release_type: str,
# ) -> dict[str, Any]:
#     log_event(
#     "POLICY_ANALYSIS_STARTED",
#     agent="Policy / Risk Appetite Calibration Agent",
#     stage="POLICY",
#     status="STARTED",
#     release_type=release_type,
#     )
#     """
#     Generate the applicable risk-policy profile for a release type.

#     The Master Orchestrator must provide all raw data through
#     ``source_data``. This agent does not read Jira, Excel, repositories,
#     or any external source directly.

#     Required source_data keys:
#     - policies
#     - regulatory_tests
#     - release_rules

#     Generated outputs:
#     - Tier policies
#     - Active regulatory tests
#     - Applicable release rules
#     - Mandatory-test identifiers
#     - Exclusion-prohibited test identifiers
#     - Overall exclusion limit
#     - Compact agent-to-agent output
#     - Markdown dashboard
#     """

#     _validate_source_data(
#         source_data
#     )

#     normalized_release_type = _normalized(
#         release_type
#     )

#     if not normalized_release_type:
#         raise ValueError(
#             "release_type cannot be empty"
#         )

#     policy_rows = source_data[
#         "policies"
#     ]
#     regulatory_rows = source_data[
#         "regulatory_tests"
#     ]
#     release_rule_rows = source_data[
#         "release_rules"
#     ]
#     log_event(
#     "POLICY_INPUTS_LOADED",
#     agent="Policy / Risk Appetite Calibration Agent",
#     stage="POLICY",
#     status="SUCCESS",
#     policies=len(policy_rows),
#     regulatory_tests=len(regulatory_rows),
#     release_rules=len(release_rule_rows),
#     )

#     # ---------------------------------------------------------
#     # 1. Select policies applicable to this release type
#     # ---------------------------------------------------------
#     applicable_policies = [
#         row
#         for row in policy_rows
#         if _row_applies_to_release_type(
#             row,
#             normalized_release_type,
#         )
#         and _is_active(row)
#     ]

#     if not applicable_policies:
#         available_release_types = sorted(
#             {
#                 _normalized(
#                     _value(
#                         row,
#                         "Release_Type",
#                         "Release Type",
#                     )
#                 )
#                 for row in policy_rows
#                 if _value(
#                     row,
#                     "Release_Type",
#                     "Release Type",
#                 )
#             }
#         )

#         raise ValueError(
#             "No active risk policy was found for "
#             f"release type {normalized_release_type!r}. "
#             f"Available policy release types: "
#             f"{available_release_types}"
#         )
#     log_event(
#         "POLICY_RULES_FILTERED",
#         agent="Policy / Risk Appetite Calibration Agent",
#         applicable_policies=len(
#         applicable_policies
#         ),
#         release_type=normalized_release_type,
#     )

#     # ---------------------------------------------------------
#     # 2. Build tier-level policy map
#     # ---------------------------------------------------------
#     tier_policies: dict[
#         str,
#         dict[str, Any],
#     ] = {}

#     general_policies: list[
#         dict[str, Any]
#     ] = []

#     for row in applicable_policies:
#         tier_value = _value(
#             row,
#             "Tier",
#             "Application_Tier",
#             "Application Tier",
#         )

#         if tier_value:
#             normalized_tier = _normalize_tier(
#                 tier_value
#             )

#             tier_policies[
#                 normalized_tier
#             ] = _normalize_policy_row(
#                 row,
#                 normalized_tier,
#             )
#         else:
#             general_policies.append(row)

#     # ---------------------------------------------------------
#     # 3. Identify active regulatory test cases
#     # ---------------------------------------------------------
#     regulatory_tests: dict[
#         str,
#         dict[str, Any],
#     ] = {}

#     for row in regulatory_rows:
#         if not _is_active(row):
#             continue

#         if not _row_applies_to_release_type(
#             row,
#             normalized_release_type,
#         ):
#             continue

#         test_case_id = _value(
#             row,
#             "Test_Case_ID",
#             "Test Case ID",
#             "TestCase_ID",
#             "Test_ID",
#             "TC_ID",
#         )

#         if not test_case_id:
#             continue

#         normalized_test_case_id = str(
#             test_case_id
#         ).strip()

#         regulatory_tests[
#             normalized_test_case_id
#         ] = {
#             **row,
#             "normalized_test_case_id": (
#                 normalized_test_case_id
#             ),
#             "policy_reason": _first_non_empty(
#                 _value(
#                     row,
#                     "Reason",
#                     "Policy_Reason",
#                     "Policy Reason",
#                     "Description",
#                 ),
#                 "Active regulatory test",
#             ),
#         }
#     log_event(
#     "REGULATORY_TESTS_IDENTIFIED",
#         agent="Policy / Risk Appetite Calibration Agent",
#         regulatory_tests=len(
#             regulatory_tests
#         ),
#     )    

#     # ---------------------------------------------------------
#     # 4. Identify applicable release rules
#     # ---------------------------------------------------------
#     release_rules = [
#         row
#         for row in release_rule_rows
#         if _row_applies_to_release_type(
#             row,
#             normalized_release_type,
#         )
#         and _is_active(row)
#     ]
#     log_event(
#         "RELEASE_RULES_APPLIED",
#         agent="Policy / Risk Appetite Calibration Agent",
#         release_rules=len(
#             release_rules
#         ),
#     )

#     mandatory_test_ids: set[str] = set(
#         regulatory_tests.keys()
#     )

#     exclusion_prohibited_test_ids: set[
#         str
#     ] = set(
#         regulatory_tests.keys()
#     )

#     always_execute_test_ids: set[str] = set(
#         regulatory_tests.keys()
#     )

#     mandatory_reasons: dict[
#         str,
#         list[str],
#     ] = {}

#     exclusion_prohibition_reasons: dict[
#         str,
#         list[str],
#     ] = {}

#     for test_case_id, row in (
#         regulatory_tests.items()
#     ):
#         reason = str(
#             row.get("policy_reason")
#             or "Regulatory test"
#         )

#         mandatory_reasons.setdefault(
#             test_case_id,
#             [],
#         ).append(reason)

#         exclusion_prohibition_reasons.setdefault(
#             test_case_id,
#             [],
#         ).append(reason)

#     # ---------------------------------------------------------
#     # 5. Process release-rule decisions
#     # ---------------------------------------------------------
#     global_rule_flags: list[
#         dict[str, Any]
#     ] = []

#     for rule in release_rules:
#         rule_type = _normalized(
#             _first_non_empty(
#                 _value(
#                     rule,
#                     "Rule_Type",
#                     "Rule Type",
#                     "Type",
#                 ),
#                 _value(
#                     rule,
#                     "Rule_Name",
#                     "Rule Name",
#                 ),
#             )
#         )

#         test_case_id = _value(
#             rule,
#             "Test_Case_ID",
#             "Test Case ID",
#             "TestCase_ID",
#             "Test_ID",
#             "TC_ID",
#         )

#         if "REGULATORY" in rule_type and "MUST" in rule_type:
#             rule_type = "REGULATORY_MANDATORY"
#         elif "DO_NOT_EXCLUDE" in rule_type or "EXCLUSION_PROHIBITED" in rule_type:
#             rule_type = "EXCLUSION_PROHIBITED"

#         rule_reason = str(
#             _first_non_empty(
#                 _value(
#                     rule,
#                     "Reason",
#                     "Rule_Reason",
#                     "Rule Reason",
#                     "Description",
#                 ),
#                 rule_type.replace(
#                     "_",
#                     " ",
#                 ).title(),
#             )
#         )

#         if test_case_id:
#             normalized_test_case_id = str(
#                 test_case_id
#             ).strip()

#             if (
#                 rule_type
#                 in MANDATORY_RULE_TYPES
#             ):
#                 mandatory_test_ids.add(
#                     normalized_test_case_id
#                 )

#                 mandatory_reasons.setdefault(
#                     normalized_test_case_id,
#                     [],
#                 ).append(rule_reason)

#             if (
#                 rule_type
#                 in EXCLUSION_PROHIBITION_RULE_TYPES
#             ):
#                 exclusion_prohibited_test_ids.add(
#                     normalized_test_case_id
#                 )

#                 exclusion_prohibition_reasons.setdefault(
#                     normalized_test_case_id,
#                     [],
#                 ).append(rule_reason)

#             if rule_type in {
#                 "ALWAYS_EXECUTE",
#                 "MANDATORY_TEST",
#                 "MUST_TEST",
#                 "REGULATORY_MANDATORY",
#             }:
#                 always_execute_test_ids.add(
#                     normalized_test_case_id
#                 )

#         else:
#             global_rule_flags.append(
#                 {
#                     "rule_type": rule_type,
#                     "reason": rule_reason,
#                     "source": rule,
#                 }
#             )

#     log_event(
#         "POLICY_DECISIONS_GENERATED",
#         agent="Policy / Risk Appetite Calibration Agent",
#         mandatory_tests=len(
#             mandatory_test_ids
#         ),
#         exclusion_prohibited=len(
#             exclusion_prohibited_test_ids
#         ),
#         always_execute=len(
#             always_execute_test_ids
#         ),
#     )

#     # ---------------------------------------------------------
#     # 6. Resolve exclusion controls
#     # ---------------------------------------------------------
#     overall_max_exclusion = (
#         _resolve_max_exclusion(
#             policies=applicable_policies,
#             rules=release_rules,
#         )
#     )

#     minimum_must_test_rate = (
#         _resolve_minimum_must_test_rate(
#             policies=applicable_policies,
#             rules=release_rules,
#         )
#     )

#     require_approval_for_exclusion = (
#         _resolve_boolean_rule(
#             rows=[
#                 *applicable_policies,
#                 *release_rules,
#             ],
#             field_names=(
#                 "Require_Approval_For_Exclusion",
#                 "Approval_Required_For_Exclusion",
#                 "Exclusion_Approval_Required",
#             ),
#             default=True,
#         )
#     )

#     high_risk_exclusion_prohibited = (
#         _resolve_boolean_rule(
#             rows=[
#                 *applicable_policies,
#                 *release_rules,
#             ],
#             field_names=(
#                 "High_Risk_Exclusion_Prohibited",
#                 "Prohibit_High_Risk_Exclusion",
#                 "No_High_Risk_Exclusion",
#             ),
#             default=True,
#         )
#     )

#     # ---------------------------------------------------------
#     # 7. Build test-level policy decisions
#     # ---------------------------------------------------------
#     all_policy_test_ids = sorted(
#         mandatory_test_ids
#         | exclusion_prohibited_test_ids
#         | always_execute_test_ids
#     )

#     test_policy_decisions: dict[
#         str,
#         dict[str, Any],
#     ] = {}

#     for test_case_id in all_policy_test_ids:
#         test_policy_decisions[
#             test_case_id
#         ] = {
#             "test_case_id": test_case_id,
#             "regulatory": (
#                 test_case_id
#                 in regulatory_tests
#             ),
#             "mandatory": (
#                 test_case_id
#                 in mandatory_test_ids
#             ),
#             "always_execute": (
#                 test_case_id
#                 in always_execute_test_ids
#             ),
#             "exclusion_prohibited": (
#                 test_case_id
#                 in exclusion_prohibited_test_ids
#             ),
#             "mandatory_reasons": (
#                 mandatory_reasons.get(
#                     test_case_id,
#                     [],
#                 )
#             ),
#             "exclusion_prohibition_reasons": (
#                 exclusion_prohibition_reasons.get(
#                     test_case_id,
#                     [],
#                 )
#             ),
#         }

#     summary = {
#         "release_type": (
#             normalized_release_type
#         ),
#         "tier_policy_count": len(
#             tier_policies
#         ),
#         "general_policy_count": len(
#             general_policies
#         ),
#         "regulatory_test_count": len(
#             regulatory_tests
#         ),
#         "release_rule_count": len(
#             release_rules
#         ),
#         "mandatory_test_count": len(
#             mandatory_test_ids
#         ),
#         "always_execute_test_count": len(
#             always_execute_test_ids
#         ),
#         "exclusion_prohibited_test_count": len(
#             exclusion_prohibited_test_ids
#         ),
#         "overall_max_exclusion": (
#             overall_max_exclusion
#         ),
#         "overall_max_exclusion_percent": round(
#             overall_max_exclusion * 100,
#             2,
#         ),
#         "minimum_must_test_rate": (
#             minimum_must_test_rate
#         ),
#         "minimum_must_test_percent": round(
#             minimum_must_test_rate * 100,
#             2,
#         ),
#         "require_approval_for_exclusion": (
#             require_approval_for_exclusion
#         ),
#         "high_risk_exclusion_prohibited": (
#             high_risk_exclusion_prohibited
#         ),
#     }
#     log_event(
#     "POLICY_SUMMARY_CREATED",
#     agent="Policy / Risk Appetite Calibration Agent",
#     release_type=normalized_release_type,
#     overall_max_exclusion=overall_max_exclusion,
#     minimum_must_test_rate=minimum_must_test_rate,
#     )

#     result: dict[str, Any] = {
#         "release_type": normalized_release_type,
#         "approval_role": _first_non_empty(
#             *[
#                 _value(
#                     row,
#                     "Over_Cap_Approval_Role",
#                     "Over Cap Approval Role",
#                 )
#                 for row in applicable_policies
#             ],
#             "QA_LEAD",
#         ),
#         "tier_policies": tier_policies,
#         "general_policies": general_policies,
#         "regulatory_tests": regulatory_tests,
#         "release_rules": release_rules,
#         "mandatory_test_ids": sorted(
#             mandatory_test_ids
#         ),
#         "always_execute_test_ids": sorted(
#             always_execute_test_ids
#         ),
#         "exclusion_prohibited_test_ids": sorted(
#             exclusion_prohibited_test_ids
#         ),
#         "mandatory_reasons": mandatory_reasons,
#         "exclusion_prohibition_reasons": (
#             exclusion_prohibition_reasons
#         ),
#         "test_policy_decisions": (
#             test_policy_decisions
#         ),
#         "global_rule_flags": (
#             global_rule_flags
#         ),
#         "overall_max_exclusion": (
#             overall_max_exclusion
#         ),
#         "minimum_must_test_rate": (
#             minimum_must_test_rate
#         ),
#         "require_approval_for_exclusion": (
#             require_approval_for_exclusion
#         ),
#         "high_risk_exclusion_prohibited": (
#             high_risk_exclusion_prohibited
#         ),
#         "summary": summary,

#         # Compact structured payload for Scoring and Governance agents.
#         "agent_output": {
#             "release_type": normalized_release_type,
#             "approval_role": _first_non_empty(
#                 *[
#                     _value(
#                         row,
#                         "Over_Cap_Approval_Role",
#                         "Over Cap Approval Role",
#                     )
#                     for row in applicable_policies
#                 ],
#                 "QA_LEAD",
#             ),
#             "tier_policies": tier_policies,
#             "mandatory_test_ids": sorted(
#                 mandatory_test_ids
#             ),
#             "always_execute_test_ids": sorted(
#                 always_execute_test_ids
#             ),
#             "regulatory_test_ids": sorted(
#                 regulatory_tests.keys()
#             ),
#             "exclusion_prohibited_test_ids": sorted(
#                 exclusion_prohibited_test_ids
#             ),
#             "test_policy_decisions": (
#                 test_policy_decisions
#             ),
#             "overall_max_exclusion": (
#                 overall_max_exclusion
#             ),
#             "minimum_must_test_rate": (
#                 minimum_must_test_rate
#             ),
#             "require_approval_for_exclusion": (
#                 require_approval_for_exclusion
#             ),
#             "high_risk_exclusion_prohibited": (
#                 high_risk_exclusion_prohibited
#             ),
#         },
#     }

#     log_event(
#        "POLICY_ANALYSIS_COMPLETED",
#         agent="Policy / Risk Appetite Calibration Agent",
#         stage="POLICY",
#         status="SUCCESS",
#         regulatory_tests=len(
#             regulatory_tests
#         ),
#        release_rules=len(
#             release_rules
#         ),
#     )

#     audit_event(
#     "POLICY_ANALYSIS_COMPLETED",
#     agent="Policy / Risk Appetite Calibration Agent",
#     message=(
#         f"Processed {len(regulatory_tests)} regulatory tests "
#         f"and {len(release_rules)} release rules."
#     ),
#     details={
#         "release_type": normalized_release_type,
#         "mandatory_tests": len(
#             mandatory_test_ids
#         ),
#         "always_execute_tests": len(
#             always_execute_test_ids
#         ),
#         "exclusion_prohibited_tests": len(
#             exclusion_prohibited_test_ids
#         ),
#         "overall_max_exclusion":
#             overall_max_exclusion,
#     },
#     )

#     result["markdown"] = (
#         format_policy_cards(result)
#     )

#     return result



# def _validate_source_data(
#     source_data: dict[
#         str,
#         list[dict[str, Any]],
#     ],
# ) -> None:
#     """
#     Validate raw data blocks supplied by the Master Orchestrator.
#     """

#     if not isinstance(
#         source_data,
#         dict,
#     ):
#         raise TypeError(
#             "source_data must be a dictionary "
#             "provided by the Master Orchestrator."
#         )

#     missing_blocks = [
#         block_name
#         for block_name in REQUIRED_INPUT_KEYS
#         if block_name not in source_data
#     ]

#     if missing_blocks:
#         raise ValueError(
#             "Policy Agent is missing required "
#             "orchestrator data blocks: "
#             f"{missing_blocks}"
#         )

#     invalid_blocks = [
#         block_name
#         for block_name in REQUIRED_INPUT_KEYS
#         if not isinstance(
#             source_data[
#                 block_name
#             ],
#             list,
#         )
#     ]

#     if invalid_blocks:
#         raise TypeError(
#             "Policy Agent expected orchestrator "
#             "data blocks as lists for: "
#             f"{invalid_blocks}"
#         )

# def format_policy_cards(
#     result: dict[str, Any],
# ) -> str:
#     """
#     Build a user-facing Markdown dashboard for ADK.
#     """

#     summary = result.get(
#         "summary",
#         {},
#     )
#     tier_policies = result.get(
#         "tier_policies",
#         {},
#     )
#     regulatory_tests = result.get(
#         "regulatory_tests",
#         {},
#     )
#     release_rules = result.get(
#         "release_rules",
#         [],
#     )
#     test_policy_decisions = result.get(
#         "test_policy_decisions",
#         {},
#     )

#     lines: list[str] = [
#         "# Policy / Risk Appetite Calibration",
#         "",
#         "## Policy Summary",
#         "",
#         "> ### Release Profile",
#         ">",
#         "> **Release type:** "
#         f"`{result.get('release_type', 'UNKNOWN')}`",
#         ">",
#         "> **Maximum exclusion:** "
#         f"`{summary.get('overall_max_exclusion_percent', 0):.2f}%`",
#         ">",
#         "> **Minimum MUST_TEST rate:** "
#         f"`{summary.get('minimum_must_test_percent', 0):.2f}%`",
#         ">",
#         "> **Exclusion approval required:** "
#         f"`{'Yes' if summary.get('require_approval_for_exclusion') else 'No'}`",
#         ">",
#         "> **High-risk exclusion prohibited:** "
#         f"`{'Yes' if summary.get('high_risk_exclusion_prohibited') else 'No'}`",
#         "",
#         "---",
#         "",
#         "## Counts",
#         "",
#         "| Metric | Count |",
#         "|---|---:|",
#         "| Tier policies | "
#         f"{summary.get('tier_policy_count', 0)} |",
#         "| Regulatory tests | "
#         f"{summary.get('regulatory_test_count', 0)} |",
#         "| Release rules | "
#         f"{summary.get('release_rule_count', 0)} |",
#         "| Mandatory tests | "
#         f"{summary.get('mandatory_test_count', 0)} |",
#         "| Always-execute tests | "
#         f"{summary.get('always_execute_test_count', 0)} |",
#         "| Exclusion-prohibited tests | "
#         f"{summary.get('exclusion_prohibited_test_count', 0)} |",
#         "",
#         "---",
#         "",
#         "## Tier Policies",
#         "",
#     ]

#     if tier_policies:
#         for tier, policy in sorted(
#             tier_policies.items()
#         ):
#             lines.extend(
#                 [
#                     f"> ### `{tier}`",
#                     ">",
#                     "> **Minimum coverage:** "
#                     f"`{policy.get('minimum_coverage_percent', 0):.2f}%`",
#                     ">",
#                     "> **Maximum exclusion:** "
#                     f"`{policy.get('maximum_exclusion_percent', 0):.2f}%`",
#                     ">",
#                     "> **Mandatory execution:** "
#                     f"`{'Yes' if policy.get('mandatory_execution') else 'No'}`",
#                     ">",
#                     "> **Approval required:** "
#                     f"`{'Yes' if policy.get('approval_required') else 'No'}`",
#                     ">",
#                     "> **Policy status:** "
#                     f"`{_display(_first_non_empty(policy.get('Policy_Status'), policy.get('Policy Status'), policy.get('Status'), 'ACTIVE'))}`",
#                     "",
#                 ]
#             )
#     else:
#         lines.extend(
#             [
#                 "> No tier-specific policies were found.",
#                 "",
#             ]
#         )

#     lines.extend(
#         [
#             "---",
#             "",
#             "## Regulatory Tests",
#             "",
#         ]
#     )

#     if regulatory_tests:
#         for test_case_id, row in sorted(
#             regulatory_tests.items()
#         ):
#             lines.extend(
#                 [
#                     f"> ### `{test_case_id}`",
#                     ">",
#                     "> **Reason:** "
#                     f"{_display(row.get('policy_reason'))}",
#                     ">",
#                     "> **Decision:** "
#                     "`MANDATORY — DO NOT EXCLUDE`",
#                     "",
#                 ]
#             )
#     else:
#         lines.extend(
#             [
#                 "> No active regulatory tests were found.",
#                 "",
#             ]
#         )

#     lines.extend(
#         [
#             "---",
#             "",
#             "## Applicable Release Rules",
#             "",
#         ]
#     )

#     if release_rules:
#         for rule in release_rules:
#             rule_type = _normalized(
#                 _value(
#                     rule,
#                     "Rule_Type",
#                     "Rule Type",
#                     "Type",
#                 )
#             )
#             test_case_id = _display(
#                 _value(
#                     rule,
#                     "Test_Case_ID",
#                     "Test Case ID",
#                     "TestCase_ID",
#                 )
#             )
#             reason = _display(
#                 _first_non_empty(
#                     _value(
#                         rule,
#                         "Reason",
#                         "Rule_Reason",
#                         "Description",
#                     ),
#                     "No description provided",
#                 )
#             )

#             lines.extend(
#                 [
#                     f"> ### `{rule_type}`",
#                     ">",
#                     f"> **Test case:** `{test_case_id}`",
#                     ">",
#                     f"> **Reason:** {reason}",
#                     "",
#                 ]
#             )
#     else:
#         lines.extend(
#             [
#                 "> No release rules were applicable.",
#                 "",
#             ]
#         )

#     lines.extend(
#         [
#             "---",
#             "",
#             "## Test Policy Decisions",
#             "",
#             "| Test Case | Regulatory | Mandatory | Always Execute | Exclusion Prohibited |",
#             "|---|---|---|---|---|",
#         ]
#     )

#     for test_case_id, decision in sorted(
#         test_policy_decisions.items()
#     ):
#         lines.append(
#             f"| `{test_case_id}` "
#             f"| {_yes_no(decision.get('regulatory'))} "
#             f"| {_yes_no(decision.get('mandatory'))} "
#             f"| {_yes_no(decision.get('always_execute'))} "
#             f"| {_yes_no(decision.get('exclusion_prohibited'))} |"
#         )

#     return "\n".join(lines)


# def _normalize_policy_row(
#     row: dict[str, Any],
#     tier: str,
# ) -> dict[str, Any]:
#     minimum_coverage = _fraction(
#         _first_non_empty(
#             _value(
#                 row,
#                 "Minimum_Coverage",
#                 "Minimum Coverage",
#                 "Min_Coverage",
#             ),
#             _default_minimum_coverage(
#                 tier
#             ),
#         )
#     )

#     # Tier policies use Tier Max Exclusion only. The release-wide Overall Max
#     # Exclusion is resolved separately and must not be replaced by a Tier-1
#     # value of zero.
#     maximum_exclusion = _fraction(
#         _first_non_empty(
#             _value(
#                 row,
#                 "Tier_Max_Exclusion",
#                 "Tier Max Exclusion",
#             ),
#             _default_maximum_exclusion(
#                 tier
#             ),
#         )
#     )

#     mandatory_execution = _boolean(
#         _first_non_empty(
#             _value(
#                 row,
#                 "Mandatory_Execution",
#                 "Mandatory Execution",
#                 "Always_Execute",
#             ),
#             tier == "TIER_1",
#         )
#     )

#     approval_required = _boolean(
#         _first_non_empty(
#             _value(
#                 row,
#                 "Approval_Required",
#                 "Approval Required",
#                 "Exclusion_Approval_Required",
#             ),
#             tier in {
#                 "TIER_1",
#                 "TIER_2",
#             },
#         )
#     )

#     approval_role = _first_non_empty(
#         _value(
#             row,
#             "Over_Cap_Approval_Role",
#             "Over Cap Approval Role",
#         ),
#         "QA_LEAD",
#     )

#     return {
#         **row,
#         "tier": tier,
#         "minimum_coverage": (
#             minimum_coverage
#         ),
#         "minimum_coverage_percent": round(
#             minimum_coverage * 100,
#             2,
#         ),
#         "maximum_exclusion": (
#             maximum_exclusion
#         ),
#         "maximum_exclusion_percent": round(
#             maximum_exclusion * 100,
#             2,
#         ),
#         "mandatory_execution": (
#             mandatory_execution
#         ),
#         "approval_required": approval_required,
#         "approval_role": approval_role,
#         "Policy_Status": _first_non_empty(
#             _value(row, "Policy_Status", "Policy Status", "PolicyStatus"),
#             _value(row, "Status"),
#             "ACTIVE",
#         ),
#         "Overall_Max_Exclusion": _first_non_empty(
#             _value(
#                 row,
#                 "Overall_Max_Exclusion",
#                 "Overall Max Exclusion",
#                 "Maximum_Exclusion",
#                 "Maximum Exclusion",
#             ),
#         ),
#     }


# def _resolve_max_exclusion(
#     policies: list[dict[str, Any]],
#     rules: list[dict[str, Any]],
# ) -> float:
#     """Resolve the release-wide exclusion cap.

#     Important: ``Tier_Max_Exclusion`` is a tier-level control and must not
#     override the release-wide ``Overall_Max_Exclusion`` value. The previous
#     implementation also accepted generic ``Maximum_Exclusion`` fields, which
#     could accidentally pull a Tier 1 value of 0.0 into the overall cap.
#     """
#     values: list[float] = []

#     for row in [*policies, *rules]:
#         value = _value(
#             row,
#             "Overall_Max_Exclusion",
#             "Overall Max Exclusion",
#             "Overall_Max_Exclusion_Rate",
#             "Overall Max Exclusion Rate",
#         )

#         if value is None or value == "":
#             continue

#         values.append(_fraction(value))

#     # The most restrictive explicit release-wide cap wins. For this project
#     # the configured business default is 30% when Jira has no global cap row.
#     # A Tier Max Exclusion of 0 must never become the global cap.
#     if values:
#         positive_or_zero = [v for v in values if v >= 0.0]
#         return min(positive_or_zero) if positive_or_zero else 0.30
#     return 0.30


# def _resolve_minimum_must_test_rate(
#     policies: list[dict[str, Any]],
#     rules: list[dict[str, Any]],
# ) -> float:
#     values: list[float] = []

#     for row in [
#         *policies,
#         *rules,
#     ]:
#         value = _value(
#             row,
#             "Minimum_Must_Test_Rate",
#             "Minimum Must Test Rate",
#             "Min_Must_Test_Percentage",
#             "Minimum_Mandatory_Coverage",
#         )

#         if value is None:
#             continue

#         values.append(
#             _fraction(value)
#         )

#     return (
#         max(values)
#         if values
#         else 0.0
#     )


# def _resolve_boolean_rule(
#     rows: list[dict[str, Any]],
#     field_names: tuple[str, ...],
#     default: bool,
# ) -> bool:
#     values: list[bool] = []

#     for row in rows:
#         value = _value(
#             row,
#             *field_names,
#         )

#         if value is None:
#             continue

#         values.append(
#             _boolean(value)
#         )

#     if not values:
#         return default

#     # Any restrictive True setting wins.
#     return any(values)


# def _row_applies_to_release_type(
#     row: dict[str, Any],
#     release_type: str,
# ) -> bool:
#     row_release_type = _normalized(
#         _first_non_empty(
#             _value(
#                 row,
#                 "Release_Type",
#                 "Release Type",
#             ),
#             "ALL",
#         )
#     )

#     return row_release_type in {
#         release_type,
#         "ALL",
#         "ANY",
#         "",
#     }


# def _is_active(
#     row: dict[str, Any],
# ) -> bool:
#     """
#     Business-active evaluation.

#     Policy Status/Rule Status/Test Status are authoritative when present.
#     Jira workflow Status such as "To Do" is never treated as an inactive
#     business status by itself.
#     """
#     business_status = _value(
#         row,
#         "Policy_Status",
#         "Policy Status",
#         "PolicyStatus",
#         "Rule_Status",
#         "Rule Status",
#         "Test_Status",
#         "Test Status",
#         "Regulatory_Status",
#         "Regulatory Status",
#         "Approval_Status",
#         "Approval Status",
#     )

#     if business_status not in (None, ""):
#         return _normalized(business_status) in {
#             "ACTIVE",
#             "APPROVED",
#             "ENABLED",
#             "CURRENT",
#             "VALID",
#             "YES",
#         }

#     # No business status on the row: absence of an inactive marker means the
#     # policy/rule/test is usable. Do not use Jira workflow Status.
#     return True

# def _default_minimum_coverage(
#     tier: str,
# ) -> float:
#     return {
#         "TIER_1": 1.00,
#         "TIER_2": 0.70,
#         "TIER_3": 0.50,
#         "TIER_4": 0.20,
#     }.get(
#         tier,
#         0.50,
#     )


# def _default_maximum_exclusion(
#     tier: str,
# ) -> float:
#     return {
#         "TIER_1": 0.05,
#         "TIER_2": 0.10,
#         "TIER_3": 0.30,
#         "TIER_4": 0.60,
#     }.get(
#         tier,
#         0.10,
#     )


# def _normalize_tier(
#     value: Any,
# ) -> str:
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


# def _fraction(
#     value: Any,
# ) -> float:
#     numeric = _to_float(
#         value,
#         default=0.0,
#     )

#     if numeric > 1:
#         numeric /= 100

#     return min(
#         max(
#             numeric,
#             0.0,
#         ),
#         1.0,
#     )


# def _boolean(
#     value: Any,
# ) -> bool:
#     if isinstance(
#         value,
#         bool,
#     ):
#         return value

#     return _normalized(
#         value
#     ) in {
#         "YES",
#         "Y",
#         "TRUE",
#         "1",
#         "ACTIVE",
#         "ENABLED",
#         "REQUIRED",
#         "MANDATORY",
#     }


# def _value(
#     row: dict[str, Any],
#     *possible_names: str,
# ) -> Any:
#     """
#     Return a value using normalized field-name matching.
#     """

#     if not row:
#         return None

#     normalized_row = {
#         _normalize_header(key): value
#         for key, value
#         in row.items()
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


# def _first_non_empty(
#     *values: Any,
# ) -> Any:
#     for value in values:
#         if (
#             value is not None
#             and value != ""
#         ):
#             return value

#     return None


# def _display(
#     value: Any,
# ) -> str:
#     if (
#         value is None
#         or value == ""
#     ):
#         return "Not available"

#     return str(value)


# def _yes_no(
#     value: Any,
# ) -> str:
#     return (
#         "Yes"
#         if bool(value)
#         else "No"
#     )


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
#             receiver='Policy / Risk Appetite Calibration Agent',
#             message_types={
#                 'POLICY_REQUEST',
#                 "AGENT_QUERY",
#             },
#         )

#         release_id = request.release_id

#         # A2A: All stage inputs arrive in request["data"], prepared by the orchestrator.
#         if request.message_type == "AGENT_QUERY":

#             return make_response(
#                 request,
#                 sender='Policy / Risk Appetite Calibration Agent',
#                 data=answer_agent_question(
#                     question=str(
#                         data.get("question") or ""
#                     ),
#                     context=data.get(
#                         "agent_context",
#                         data,
#                     ),
#                 ),
#             )

#         result = calibrate_risk_policy(
#             source_data=data.get(
#                 "source_data",
#                 {},
#             ),
#             release_type=str(
#                 data.get("release_type")
#                 or ""
#             ).strip().upper(),
#         )

#         return make_response(
#             request,
#             sender='Policy / Risk Appetite Calibration Agent',
#             data=result,
#         )

#     except Exception as exc:

#         trace_error(
#             "POLICY_AGENT_FAILED",
#             agent="Policy / Risk Appetite Calibration Agent",
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
#     "POLICY_AGENT_QUERY",
#     agent="Policy / Risk Appetite Calibration Agent",
#     stage="POLICY",
#     status="SUCCESS",
#     question=question,
#     )

#     return {
#         "status": "success",
#         "agent": 'Policy / Risk Appetite Calibration Agent',
#         "question": question,
#         "context": context,
#         "markdown": _agent_question_markdown(question, context),
#     }


# def _agent_question_markdown(question: str, context: dict[str, Any]) -> str:
#     import json
#     output = context.get("agent_output", context)
#     return "\n".join([
#         f"# {'Policy / Risk Appetite Calibration Agent'}",
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



#old_policy_agent/tools.py
from __future__ import annotations

from typing import Any

from app.observability.logger import (
    log_event,
    trace_error,
)

from app.observability.audit import audit_event

from app.models import A2ARequest, A2AResponse
from app.services.a2a import make_response, validate_message



MANDATORY_RULE_TYPES = {
    "MANDATORY_TEST",
    "ALWAYS_EXECUTE",
    "MUST_TEST",
    "REGULATORY_MANDATORY",
    "DO_NOT_EXCLUDE",
    "EXCLUSION_PROHIBITED",
}

EXCLUSION_PROHIBITION_RULE_TYPES = {
    "DO_NOT_EXCLUDE",
    "EXCLUSION_PROHIBITED",
    "MANDATORY_TEST",
    "ALWAYS_EXECUTE",
    "REGULATORY_MANDATORY",
}


REQUIRED_INPUT_KEYS: tuple[str, ...] = (
    "policies",
    "regulatory_tests",
    "release_rules",
)


def calibrate_risk_policy(
    source_data: dict[
        str,
        list[dict[str, Any]],
    ],
    release_type: str,
) -> dict[str, Any]:
    """
    Generate the applicable risk-policy profile for a release type.

    The Master Orchestrator must provide all raw data through
    ``source_data``. This agent does not read Jira, Excel, repositories,
    or any external source directly.

    Required source_data keys:
    - policies
    - regulatory_tests
    - release_rules

    Generated outputs:
    - Tier policies
    - Active regulatory tests
    - Applicable release rules
    - Mandatory-test identifiers
    - Exclusion-prohibited test identifiers
    - Overall exclusion limit
    - Compact agent-to-agent output
    - Markdown dashboard
    """
    log_event(
    "POLICY_ANALYSIS_STARTED",
    agent="Policy / Risk Appetite Calibration Agent",
    stage="POLICY",
    status="STARTED",
    release_type=release_type,
    )

    _validate_source_data(
        source_data
    )

    normalized_release_type = _normalized(
        release_type
    )

    if not normalized_release_type:
        raise ValueError(
            "release_type cannot be empty"
        )

    policy_rows = source_data[
        "policies"
    ]
    regulatory_rows = source_data[
        "regulatory_tests"
    ]
    release_rule_rows = source_data[
        "release_rules"
    ]
    log_event(
    "POLICY_INPUTS_LOADED",
    agent="Policy / Risk Appetite Calibration Agent",
    stage="POLICY",
    status="SUCCESS",
    policies=len(policy_rows),
    regulatory_tests=len(regulatory_rows),
    release_rules=len(release_rule_rows),
    )

    # ---------------------------------------------------------
    # 1. Select policies applicable to this release type
    # ---------------------------------------------------------
    applicable_policies = [
        row
        for row in policy_rows
        if _row_applies_to_release_type(
            row,
            normalized_release_type,
        )
        and _is_active(row)
    ]

    policy_fallback_applied = False

    if not applicable_policies:
        available_release_types = sorted(
            {
                _normalized(
                    _value(
                        row,
                        "Release_Type",
                        "Release Type",
                    )
                )
                for row in policy_rows
                if _value(
                    row,
                    "Release_Type",
                    "Release Type",
                )
            }
        )

        # No active Policy-type Jira issue applies to this release — most
        # often because the project has none at all yet. Rather than block
        # the whole run, proceed with an empty applicable_policies list:
        # every downstream field already has its own established default
        # when no policy row supplies it (_resolve_max_exclusion falls back
        # to 0.30, approval_role falls back to "QA_LEAD", etc. — see below),
        # so this simply means "no Jira-sourced override", not "no policy
        # at all". Recorded loudly so this is never mistaken for a real,
        # Jira-sourced calibration.
        policy_fallback_applied = True
        log_event(
            "POLICY_FALLBACK_NO_ACTIVE_POLICY",
            agent="Policy / Risk Appetite Calibration Agent",
            status="FALLBACK",
            release_type=normalized_release_type,
            policy_rows=len(policy_rows),
            available_release_types=available_release_types,
        )

    log_event(
        "POLICY_RULES_FILTERED",
        agent="Policy / Risk Appetite Calibration Agent",
        applicable_policies=len(
        applicable_policies
        ),
        release_type=normalized_release_type,
    )

    # ---------------------------------------------------------
    # 2. Build tier-level policy map
    # ---------------------------------------------------------
    tier_policies: dict[
        str,
        dict[str, Any],
    ] = {}

    general_policies: list[
        dict[str, Any]
    ] = []

    for row in applicable_policies:
        tier_value = _value(
            row,
            "Tier",
            "Application_Tier",
            "Application Tier",
        )

        if tier_value:
            normalized_tier = _normalize_tier(
                tier_value
            )

            tier_policies[
                normalized_tier
            ] = _normalize_policy_row(
                row,
                normalized_tier,
            )
        else:
            general_policies.append(row)

    # ---------------------------------------------------------
    # 3. Identify active regulatory test cases
    # ---------------------------------------------------------
    regulatory_tests: dict[
        str,
        dict[str, Any],
    ] = {}

    for row in regulatory_rows:
        if not _is_active(row):
            continue

        if not _row_applies_to_release_type(
            row,
            normalized_release_type,
        ):
            continue

        test_case_id = _value(
            row,
            "Test_Case_ID",
            "Test Case ID",
            "TestCase_ID",
            "Test_ID",
            "TC_ID",
        )

        if not test_case_id:
            continue

        normalized_test_case_id = str(
            test_case_id
        ).strip()

        regulatory_tests[
            normalized_test_case_id
        ] = {
            **row,
            "normalized_test_case_id": (
                normalized_test_case_id
            ),
            "policy_reason": _first_non_empty(
                _value(
                    row,
                    "Reason",
                    "Policy_Reason",
                    "Policy Reason",
                    "Description",
                ),
                "Active regulatory test",
            ),
        }
    log_event(
    "REGULATORY_TESTS_IDENTIFIED",
        agent="Policy / Risk Appetite Calibration Agent",
        regulatory_tests=len(
            regulatory_tests
        ),
    )    

    # ---------------------------------------------------------
    # 4. Identify applicable release rules
    # ---------------------------------------------------------
    release_rules = [
        row
        for row in release_rule_rows
        if _row_applies_to_release_type(
            row,
            normalized_release_type,
        )
        and _is_active(row)
    ]
    log_event(
        "RELEASE_RULES_APPLIED",
        agent="Policy / Risk Appetite Calibration Agent",
        release_rules=len(
            release_rules
        ),
    )

    mandatory_test_ids: set[str] = set(
        regulatory_tests.keys()
    )

    exclusion_prohibited_test_ids: set[
        str
    ] = set(
        regulatory_tests.keys()
    )

    always_execute_test_ids: set[str] = set(
        regulatory_tests.keys()
    )

    mandatory_reasons: dict[
        str,
        list[str],
    ] = {}

    exclusion_prohibition_reasons: dict[
        str,
        list[str],
    ] = {}

    for test_case_id, row in (
        regulatory_tests.items()
    ):
        reason = str(
            row.get("policy_reason")
            or "Regulatory test"
        )

        mandatory_reasons.setdefault(
            test_case_id,
            [],
        ).append(reason)

        exclusion_prohibition_reasons.setdefault(
            test_case_id,
            [],
        ).append(reason)

    # ---------------------------------------------------------
    # 5. Process release-rule decisions
    # ---------------------------------------------------------
    global_rule_flags: list[
        dict[str, Any]
    ] = []

    for rule in release_rules:
        rule_type = _normalized(
            _first_non_empty(
                _value(
                    rule,
                    "Rule_Type",
                    "Rule Type",
                    "Type",
                ),
                _value(
                    rule,
                    "Rule_Name",
                    "Rule Name",
                ),
            )
        )

        test_case_id = _value(
            rule,
            "Test_Case_ID",
            "Test Case ID",
            "TestCase_ID",
            "Test_ID",
            "TC_ID",
        )

        if "REGULATORY" in rule_type and "MUST" in rule_type:
            rule_type = "REGULATORY_MANDATORY"
        elif "DO_NOT_EXCLUDE" in rule_type or "EXCLUSION_PROHIBITED" in rule_type:
            rule_type = "EXCLUSION_PROHIBITED"

        rule_reason = str(
            _first_non_empty(
                _value(
                    rule,
                    "Reason",
                    "Rule_Reason",
                    "Rule Reason",
                    "Description",
                ),
                rule_type.replace(
                    "_",
                    " ",
                ).title(),
            )
        )

        if test_case_id:
            normalized_test_case_id = str(
                test_case_id
            ).strip()

            if (
                rule_type
                in MANDATORY_RULE_TYPES
            ):
                mandatory_test_ids.add(
                    normalized_test_case_id
                )

                mandatory_reasons.setdefault(
                    normalized_test_case_id,
                    [],
                ).append(rule_reason)

            if (
                rule_type
                in EXCLUSION_PROHIBITION_RULE_TYPES
            ):
                exclusion_prohibited_test_ids.add(
                    normalized_test_case_id
                )

                exclusion_prohibition_reasons.setdefault(
                    normalized_test_case_id,
                    [],
                ).append(rule_reason)

            if rule_type in {
                "ALWAYS_EXECUTE",
                "MANDATORY_TEST",
                "MUST_TEST",
                "REGULATORY_MANDATORY",
            }:
                always_execute_test_ids.add(
                    normalized_test_case_id
                )

        else:
            global_rule_flags.append(
                {
                    "rule_type": rule_type,
                    "reason": rule_reason,
                    "source": rule,
                }
            )

    log_event(
        "POLICY_DECISIONS_GENERATED",
        agent="Policy / Risk Appetite Calibration Agent",
        mandatory_tests=len(
            mandatory_test_ids
        ),
        exclusion_prohibited=len(
            exclusion_prohibited_test_ids
        ),
        always_execute=len(
            always_execute_test_ids
        ),
    )

    # ---------------------------------------------------------
    # 6. Resolve exclusion controls
    # ---------------------------------------------------------
    overall_max_exclusion = (
        _resolve_max_exclusion(
            policies=applicable_policies,
            rules=release_rules,
        )
    )

    minimum_must_test_rate = (
        _resolve_minimum_must_test_rate(
            policies=applicable_policies,
            rules=release_rules,
        )
    )

    require_approval_for_exclusion = (
        _resolve_boolean_rule(
            rows=[
                *applicable_policies,
                *release_rules,
            ],
            field_names=(
                "Require_Approval_For_Exclusion",
                "Approval_Required_For_Exclusion",
                "Exclusion_Approval_Required",
            ),
            default=True,
        )
    )

    high_risk_exclusion_prohibited = (
        _resolve_boolean_rule(
            rows=[
                *applicable_policies,
                *release_rules,
            ],
            field_names=(
                "High_Risk_Exclusion_Prohibited",
                "Prohibit_High_Risk_Exclusion",
                "No_High_Risk_Exclusion",
            ),
            default=True,
        )
    )

    # ---------------------------------------------------------
    # 7. Build test-level policy decisions
    # ---------------------------------------------------------
    all_policy_test_ids = sorted(
        mandatory_test_ids
        | exclusion_prohibited_test_ids
        | always_execute_test_ids
    )

    test_policy_decisions: dict[
        str,
        dict[str, Any],
    ] = {}

    for test_case_id in all_policy_test_ids:
        test_policy_decisions[
            test_case_id
        ] = {
            "test_case_id": test_case_id,
            "regulatory": (
                test_case_id
                in regulatory_tests
            ),
            "mandatory": (
                test_case_id
                in mandatory_test_ids
            ),
            "always_execute": (
                test_case_id
                in always_execute_test_ids
            ),
            "exclusion_prohibited": (
                test_case_id
                in exclusion_prohibited_test_ids
            ),
            "mandatory_reasons": (
                mandatory_reasons.get(
                    test_case_id,
                    [],
                )
            ),
            "exclusion_prohibition_reasons": (
                exclusion_prohibition_reasons.get(
                    test_case_id,
                    [],
                )
            ),
        }

    summary = {
        "release_type": (
            normalized_release_type
        ),
        "tier_policy_count": len(
            tier_policies
        ),
        "general_policy_count": len(
            general_policies
        ),
        "regulatory_test_count": len(
            regulatory_tests
        ),
        "release_rule_count": len(
            release_rules
        ),
        "mandatory_test_count": len(
            mandatory_test_ids
        ),
        "always_execute_test_count": len(
            always_execute_test_ids
        ),
        "exclusion_prohibited_test_count": len(
            exclusion_prohibited_test_ids
        ),
        "overall_max_exclusion": (
            overall_max_exclusion
        ),
        "overall_max_exclusion_percent": round(
            overall_max_exclusion * 100,
            2,
        ),
        "minimum_must_test_rate": (
            minimum_must_test_rate
        ),
        "minimum_must_test_percent": round(
            minimum_must_test_rate * 100,
            2,
        ),
        "require_approval_for_exclusion": (
            require_approval_for_exclusion
        ),
        "high_risk_exclusion_prohibited": (
            high_risk_exclusion_prohibited
        ),
    }
    log_event(
    "POLICY_SUMMARY_CREATED",
    agent="Policy / Risk Appetite Calibration Agent",
    release_type=normalized_release_type,
    overall_max_exclusion=overall_max_exclusion,
    minimum_must_test_rate=minimum_must_test_rate,
    )

    result: dict[str, Any] = {
        "release_type": normalized_release_type,
        "policy_fallback_applied": policy_fallback_applied,
        "approval_role": _first_non_empty(
            *[
                _value(
                    row,
                    "Over_Cap_Approval_Role",
                    "Over Cap Approval Role",
                )
                for row in applicable_policies
            ],
            "QA_LEAD",
        ),
        "tier_policies": tier_policies,
        "general_policies": general_policies,
        "regulatory_tests": regulatory_tests,
        "release_rules": release_rules,
        "mandatory_test_ids": sorted(
            mandatory_test_ids
        ),
        "always_execute_test_ids": sorted(
            always_execute_test_ids
        ),
        "exclusion_prohibited_test_ids": sorted(
            exclusion_prohibited_test_ids
        ),
        "mandatory_reasons": mandatory_reasons,
        "exclusion_prohibition_reasons": (
            exclusion_prohibition_reasons
        ),
        "test_policy_decisions": (
            test_policy_decisions
        ),
        "global_rule_flags": (
            global_rule_flags
        ),
        "overall_max_exclusion": (
            overall_max_exclusion
        ),
        "minimum_must_test_rate": (
            minimum_must_test_rate
        ),
        "require_approval_for_exclusion": (
            require_approval_for_exclusion
        ),
        "high_risk_exclusion_prohibited": (
            high_risk_exclusion_prohibited
        ),
        "summary": summary,

        # Compact structured payload for Scoring and Governance agents.
        "agent_output": {
            "release_type": normalized_release_type,
            "approval_role": _first_non_empty(
                *[
                    _value(
                        row,
                        "Over_Cap_Approval_Role",
                        "Over Cap Approval Role",
                    )
                    for row in applicable_policies
                ],
                "QA_LEAD",
            ),
            "tier_policies": tier_policies,
            "mandatory_test_ids": sorted(
                mandatory_test_ids
            ),
            "always_execute_test_ids": sorted(
                always_execute_test_ids
            ),
            "regulatory_test_ids": sorted(
                regulatory_tests.keys()
            ),
            "exclusion_prohibited_test_ids": sorted(
                exclusion_prohibited_test_ids
            ),
            "test_policy_decisions": (
                test_policy_decisions
            ),
            "overall_max_exclusion": (
                overall_max_exclusion
            ),
            "minimum_must_test_rate": (
                minimum_must_test_rate
            ),
            "require_approval_for_exclusion": (
                require_approval_for_exclusion
            ),
            "high_risk_exclusion_prohibited": (
                high_risk_exclusion_prohibited
            ),
        },
    }

    log_event(
       "POLICY_ANALYSIS_COMPLETED",
        agent="Policy / Risk Appetite Calibration Agent",
        stage="POLICY",
        status="SUCCESS",
        regulatory_tests=len(
            regulatory_tests
        ),
       release_rules=len(
            release_rules
        ),
    )

    audit_event(
    "POLICY_ANALYSIS_COMPLETED",
    agent="Policy / Risk Appetite Calibration Agent",
    message=(
        f"Processed {len(regulatory_tests)} regulatory tests "
        f"and {len(release_rules)} release rules."
    ),
    details={
        "release_type": normalized_release_type,
        "mandatory_tests": len(
            mandatory_test_ids
        ),
        "always_execute_tests": len(
            always_execute_test_ids
        ),
        "exclusion_prohibited_tests": len(
            exclusion_prohibited_test_ids
        ),
        "overall_max_exclusion":
            overall_max_exclusion,
    },
    )

    result["markdown"] = (
        format_policy_cards(result)
    )

    return result



def _validate_source_data(
    source_data: dict[
        str,
        list[dict[str, Any]],
    ],
) -> None:
    """
    Validate raw data blocks supplied by the Master Orchestrator.
    """

    if not isinstance(
        source_data,
        dict,
    ):
        raise TypeError(
            "source_data must be a dictionary "
            "provided by the Master Orchestrator."
        )

    missing_blocks = [
        block_name
        for block_name in REQUIRED_INPUT_KEYS
        if block_name not in source_data
    ]

    if missing_blocks:
        raise ValueError(
            "Policy Agent is missing required "
            "orchestrator data blocks: "
            f"{missing_blocks}"
        )

    invalid_blocks = [
        block_name
        for block_name in REQUIRED_INPUT_KEYS
        if not isinstance(
            source_data[
                block_name
            ],
            list,
        )
    ]

    if invalid_blocks:
        raise TypeError(
            "Policy Agent expected orchestrator "
            "data blocks as lists for: "
            f"{invalid_blocks}"
        )

def format_policy_cards(
    result: dict[str, Any],
) -> str:
    """
    Build a user-facing Markdown dashboard for ADK.
    """

    summary = result.get(
        "summary",
        {},
    )
    tier_policies = result.get(
        "tier_policies",
        {},
    )
    regulatory_tests = result.get(
        "regulatory_tests",
        {},
    )
    release_rules = result.get(
        "release_rules",
        [],
    )
    test_policy_decisions = result.get(
        "test_policy_decisions",
        {},
    )

    lines: list[str] = [
        "# Policy / Risk Appetite Calibration",
        "",
        "## Policy Summary",
        "",
        "> ### Release Profile",
        ">",
        "> **Release type:** "
        f"`{result.get('release_type', 'UNKNOWN')}`",
        ">",
        "> **Maximum exclusion:** "
        f"`{summary.get('overall_max_exclusion_percent', 0):.2f}%`",
        ">",
        "> **Minimum MUST_TEST rate:** "
        f"`{summary.get('minimum_must_test_percent', 0):.2f}%`",
        ">",
        "> **Exclusion approval required:** "
        f"`{'Yes' if summary.get('require_approval_for_exclusion') else 'No'}`",
        ">",
        "> **High-risk exclusion prohibited:** "
        f"`{'Yes' if summary.get('high_risk_exclusion_prohibited') else 'No'}`",
        "",
        "---",
        "",
        "## Counts",
        "",
        "| Metric | Count |",
        "|---|---:|",
        "| Tier policies | "
        f"{summary.get('tier_policy_count', 0)} |",
        "| Regulatory tests | "
        f"{summary.get('regulatory_test_count', 0)} |",
        "| Release rules | "
        f"{summary.get('release_rule_count', 0)} |",
        "| Mandatory tests | "
        f"{summary.get('mandatory_test_count', 0)} |",
        "| Always-execute tests | "
        f"{summary.get('always_execute_test_count', 0)} |",
        "| Exclusion-prohibited tests | "
        f"{summary.get('exclusion_prohibited_test_count', 0)} |",
        "",
        "---",
        "",
        "## Tier Policies",
        "",
    ]

    if tier_policies:
        for tier, policy in sorted(
            tier_policies.items()
        ):
            lines.extend(
                [
                    f"> ### `{tier}`",
                    ">",
                    "> **Minimum coverage:** "
                    f"`{policy.get('minimum_coverage_percent', 0):.2f}%`",
                    ">",
                    "> **Maximum exclusion:** "
                    f"`{policy.get('maximum_exclusion_percent', 0):.2f}%`",
                    ">",
                    "> **Mandatory execution:** "
                    f"`{'Yes' if policy.get('mandatory_execution') else 'No'}`",
                    ">",
                    "> **Approval required:** "
                    f"`{'Yes' if policy.get('approval_required') else 'No'}`",
                    ">",
                    "> **Policy status:** "
                    f"`{_display(_first_non_empty(policy.get('Policy_Status'), policy.get('Policy Status'), policy.get('Status'), 'ACTIVE'))}`",
                    "",
                ]
            )
    else:
        lines.extend(
            [
                "> No tier-specific policies were found.",
                "",
            ]
        )

    lines.extend(
        [
            "---",
            "",
            "## Regulatory Tests",
            "",
        ]
    )

    if regulatory_tests:
        for test_case_id, row in sorted(
            regulatory_tests.items()
        ):
            lines.extend(
                [
                    f"> ### `{test_case_id}`",
                    ">",
                    "> **Reason:** "
                    f"{_display(row.get('policy_reason'))}",
                    ">",
                    "> **Decision:** "
                    "`MANDATORY — DO NOT EXCLUDE`",
                    "",
                ]
            )
    else:
        lines.extend(
            [
                "> No active regulatory tests were found.",
                "",
            ]
        )

    lines.extend(
        [
            "---",
            "",
            "## Applicable Release Rules",
            "",
        ]
    )

    if release_rules:
        for rule in release_rules:
            rule_type = _normalized(
                _value(
                    rule,
                    "Rule_Type",
                    "Rule Type",
                    "Type",
                )
            )
            test_case_id = _display(
                _value(
                    rule,
                    "Test_Case_ID",
                    "Test Case ID",
                    "TestCase_ID",
                )
            )
            reason = _display(
                _first_non_empty(
                    _value(
                        rule,
                        "Reason",
                        "Rule_Reason",
                        "Description",
                    ),
                    "No description provided",
                )
            )

            lines.extend(
                [
                    f"> ### `{rule_type}`",
                    ">",
                    f"> **Test case:** `{test_case_id}`",
                    ">",
                    f"> **Reason:** {reason}",
                    "",
                ]
            )
    else:
        lines.extend(
            [
                "> No release rules were applicable.",
                "",
            ]
        )

    lines.extend(
        [
            "---",
            "",
            "## Test Policy Decisions",
            "",
            "| Test Case | Regulatory | Mandatory | Always Execute | Exclusion Prohibited |",
            "|---|---|---|---|---|",
        ]
    )

    for test_case_id, decision in sorted(
        test_policy_decisions.items()
    ):
        lines.append(
            f"| `{test_case_id}` "
            f"| {_yes_no(decision.get('regulatory'))} "
            f"| {_yes_no(decision.get('mandatory'))} "
            f"| {_yes_no(decision.get('always_execute'))} "
            f"| {_yes_no(decision.get('exclusion_prohibited'))} |"
        )

    return "\n".join(lines)


def _normalize_policy_row(
    row: dict[str, Any],
    tier: str,
) -> dict[str, Any]:
    minimum_coverage = _fraction(
        _first_non_empty(
            _value(
                row,
                "Minimum_Coverage",
                "Minimum Coverage",
                "Min_Coverage",
            ),
            _default_minimum_coverage(
                tier
            ),
        )
    )

    # Tier policies use Tier Max Exclusion only. The release-wide Overall Max
    # Exclusion is resolved separately and must not be replaced by a Tier-1
    # value of zero.
    maximum_exclusion = _fraction(
        _first_non_empty(
            _value(
                row,
                "Tier_Max_Exclusion",
                "Tier Max Exclusion",
            ),
            _default_maximum_exclusion(
                tier
            ),
        )
    )

    mandatory_execution = _boolean(
        _first_non_empty(
            _value(
                row,
                "Mandatory_Execution",
                "Mandatory Execution",
                "Always_Execute",
            ),
            tier == "TIER_1",
        )
    )

    approval_required = _boolean(
        _first_non_empty(
            _value(
                row,
                "Approval_Required",
                "Approval Required",
                "Exclusion_Approval_Required",
            ),
            tier in {
                "TIER_1",
                "TIER_2",
            },
        )
    )

    approval_role = _first_non_empty(
        _value(
            row,
            "Over_Cap_Approval_Role",
            "Over Cap Approval Role",
        ),
        "QA_LEAD",
    )

    return {
        **row,
        "tier": tier,
        "minimum_coverage": (
            minimum_coverage
        ),
        "minimum_coverage_percent": round(
            minimum_coverage * 100,
            2,
        ),
        "maximum_exclusion": (
            maximum_exclusion
        ),
        "maximum_exclusion_percent": round(
            maximum_exclusion * 100,
            2,
        ),
        "mandatory_execution": (
            mandatory_execution
        ),
        "approval_required": approval_required,
        "approval_role": approval_role,
        "Policy_Status": _first_non_empty(
            _value(row, "Policy_Status", "Policy Status", "PolicyStatus"),
            _value(row, "Status"),
            "ACTIVE",
        ),
        "Overall_Max_Exclusion": _first_non_empty(
            _value(
                row,
                "Overall_Max_Exclusion",
                "Overall Max Exclusion",
                "Maximum_Exclusion",
                "Maximum Exclusion",
            ),
        ),
    }


def _resolve_max_exclusion(
    policies: list[dict[str, Any]],
    rules: list[dict[str, Any]],
) -> float:
    """Resolve the release-wide exclusion cap.

    Important: ``Tier_Max_Exclusion`` is a tier-level control and must not
    override the release-wide ``Overall_Max_Exclusion`` value. The previous
    implementation also accepted generic ``Maximum_Exclusion`` fields, which
    could accidentally pull a Tier 1 value of 0.0 into the overall cap.
    """
    values: list[float] = []

    for row in [*policies, *rules]:
        value = _value(
            row,
            "Overall_Max_Exclusion",
            "Overall Max Exclusion",
            "Overall_Max_Exclusion_Rate",
            "Overall Max Exclusion Rate",
        )

        if value is None or value == "":
            continue

        values.append(_fraction(value))

    # The most restrictive explicit release-wide cap wins. For this project
    # the configured business default is 30% when Jira has no global cap row.
    # A Tier Max Exclusion of 0 must never become the global cap.
    if values:
        positive_or_zero = [v for v in values if v >= 0.0]
        return min(positive_or_zero) if positive_or_zero else 0.30
    return 0.30


def _resolve_minimum_must_test_rate(
    policies: list[dict[str, Any]],
    rules: list[dict[str, Any]],
) -> float:
    values: list[float] = []

    for row in [
        *policies,
        *rules,
    ]:
        value = _value(
            row,
            "Minimum_Must_Test_Rate",
            "Minimum Must Test Rate",
            "Min_Must_Test_Percentage",
            "Minimum_Mandatory_Coverage",
        )

        if value is None:
            continue

        values.append(
            _fraction(value)
        )

    return (
        max(values)
        if values
        else 0.0
    )


def _resolve_boolean_rule(
    rows: list[dict[str, Any]],
    field_names: tuple[str, ...],
    default: bool,
) -> bool:
    values: list[bool] = []

    for row in rows:
        value = _value(
            row,
            *field_names,
        )

        if value is None:
            continue

        values.append(
            _boolean(value)
        )

    if not values:
        return default

    # Any restrictive True setting wins.
    return any(values)


def _row_applies_to_release_type(
    row: dict[str, Any],
    release_type: str,
) -> bool:
    row_release_type = _normalized(
        _first_non_empty(
            _value(
                row,
                "Release_Type",
                "Release Type",
            ),
            "ALL",
        )
    )

    return row_release_type in {
        release_type,
        "ALL",
        "ANY",
        "",
    }


def _is_active(
    row: dict[str, Any],
) -> bool:
    """
    Business-active evaluation.

    Policy Status/Rule Status/Test Status are authoritative when present.
    Jira workflow Status such as "To Do" is never treated as an inactive
    business status by itself.
    """
    business_status = _value(
        row,
        "Policy_Status",
        "Policy Status",
        "PolicyStatus",
        "Rule_Status",
        "Rule Status",
        "Test_Status",
        "Test Status",
        "Regulatory_Status",
        "Regulatory Status",
        "Approval_Status",
        "Approval Status",
    )

    if business_status not in (None, ""):
        return _normalized(business_status) in {
            "ACTIVE",
            "APPROVED",
            "ENABLED",
            "CURRENT",
            "VALID",
            "YES",
        }

    # No business status on the row: absence of an inactive marker means the
    # policy/rule/test is usable. Do not use Jira workflow Status.
    return True

def _default_minimum_coverage(
    tier: str,
) -> float:
    return {
        "TIER_1": 1.00,
        "TIER_2": 0.80,
        "TIER_3": 0.50,
        "TIER_4": 0.20,
    }.get(
        tier,
        0.50,
    )


def _default_maximum_exclusion(
    tier: str,
) -> float:
    return {
        "TIER_1": 0.00,
        "TIER_2": 0.10,
        "TIER_3": 0.30,
        "TIER_4": 0.50,
    }.get(
        tier,
        0.10,
    )


def _normalize_tier(
    value: Any,
) -> str:
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


def _fraction(
    value: Any,
) -> float:
    numeric = _to_float(
        value,
        default=0.0,
    )

    if numeric > 1:
        numeric /= 100

    return min(
        max(
            numeric,
            0.0,
        ),
        1.0,
    )


def _boolean(
    value: Any,
) -> bool:
    if isinstance(
        value,
        bool,
    ):
        return value

    return _normalized(
        value
    ) in {
        "YES",
        "Y",
        "TRUE",
        "1",
        "ACTIVE",
        "ENABLED",
        "REQUIRED",
        "MANDATORY",
    }


def _value(
    row: dict[str, Any],
    *possible_names: str,
) -> Any:
    """
    Return a value using normalized field-name matching.
    """

    if not row:
        return None

    normalized_row = {
        _normalize_header(key): value
        for key, value
        in row.items()
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


def _first_non_empty(
    *values: Any,
) -> Any:
    for value in values:
        if (
            value is not None
            and value != ""
        ):
            return value

    return None


def _display(
    value: Any,
) -> str:
    if (
        value is None
        or value == ""
    ):
        return "Not available"

    return str(value)


def _yes_no(
    value: Any,
) -> str:
    return (
        "Yes"
        if bool(value)
        else "No"
    )


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
            receiver='Policy / Risk Appetite Calibration Agent',
            message_types={
                'POLICY_REQUEST',
                "AGENT_QUERY",
            },
        )

        release_id = request.release_id

        # A2A: All stage inputs arrive in request["data"], prepared by the orchestrator.
        if request.message_type == "AGENT_QUERY":

            return make_response(
                request,
                sender='Policy / Risk Appetite Calibration Agent',
                data=answer_agent_question(
                    question=str(
                        data.get("question") or ""
                    ),
                    context=data.get(
                        "agent_context",
                        data,
                    ),
                ),
            )

        result = calibrate_risk_policy(
            source_data=data.get(
                "source_data",
                {},
            ),
            release_type=str(
                data.get("release_type")
                or ""
            ).strip().upper(),
        )

        return make_response(
            request,
            sender='Policy / Risk Appetite Calibration Agent',
            data=result,
        )

    except Exception as exc:

        trace_error(
            "POLICY_AGENT_FAILED",
            agent="Policy / Risk Appetite Calibration Agent",
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
    "POLICY_AGENT_QUERY",
    agent="Policy / Risk Appetite Calibration Agent",
    stage="POLICY",
    status="SUCCESS",
    question=question,
    )

    return {
        "status": "success",
        "agent": 'Policy / Risk Appetite Calibration Agent',
        "question": question,
        "context": context,
        "markdown": _agent_question_markdown(question, context),
    }


def _agent_question_markdown(question: str, context: dict[str, Any]) -> str:
    import json
    output = context.get("agent_output", context)
    return "\n".join([
        f"# {'Policy / Risk Appetite Calibration Agent'}",
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
