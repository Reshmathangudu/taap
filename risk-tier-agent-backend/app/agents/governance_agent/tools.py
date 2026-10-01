
# #_old_governance_agent/tools.py
# from __future__ import annotations

# from typing import Any

# from app.observability.logger import (
#     log_event,
#     trace_error,
# )

# from app.observability.audit import audit_event

# from app.models import A2ARequest, A2AResponse
# from app.services.a2a import make_response, validate_message

# from app.utils.helpers import is_yes


# HARD_EXCLUSION_PROTECTIONS = {
#     "REGULATORY_ALWAYS_EXECUTE",
#     "POLICY_MANDATORY",
#     "POLICY_EXCLUSION_PROHIBITED",
#     "NEW_FEATURE_PROTECTION",
#     "DEFECT_CATCH_PROTECTION",
#     "TIER_1_FLOOR",
# }


# def evaluate_exclusion_governance(
#     scoring: dict[str, Any],
#     policy: dict[str, Any],
# ) -> dict[str, Any]:
#     log_event(
#     "GOVERNANCE_STARTED",
#     agent="Exclusion Risk & Governance Agent",
#     stage="GOVERNANCE",
#     status="STARTED",
#     )
#     """
#     Generate exclusion-risk and governance decisions.

#     This function is orchestrator-only. It consumes the structured scoring and
#     policy outputs prepared by the Master Orchestrator. It does not read
#     Jira, Excel, configuration, files, or external services.

#     The Master Orchestrator must provide:

#     - scoring: structured output from the Decision Engine / Scoring Agent
#     - policy: structured output from the Policy / Risk Appetite Agent

#     Only tests classified as EXCLUDE are governance exclusion candidates.
#     OPTIONAL tests are reported separately and do not require exclusion
#     approval unless another process explicitly changes them to EXCLUDE.
#     """

#     _validate_orchestrator_inputs(
#         scoring=scoring,
#         policy=policy,
#     )

#     scoring_payload = scoring.get(
#         "agent_output",
#         scoring,
#     )
#     policy_payload = policy.get(
#         "agent_output",
#         policy,
#     )

#     scoring_results = scoring_payload.get(
#         "results",
#         scoring.get(
#             "results",
#             [],
#         ),
#     )
#     scoring_summary = scoring_payload.get(
#         "summary",
#         scoring.get(
#             "summary",
#             {},
#         ),
#     )

#     exclusion_prohibited_test_ids = _string_set(
#         policy_payload.get(
#             "exclusion_prohibited_test_ids",
#             policy.get(
#                 "exclusion_prohibited_test_ids",
#                 [],
#             ),
#         )
#     )
#     mandatory_test_ids = _string_set(
#         policy_payload.get(
#             "mandatory_test_ids",
#             policy.get(
#                 "mandatory_test_ids",
#                 [],
#             ),
#         )
#     )
#     regulatory_test_ids = _string_set(
#         policy_payload.get(
#             "regulatory_test_ids",
#             list(
#                 policy.get(
#                     "regulatory_tests",
#                     {},
#                 ).keys()
#             ),
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

#     maximum_allowed = _fraction(
#         policy_payload.get(
#             "overall_max_exclusion",
#             policy.get(
#                 "overall_max_exclusion",
#                 0.10,
#             ),
#         )
#     )

#     require_approval_for_exclusion = is_yes(
#         policy_payload.get(
#             "require_approval_for_exclusion",
#             policy.get(
#                 "require_approval_for_exclusion",
#                 True,
#             ),
#         )
#     )

#     configured_approval_role = str(
#         policy_payload.get(
#             "approval_role",
#             policy.get(
#                 "approval_role",
#                 "QA_LEAD",
#             ),
#         )
#         or "QA_LEAD"
#     ).strip().upper()

#     high_risk_exclusion_prohibited = is_yes(
#         policy_payload.get(
#             "high_risk_exclusion_prohibited",
#             policy.get(
#                 "high_risk_exclusion_prohibited",
#                 True,
#             ),
#         )
#     )
#     log_event(
#     "GOVERNANCE_INPUTS_LOADED",
#     agent="Exclusion Risk & Governance Agent",
#     stage="GOVERNANCE",
#     scoring_results=len(scoring_results),
#     )


#     optional_tests = [
#         row
#         for row in scoring_results
#         if _normalized(
#             row.get(
#                 "classification"
#             )
#         )
#         == "OPTIONAL"
#     ]

#     exclusion_candidates = [
#         row
#         for row in scoring_results
#         if _normalized(
#             row.get(
#                 "classification"
#             )
#         )
#         == "EXCLUDE"
#     ]
#     log_event(
#     "EXCLUSION_CANDIDATES_IDENTIFIED",
#     agent="Exclusion Risk & Governance Agent",
#     candidates=len(
#         exclusion_candidates
#     ),
#     optional_tests=len(
#         optional_tests
#     ),
#     )

#     records: list[dict[str, Any]] = []

#     for index, result in enumerate(
#         exclusion_candidates,
#         start=1,
#     ):
#         test_case_id = str(
#             result.get("test_case_id")
#             or ""
#         ).strip()

#         classification = _normalized(
#             result.get(
#                 "classification"
#             )
#             or "EXCLUDE"
#         )

#         score = _to_float(
#             result.get("composite_score"),
#             default=0.0,
#         )

#         tier = _normalize_tier(
#             result.get("tier")
#             or "TIER_3"
#         )

#         protection_flags = {
#             str(flag).strip()
#             for flag in result.get(
#                 "protection_flags",
#                 [],
#             )
#             if flag is not None
#             and str(flag).strip()
#         }

#         policy_decision = (
#             test_policy_decisions.get(
#                 test_case_id,
#                 {},
#             )
#         )

#         if test_case_id in regulatory_test_ids:
#             protection_flags.add(
#                 "REGULATORY_ALWAYS_EXECUTE"
#             )

#         if (
#             test_case_id in mandatory_test_ids
#             or is_yes(
#                 policy_decision.get(
#                     "mandatory"
#                 )
#             )
#             or is_yes(
#                 policy_decision.get(
#                     "always_execute"
#                 )
#             )
#         ):
#             protection_flags.add(
#                 "POLICY_MANDATORY"
#             )

#         if (
#             test_case_id
#             in exclusion_prohibited_test_ids
#             or is_yes(
#                 policy_decision.get(
#                     "exclusion_prohibited"
#                 )
#             )
#         ):
#             protection_flags.add(
#                 "POLICY_EXCLUSION_PROHIBITED"
#             )

#         protected_from_exclusion = bool(
#             HARD_EXCLUSION_PROTECTIONS.intersection(
#                 protection_flags
#             )
#         )

#         likelihood = _likelihood_from_score(
#             score
#         )
#         business_impact = (
#             _business_impact_from_tier(
#                 tier
#             )
#         )
#         residual_risk = (
#             _calculate_residual_risk(
#                 likelihood=likelihood,
#                 business_impact=(
#                     business_impact
#                 ),
#                 protected_from_exclusion=(
#                     protected_from_exclusion
#                 ),
#             )
#         )

#         governance_decision = (
#             _governance_decision(
#                 classification=classification,
#                 protected_from_exclusion=(
#                     protected_from_exclusion
#                 ),
#                 residual_risk=residual_risk,
#                 high_risk_exclusion_prohibited=(
#                     high_risk_exclusion_prohibited
#                 ),
#             )
#         )

#         approval_role = _approval_role(
#             residual_risk=residual_risk,
#             classification=classification,
#             governance_decision=governance_decision,
#             require_approval=require_approval_for_exclusion,
#             configured_role=configured_approval_role,
#         )

#         approval_required = (
#             approval_role != "NONE"
#         )

#         approval_status = (
#             "PENDING"
#             if approval_required
#             else "NOT_REQUIRED"
#         )

#         exclusion_reasons = (
#             _build_exclusion_reasons(
#                 result=result,
#                 protected_from_exclusion=(
#                     protected_from_exclusion
#                 ),
#                 protection_flags=(
#                     protection_flags
#                 ),
#                 governance_decision=(
#                     governance_decision
#                 ),
#             )
#         )

#         records.append(
#             {
#                 "exclusion_id": (
#                     f"RUN-EXC-{index:03d}"
#                 ),
#                 "test_case_id": test_case_id,
#                 "test_name": result.get(
#                     "test_name"
#                 ),
#                 "module_id": result.get(
#                     "module_id"
#                 ),
#                 "tier": tier,
#                 "composite_score": round(
#                     score,
#                     2,
#                 ),
#                 "risk_band": result.get(
#                     "risk_band"
#                 ),
#                 "proposed_classification": (
#                     classification
#                 ),
#                 "governance_decision": (
#                     governance_decision
#                 ),
#                 "exclusion_reason": "; ".join(
#                     exclusion_reasons
#                 ),
#                 "exclusion_reasons": (
#                     exclusion_reasons
#                 ),
#                 "protection_flags": sorted(
#                     protection_flags
#                 ),
#                 "protected_from_exclusion": (
#                     protected_from_exclusion
#                 ),
#                 "likelihood": likelihood,
#                 "business_impact": (
#                     business_impact
#                 ),
#                 "residual_risk": (
#                     residual_risk
#                 ),
#                 "approval_required": (
#                     approval_required
#                 ),
#                 "approval_role": (
#                     approval_role
#                 ),
#                 "approval_status": (
#                     approval_status
#                 ),
#             }
#         )

#     log_event(
#         "GOVERNANCE_DECISIONS_CREATED",
#         agent="Exclusion Risk & Governance Agent",
#         reviewed_candidates=len(
#             records
#         ),
#     )    

#     total_tests = int(
#         scoring_summary.get(
#             "total_tests",
#             0,
#         )
#         or 0
#     )

#     approved_exclusions_before_cap = sum(
#         1
#         for row in records
#         if row["governance_decision"]
#         == "APPROVE_EXCLUSION"
#     )

#     exclusion_rate = (
#         approved_exclusions_before_cap
#         / total_tests
#         if total_tests
#         else 0.0
#     )

#     over_cap = (
#         exclusion_rate
#         > maximum_allowed
#     )

#     if over_cap:
#         for row in records:
#             if (
#                 row["governance_decision"]
#                 == "APPROVE_EXCLUSION"
#             ):
#                 row[
#                     "governance_decision"
#                 ] = "PENDING_CAP_REVIEW"
#                 row[
#                     "approval_required"
#                 ] = True
#                 row[
#                     "approval_role"
#                 ] = (
#                     "QA_LEAD_AND_BUSINESS_OWNER"
#                 )
#                 row[
#                     "approval_status"
#                 ] = "PENDING"
#                 row[
#                     "exclusion_reasons"
#                 ].append(
#                     "Overall exclusion cap exceeded"
#                 )
#                 row[
#                     "exclusion_reason"
#                 ] = "; ".join(
#                     row[
#                         "exclusion_reasons"
#                     ]
#                 )

#     log_event(
#     "EXCLUSION_CAP_CHECK_COMPLETED",
#     agent="Exclusion Risk & Governance Agent",
#     over_cap=over_cap,
#     exclusion_rate=round(
#         exclusion_rate * 100,
#         2,
#     ),
#     maximum_allowed=round(
#         maximum_allowed * 100,
#         2,
#     ),
#     )            

#     approved_exclusions = sum(
#         1
#         for row in records
#         if row[
#             "governance_decision"
#         ]
#         == "APPROVE_EXCLUSION"
#     )

#     pending_cap_review = sum(
#         1
#         for row in records
#         if row[
#             "governance_decision"
#         ]
#         == "PENDING_CAP_REVIEW"
#     )

#     pending_approval_records = [
#         row
#         for row in records
#         if row[
#             "approval_status"
#         ]
#         == "PENDING"
#     ]

#     rejected_exclusions = sum(
#         1
#         for row in records
#         if row[
#             "governance_decision"
#         ]
#         == "REJECT_EXCLUSION"
#     )

#     pending_risk_approval = sum(
#         1
#         for row in records
#         if row[
#             "governance_decision"
#         ]
#         == "PENDING_APPROVAL"
#     )

#     summary = {
#         "optional_tests": len(
#             optional_tests
#         ),
#         "exclusion_candidates": len(
#             exclusion_candidates
#         ),
#         "approved_exclusions": (
#             approved_exclusions
#         ),
#         "approved_exclusions_before_cap": (
#             approved_exclusions_before_cap
#         ),
#         "exclusion_rate": round(
#             exclusion_rate,
#             4,
#         ),
#         "exclusion_rate_percent": round(
#             exclusion_rate * 100,
#             2,
#         ),
#         "maximum_allowed_exclusion_rate": (
#             maximum_allowed
#         ),
#         "maximum_allowed_exclusion_percent": round(
#             maximum_allowed * 100,
#             2,
#         ),
#         "approval_role": configured_approval_role,
#         "over_cap": over_cap,
#         "pending_cap_review": (
#             pending_cap_review
#         ),
#         "pending_approvals": len(
#             pending_approval_records
#         ),
#         "pending_risk_approval": (
#             pending_risk_approval
#         ),
#         "rejected_exclusions": (
#             rejected_exclusions
#         ),
#         "protected_candidates": sum(
#             1
#             for row in records
#             if row[
#                 "protected_from_exclusion"
#             ]
#         ),
#     }
#     log_event(
#     "GOVERNANCE_SUMMARY_CREATED",
#     agent="Exclusion Risk & Governance Agent",
#     approved_exclusions=approved_exclusions,
#     rejected_exclusions=rejected_exclusions,
#     pending_approvals=len(
#         pending_approval_records
#     ),
#     )

#     result: dict[str, Any] = {
#         "records": records,
#         "optional_tests": optional_tests,
#         "summary": summary,
#         "agent_output": {
#             "summary": summary,
#             "optional_test_ids": [
#                 str(
#                     row.get(
#                         "test_case_id"
#                     )
#                     or ""
#                 ).strip()
#                 for row in optional_tests
#                 if row.get(
#                     "test_case_id"
#                 )
#             ],
#             "approved_exclusion_test_ids": [
#                 row["test_case_id"]
#                 for row in records
#                 if row[
#                     "governance_decision"
#                 ]
#                 == "APPROVE_EXCLUSION"
#             ],
#             "pending_approval_test_ids": [
#                 row["test_case_id"]
#                 for row in pending_approval_records
#             ],
#             "rejected_exclusion_test_ids": [
#                 row["test_case_id"]
#                 for row in records
#                 if row[
#                     "governance_decision"
#                 ]
#                 == "REJECT_EXCLUSION"
#             ],
#             "over_cap": over_cap,
#         },
#     }
#     log_event(
#     "GOVERNANCE_COMPLETED",
#     agent="Exclusion Risk & Governance Agent",
#     stage="GOVERNANCE",
#     status="SUCCESS",
#     exclusion_candidates=len(
#         exclusion_candidates
#     ),
#     )

#     audit_event(
#     "GOVERNANCE_COMPLETED",
#     agent="Exclusion Risk & Governance Agent",
#     message=(
#         f"Reviewed {len(exclusion_candidates)} "
#         f"exclusion candidates."
#     ),
#     details={
#         "approved_exclusions":
#             approved_exclusions,
#         "rejected_exclusions":
#             rejected_exclusions,
#         "pending_approvals":
#             len(
#                 pending_approval_records
#             ),
#         "over_cap":
#             over_cap,
#     },
#     )

#     result["markdown"] = (
#         format_governance_dashboard(
#             result
#         )
#     )

#     return result


# def _validate_orchestrator_inputs(
#     scoring: dict[str, Any],
#     policy: dict[str, Any],
# ) -> None:
#     """
#     Validate structured scoring and policy inputs supplied by the Master Orchestrator.
#     """

#     if not isinstance(
#         scoring,
#         dict,
#     ):
#         raise TypeError(
#             "scoring must be a dictionary supplied by "
#             "the Master Orchestrator."
#         )

#     if not isinstance(
#         policy,
#         dict,
#     ):
#         raise TypeError(
#             "policy must be a dictionary supplied by "
#             "the Master Orchestrator."
#         )

#     scoring_payload = scoring.get(
#         "agent_output",
#         scoring,
#     )

#     policy_payload = policy.get(
#         "agent_output",
#         policy,
#     )

#     if not isinstance(
#         scoring_payload,
#         dict,
#     ):
#         raise TypeError(
#             "The Scoring Agent output must be a dictionary."
#         )

#     if not isinstance(
#         policy_payload,
#         dict,
#     ):
#         raise TypeError(
#             "The Policy Agent output must be a dictionary."
#         )

#     results = scoring_payload.get(
#         "results",
#         scoring.get(
#             "results",
#         ),
#     )

#     if results is None:
#         raise ValueError(
#             "The Scoring Agent output does not contain "
#             "a results collection."
#         )

#     if not isinstance(
#         results,
#         list,
#     ):
#         raise TypeError(
#             "The Scoring Agent results must be a list."
#         )


# def format_governance_dashboard(
#     result: dict[str, Any],
# ) -> str:
#     """Build a user-facing Markdown dashboard for ADK."""

#     records = result.get(
#         "records",
#         [],
#     )
#     summary = result.get(
#         "summary",
#         {},
#     )

#     lines: list[str] = [
#         "# Exclusion Risk & Governance",
#         "",
#         "## Governance Summary",
#         "",
#         "| Metric | Value |",
#         "|---|---:|",
#         "| Optional tests | "
#         f"{summary.get('optional_tests', 0)} |",
#         "| Exclusion candidates | "
#         f"{summary.get('exclusion_candidates', 0)} |",
#         "| Approved exclusions | "
#         f"{summary.get('approved_exclusions', 0)} |",
#         "| Rejected exclusions | "
#         f"{summary.get('rejected_exclusions', 0)} |",
#         "| Pending approvals | "
#         f"{summary.get('pending_approvals', 0)} |",
#         "| Pending cap review | "
#         f"{summary.get('pending_cap_review', 0)} |",
#         "| Exclusion rate | "
#         f"{summary.get('exclusion_rate_percent', 0):.2f}% |",
#         "| Maximum allowed | "
#         f"{summary.get('maximum_allowed_exclusion_percent', 0):.2f}% |",
#         "| Exclusion cap exceeded | "
#         f"{'Yes' if summary.get('over_cap') else 'No'} |",
#         "",
#         "---",
#         "",
#         "## Exclusion Candidate Decisions",
#         "",
#     ]

#     if not records:
#         lines.extend(
#             [
#                 "> No EXCLUDE candidates require governance review.",
#                 "",
#             ]
#         )
#         return "\n".join(lines)

#     for row in records:
#         flags = row.get(
#             "protection_flags",
#             [],
#         )
#         flags_text = (
#             ", ".join(flags)
#             if flags
#             else "None"
#         )

#         reasons = row.get(
#             "exclusion_reasons",
#             [],
#         )
#         reasons_text = (
#             "; ".join(reasons)
#             if reasons
#             else "No reason available"
#         )

#         lines.extend(
#             [
#                 f"> ### `{row.get('test_case_id')}` — "
#                 f"{_display(row.get('test_name'))}",
#                 ">",
#                 f"> **Module:** `{_display(row.get('module_id'))}`",
#                 ">",
#                 f"> **Tier:** `{row.get('tier', 'TIER_3')}`",
#                 ">",
#                 f"> **Score:** `{row.get('composite_score', 0):.2f}`",
#                 ">",
#                 f"> **Proposed:** `{row.get('proposed_classification')}`",
#                 ">",
#                 f"> **Decision:** `{row.get('governance_decision')}`",
#                 ">",
#                 f"> **Likelihood:** `{row.get('likelihood')}`",
#                 ">",
#                 f"> **Business impact:** `{row.get('business_impact')}`",
#                 ">",
#                 f"> **Residual risk:** `{row.get('residual_risk')}`",
#                 ">",
#                 f"> **Protected:** "
#                 f"{'Yes' if row.get('protected_from_exclusion') else 'No'}",
#                 ">",
#                 f"> **Protection flags:** {flags_text}",
#                 ">",
#                 f"> **Approval:** "
#                 f"`{row.get('approval_status')}` "
#                 f"({row.get('approval_role')})",
#                 ">",
#                 f"> **Reason:** {reasons_text}",
#                 "",
#             ]
#         )

#     return "\n".join(lines)


# def _governance_decision(
#     classification: str,
#     protected_from_exclusion: bool,
#     residual_risk: str,
#     high_risk_exclusion_prohibited: bool,
# ) -> str:
#     if classification != "EXCLUDE":
#         return "RETAIN_TEST"

#     if protected_from_exclusion:
#         return "REJECT_EXCLUSION"

#     if (
#         residual_risk == "HIGH"
#         and high_risk_exclusion_prohibited
#     ):
#         return "REJECT_EXCLUSION"

#     if residual_risk == "LOW":
#         return "APPROVE_EXCLUSION"

#     return "PENDING_APPROVAL"


# def _build_exclusion_reasons(
#     result: dict[str, Any],
#     protected_from_exclusion: bool,
#     protection_flags: set[str],
#     governance_decision: str,
# ) -> list[str]:
#     reasons: list[str] = []

#     for reason in result.get(
#         "reasons",
#         [],
#     )[:3]:
#         if reason:
#             reasons.append(
#                 str(reason)
#             )

#     if protected_from_exclusion:
#         reasons.append(
#             "Exclusion prohibited by protection rule"
#         )

#     for flag in sorted(
#         protection_flags
#     ):
#         reasons.append(flag)

#     if governance_decision == "APPROVE_EXCLUSION":
#         reasons.append(
#             "Low residual risk supports exclusion"
#         )
#     elif governance_decision == "PENDING_APPROVAL":
#         reasons.append(
#             "Residual risk requires governance approval"
#         )
#     elif governance_decision == "REJECT_EXCLUSION":
#         reasons.append(
#             "Governance rejected the proposed exclusion"
#         )

#     return list(
#         dict.fromkeys(reasons)
#     )


# def _likelihood_from_score(
#     score: float,
# ) -> str:
#     if score >= 60:
#         return "HIGH"

#     if score >= 40:
#         return "MEDIUM"

#     return "LOW"


# def _business_impact_from_tier(
#     tier: str,
# ) -> str:
#     return {
#         "TIER_1": "HIGH",
#         "TIER_2": "MEDIUM",
#         "TIER_3": "MEDIUM",
#         "TIER_4": "LOW",
#     }.get(
#         tier,
#         "MEDIUM",
#     )


# def _calculate_residual_risk(
#     likelihood: str,
#     business_impact: str,
#     protected_from_exclusion: bool,
# ) -> str:
#     if protected_from_exclusion:
#         return "HIGH"

#     risk_matrix = {
#         ("HIGH", "HIGH"): "HIGH",
#         ("HIGH", "MEDIUM"): "HIGH",
#         ("HIGH", "LOW"): "MEDIUM",
#         ("MEDIUM", "HIGH"): "HIGH",
#         ("MEDIUM", "MEDIUM"): "MEDIUM",
#         ("MEDIUM", "LOW"): "LOW",
#         ("LOW", "HIGH"): "MEDIUM",
#         ("LOW", "MEDIUM"): "LOW",
#         ("LOW", "LOW"): "LOW",
#     }

#     return risk_matrix.get(
#         (
#             likelihood,
#             business_impact,
#         ),
#         "MEDIUM",
#     )


# def _approval_role(
#     residual_risk: str,
#     classification: str,
#     governance_decision: str,
#     require_approval: bool,
#     configured_role: str = "QA_LEAD",
# ) -> str:
#     if classification != "EXCLUDE":
#         return "NONE"

#     if governance_decision == "REJECT_EXCLUSION":
#         return "NONE"

#     # BR-GOV-02: Medium requires QA Lead; High requires QA Lead plus Business Owner.
#     # Low-risk exclusions do not require per-test approval unless an over-cap
#     # release control separately blocks finalization.
#     if residual_risk == "LOW":
#         return "NONE"

#     if not require_approval:
#         return "NONE"

#     base_role = configured_role or "QA_LEAD"

#     if residual_risk == "HIGH":
#         if "BUSINESS_OWNER" in base_role:
#             return base_role
#         return f"{base_role}_AND_BUSINESS_OWNER"

#     return base_role


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
#             receiver='Exclusion Risk & Governance Agent',
#             message_types={
#                 'GOVERNANCE_REQUEST',
#                 "AGENT_QUERY",
#             },
#         )

#         release_id = request.release_id

#         if request.message_type == "AGENT_QUERY":

#             return make_response(
#                 request,
#                 sender='Exclusion Risk & Governance Agent',
#                 data=answer_agent_question(
#                     question=str(
#                         data.get("question")
#                         or ""
#                     ),
#                     context=data.get(
#                         "agent_context",
#                         data,
#                     ),
#                 ),
#             )

#         result = evaluate_exclusion_governance(
#             scoring=data.get(
#                 "scoring",
#                 {},
#             ),
#             policy=data.get(
#                 "policy",
#                 {},
#             ),
#         )

#         return make_response(
#             request,
#             sender='Exclusion Risk & Governance Agent',
#             data=result,
#         )

#     except Exception as exc:

#         trace_error(
#             "GOVERNANCE_AGENT_FAILED",
#             agent="Exclusion Risk & Governance Agent",
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
#     "GOVERNANCE_AGENT_QUERY",
#     agent="Exclusion Risk & Governance Agent",
#     stage="GOVERNANCE",
#     status="SUCCESS",
#     question=question,
#     )
#     return {
#         "status": "success",
#         "agent": 'Exclusion Risk & Governance Agent',
#         "question": question,
#         "context": context,
#         "markdown": _agent_question_markdown(question, context),
#     }


# def _agent_question_markdown(question: str, context: dict[str, Any]) -> str:
#     import json
#     output = context.get("agent_output", context)
#     return "\n".join([
#         f"# {'Exclusion Risk & Governance Agent'}",
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

#_old_governance_agent/tools.py
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


HARD_EXCLUSION_PROTECTIONS = {
    "REGULATORY_ALWAYS_EXECUTE",
    "POLICY_MANDATORY",
    "POLICY_EXCLUSION_PROHIBITED",
    "NEW_FEATURE_PROTECTION",
    "DEFECT_CATCH_PROTECTION",
    "TIER_1_FLOOR",
}


def evaluate_exclusion_governance(
    scoring: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    """
    Generate exclusion-risk and governance decisions.

    This function is orchestrator-only. It consumes the structured scoring and
    policy outputs prepared by the Master Orchestrator. It does not read
    Jira, Excel, configuration, files, or external services.

    The Master Orchestrator must provide:

    - scoring: structured output from the Decision Engine / Scoring Agent
    - policy: structured output from the Policy / Risk Appetite Agent

    Only tests classified as EXCLUDE are governance exclusion candidates.
    OPTIONAL tests are reported separately and do not require exclusion
    approval unless another process explicitly changes them to EXCLUDE.
    """
    log_event(
    "GOVERNANCE_STARTED",
    agent="Exclusion Risk & Governance Agent",
    stage="GOVERNANCE",
    status="STARTED",
    )

    _validate_orchestrator_inputs(
        scoring=scoring,
        policy=policy,
    )

    scoring_payload = scoring.get(
        "agent_output",
        scoring,
    )
    policy_payload = policy.get(
        "agent_output",
        policy,
    )

    scoring_results = scoring_payload.get(
        "results",
        scoring.get(
            "results",
            [],
        ),
    )
    scoring_summary = scoring_payload.get(
        "summary",
        scoring.get(
            "summary",
            {},
        ),
    )

    exclusion_prohibited_test_ids = _string_set(
        policy_payload.get(
            "exclusion_prohibited_test_ids",
            policy.get(
                "exclusion_prohibited_test_ids",
                [],
            ),
        )
    )
    mandatory_test_ids = _string_set(
        policy_payload.get(
            "mandatory_test_ids",
            policy.get(
                "mandatory_test_ids",
                [],
            ),
        )
    )
    regulatory_test_ids = _string_set(
        policy_payload.get(
            "regulatory_test_ids",
            list(
                policy.get(
                    "regulatory_tests",
                    {},
                ).keys()
            ),
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

    maximum_allowed = _fraction(
        policy_payload.get(
            "overall_max_exclusion",
            policy.get(
                "overall_max_exclusion",
                0.10,
            ),
        )
    )

    require_approval_for_exclusion = is_yes(
        policy_payload.get(
            "require_approval_for_exclusion",
            policy.get(
                "require_approval_for_exclusion",
                True,
            ),
        )
    )

    configured_approval_role = str(
        policy_payload.get(
            "approval_role",
            policy.get(
                "approval_role",
                "QA_LEAD",
            ),
        )
        or "QA_LEAD"
    ).strip().upper()

    high_risk_exclusion_prohibited = is_yes(
        policy_payload.get(
            "high_risk_exclusion_prohibited",
            policy.get(
                "high_risk_exclusion_prohibited",
                True,
            ),
        )
    )
    log_event(
    "GOVERNANCE_INPUTS_LOADED",
    agent="Exclusion Risk & Governance Agent",
    stage="GOVERNANCE",
    scoring_results=len(scoring_results),
    )


    optional_tests = [
        row
        for row in scoring_results
        if _normalized(
            row.get(
                "classification"
            )
        )
        == "OPTIONAL"
    ]

    exclusion_candidates = [
        row
        for row in scoring_results
        if _normalized(
            row.get(
                "classification"
            )
        )
        == "EXCLUDE"
    ]
    log_event(
    "EXCLUSION_CANDIDATES_IDENTIFIED",
    agent="Exclusion Risk & Governance Agent",
    candidates=len(
        exclusion_candidates
    ),
    optional_tests=len(
        optional_tests
    ),
    )

    records: list[dict[str, Any]] = []

    for index, result in enumerate(
        exclusion_candidates,
        start=1,
    ):
        test_case_id = str(
            result.get("test_case_id")
            or ""
        ).strip()

        classification = _normalized(
            result.get(
                "classification"
            )
            or "EXCLUDE"
        )

        score = _to_float(
            result.get("composite_score"),
            default=0.0,
        )

        tier = _normalize_tier(
            result.get("tier")
            or "TIER_3"
        )

        protection_flags = {
            str(flag).strip()
            for flag in result.get(
                "protection_flags",
                [],
            )
            if flag is not None
            and str(flag).strip()
        }

        policy_decision = (
            test_policy_decisions.get(
                test_case_id,
                {},
            )
        )

        if test_case_id in regulatory_test_ids:
            protection_flags.add(
                "REGULATORY_ALWAYS_EXECUTE"
            )

        if (
            test_case_id in mandatory_test_ids
            or is_yes(
                policy_decision.get(
                    "mandatory"
                )
            )
            or is_yes(
                policy_decision.get(
                    "always_execute"
                )
            )
        ):
            protection_flags.add(
                "POLICY_MANDATORY"
            )

        if (
            test_case_id
            in exclusion_prohibited_test_ids
            or is_yes(
                policy_decision.get(
                    "exclusion_prohibited"
                )
            )
        ):
            protection_flags.add(
                "POLICY_EXCLUSION_PROHIBITED"
            )

        protected_from_exclusion = bool(
            HARD_EXCLUSION_PROTECTIONS.intersection(
                protection_flags
            )
        )

        likelihood = _likelihood_from_score(
            score
        )
        business_impact = (
            _business_impact_from_tier(
                tier
            )
        )
        residual_risk = (
            _calculate_residual_risk(
                likelihood=likelihood,
                business_impact=(
                    business_impact
                ),
                protected_from_exclusion=(
                    protected_from_exclusion
                ),
            )
        )

        governance_decision = (
            _governance_decision(
                classification=classification,
                protected_from_exclusion=(
                    protected_from_exclusion
                ),
                residual_risk=residual_risk,
                high_risk_exclusion_prohibited=(
                    high_risk_exclusion_prohibited
                ),
            )
        )

        approval_role = _approval_role(
            residual_risk=residual_risk,
            classification=classification,
            governance_decision=governance_decision,
            require_approval=require_approval_for_exclusion,
            configured_role=configured_approval_role,
        )

        approval_required = (
            approval_role != "NONE"
        )

        approval_status = (
            "PENDING"
            if approval_required
            else "NOT_REQUIRED"
        )

        exclusion_reasons = (
            _build_exclusion_reasons(
                result=result,
                protected_from_exclusion=(
                    protected_from_exclusion
                ),
                protection_flags=(
                    protection_flags
                ),
                governance_decision=(
                    governance_decision
                ),
            )
        )

        records.append(
            {
                "exclusion_id": (
                    f"RUN-EXC-{index:03d}"
                ),
                "test_case_id": test_case_id,
                "test_name": result.get(
                    "test_name"
                ),
                "module_id": result.get(
                    "module_id"
                ),
                "tier": tier,
                "composite_score": round(
                    score,
                    2,
                ),
                "risk_band": result.get(
                    "risk_band"
                ),
                "proposed_classification": (
                    classification
                ),
                "governance_decision": (
                    governance_decision
                ),
                "exclusion_reason": "; ".join(
                    exclusion_reasons
                ),
                "exclusion_reasons": (
                    exclusion_reasons
                ),
                "protection_flags": sorted(
                    protection_flags
                ),
                "protected_from_exclusion": (
                    protected_from_exclusion
                ),
                "likelihood": likelihood,
                "business_impact": (
                    business_impact
                ),
                "residual_risk": (
                    residual_risk
                ),
                "approval_required": (
                    approval_required
                ),
                "approval_role": (
                    approval_role
                ),
                "approval_status": (
                    approval_status
                ),
            }
        )

    log_event(
        "GOVERNANCE_DECISIONS_CREATED",
        agent="Exclusion Risk & Governance Agent",
        reviewed_candidates=len(
            records
        ),
    )    

    total_tests = int(
        scoring_summary.get(
            "total_tests",
            0,
        )
        or 0
    )

    approved_exclusions_before_cap = sum(
        1
        for row in records
        if row["governance_decision"]
        == "APPROVE_EXCLUSION"
    )

    exclusion_rate = (
        approved_exclusions_before_cap
        / total_tests
        if total_tests
        else 0.0
    )

    over_cap = (
        exclusion_rate
        > maximum_allowed
    )

    if over_cap:
        for row in records:
            if (
                row["governance_decision"]
                == "APPROVE_EXCLUSION"
            ):
                row[
                    "governance_decision"
                ] = "PENDING_CAP_REVIEW"
                row[
                    "approval_required"
                ] = True
                row[
                    "approval_role"
                ] = (
                    "QA_LEAD_AND_BUSINESS_OWNER"
                )
                row[
                    "approval_status"
                ] = "PENDING"
                row[
                    "exclusion_reasons"
                ].append(
                    "Overall exclusion cap exceeded"
                )
                row[
                    "exclusion_reason"
                ] = "; ".join(
                    row[
                        "exclusion_reasons"
                    ]
                )

    log_event(
    "EXCLUSION_CAP_CHECK_COMPLETED",
    agent="Exclusion Risk & Governance Agent",
    over_cap=over_cap,
    exclusion_rate=round(
        exclusion_rate * 100,
        2,
    ),
    maximum_allowed=round(
        maximum_allowed * 100,
        2,
    ),
    )            

    approved_exclusions = sum(
        1
        for row in records
        if row[
            "governance_decision"
        ]
        == "APPROVE_EXCLUSION"
    )

    pending_cap_review = sum(
        1
        for row in records
        if row[
            "governance_decision"
        ]
        == "PENDING_CAP_REVIEW"
    )

    pending_approval_records = [
        row
        for row in records
        if row[
            "approval_status"
        ]
        == "PENDING"
    ]

    rejected_exclusions = sum(
        1
        for row in records
        if row[
            "governance_decision"
        ]
        == "REJECT_EXCLUSION"
    )

    pending_risk_approval = sum(
        1
        for row in records
        if row[
            "governance_decision"
        ]
        == "PENDING_APPROVAL"
    )

    summary = {
        "optional_tests": len(
            optional_tests
        ),
        "exclusion_candidates": len(
            exclusion_candidates
        ),
        "approved_exclusions": (
            approved_exclusions
        ),
        "approved_exclusions_before_cap": (
            approved_exclusions_before_cap
        ),
        "exclusion_rate": round(
            exclusion_rate,
            4,
        ),
        "exclusion_rate_percent": round(
            exclusion_rate * 100,
            2,
        ),
        "maximum_allowed_exclusion_rate": (
            maximum_allowed
        ),
        "maximum_allowed_exclusion_percent": round(
            maximum_allowed * 100,
            2,
        ),
        "approval_role": configured_approval_role,
        "over_cap": over_cap,
        "pending_cap_review": (
            pending_cap_review
        ),
        "pending_approvals": len(
            pending_approval_records
        ),
        "pending_risk_approval": (
            pending_risk_approval
        ),
        "rejected_exclusions": (
            rejected_exclusions
        ),
        "protected_candidates": sum(
            1
            for row in records
            if row[
                "protected_from_exclusion"
            ]
        ),
    }
    log_event(
    "GOVERNANCE_SUMMARY_CREATED",
    agent="Exclusion Risk & Governance Agent",
    approved_exclusions=approved_exclusions,
    rejected_exclusions=rejected_exclusions,
    pending_approvals=len(
        pending_approval_records
    ),
    )

    result: dict[str, Any] = {
        "records": records,
        "optional_tests": optional_tests,
        "summary": summary,
        "agent_output": {
            "summary": summary,
            "optional_test_ids": [
                str(
                    row.get(
                        "test_case_id"
                    )
                    or ""
                ).strip()
                for row in optional_tests
                if row.get(
                    "test_case_id"
                )
            ],
            "approved_exclusion_test_ids": [
                row["test_case_id"]
                for row in records
                if row[
                    "governance_decision"
                ]
                == "APPROVE_EXCLUSION"
            ],
            "pending_approval_test_ids": [
                row["test_case_id"]
                for row in pending_approval_records
            ],
            "rejected_exclusion_test_ids": [
                row["test_case_id"]
                for row in records
                if row[
                    "governance_decision"
                ]
                == "REJECT_EXCLUSION"
            ],
            "over_cap": over_cap,
        },
    }
    log_event(
    "GOVERNANCE_COMPLETED",
    agent="Exclusion Risk & Governance Agent",
    stage="GOVERNANCE",
    status="SUCCESS",
    exclusion_candidates=len(
        exclusion_candidates
    ),
    )

    audit_event(
    "GOVERNANCE_COMPLETED",
    agent="Exclusion Risk & Governance Agent",
    message=(
        f"Reviewed {len(exclusion_candidates)} "
        f"exclusion candidates."
    ),
    details={
        "approved_exclusions":
            approved_exclusions,
        "rejected_exclusions":
            rejected_exclusions,
        "pending_approvals":
            len(
                pending_approval_records
            ),
        "over_cap":
            over_cap,
    },
    )

    result["markdown"] = (
        format_governance_dashboard(
            result
        )
    )

    return result


def _validate_orchestrator_inputs(
    scoring: dict[str, Any],
    policy: dict[str, Any],
) -> None:
    """
    Validate structured scoring and policy inputs supplied by the Master Orchestrator.
    """

    if not isinstance(
        scoring,
        dict,
    ):
        raise TypeError(
            "scoring must be a dictionary supplied by "
            "the Master Orchestrator."
        )

    if not isinstance(
        policy,
        dict,
    ):
        raise TypeError(
            "policy must be a dictionary supplied by "
            "the Master Orchestrator."
        )

    scoring_payload = scoring.get(
        "agent_output",
        scoring,
    )

    policy_payload = policy.get(
        "agent_output",
        policy,
    )

    if not isinstance(
        scoring_payload,
        dict,
    ):
        raise TypeError(
            "The Scoring Agent output must be a dictionary."
        )

    if not isinstance(
        policy_payload,
        dict,
    ):
        raise TypeError(
            "The Policy Agent output must be a dictionary."
        )

    results = scoring_payload.get(
        "results",
        scoring.get(
            "results",
        ),
    )

    if results is None:
        raise ValueError(
            "The Scoring Agent output does not contain "
            "a results collection."
        )

    if not isinstance(
        results,
        list,
    ):
        raise TypeError(
            "The Scoring Agent results must be a list."
        )


def format_governance_dashboard(
    result: dict[str, Any],
) -> str:
    """Build a user-facing Markdown dashboard for ADK."""

    records = result.get(
        "records",
        [],
    )
    summary = result.get(
        "summary",
        {},
    )

    lines: list[str] = [
        "# Exclusion Risk & Governance",
        "",
        "## Governance Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Optional tests | "
        f"{summary.get('optional_tests', 0)} |",
        "| Exclusion candidates | "
        f"{summary.get('exclusion_candidates', 0)} |",
        "| Approved exclusions | "
        f"{summary.get('approved_exclusions', 0)} |",
        "| Rejected exclusions | "
        f"{summary.get('rejected_exclusions', 0)} |",
        "| Pending approvals | "
        f"{summary.get('pending_approvals', 0)} |",
        "| Pending cap review | "
        f"{summary.get('pending_cap_review', 0)} |",
        "| Exclusion rate | "
        f"{summary.get('exclusion_rate_percent', 0):.2f}% |",
        "| Maximum allowed | "
        f"{summary.get('maximum_allowed_exclusion_percent', 0):.2f}% |",
        "| Exclusion cap exceeded | "
        f"{'Yes' if summary.get('over_cap') else 'No'} |",
        "",
        "---",
        "",
        "## Exclusion Candidate Decisions",
        "",
    ]

    if not records:
        lines.extend(
            [
                "> No EXCLUDE candidates require governance review.",
                "",
            ]
        )
        return "\n".join(lines)

    for row in records:
        flags = row.get(
            "protection_flags",
            [],
        )
        flags_text = (
            ", ".join(flags)
            if flags
            else "None"
        )

        reasons = row.get(
            "exclusion_reasons",
            [],
        )
        reasons_text = (
            "; ".join(reasons)
            if reasons
            else "No reason available"
        )

        lines.extend(
            [
                f"> ### `{row.get('test_case_id')}` — "
                f"{_display(row.get('test_name'))}",
                ">",
                f"> **Module:** `{_display(row.get('module_id'))}`",
                ">",
                f"> **Tier:** `{row.get('tier', 'TIER_3')}`",
                ">",
                f"> **Score:** `{row.get('composite_score', 0):.2f}`",
                ">",
                f"> **Proposed:** `{row.get('proposed_classification')}`",
                ">",
                f"> **Decision:** `{row.get('governance_decision')}`",
                ">",
                f"> **Likelihood:** `{row.get('likelihood')}`",
                ">",
                f"> **Business impact:** `{row.get('business_impact')}`",
                ">",
                f"> **Residual risk:** `{row.get('residual_risk')}`",
                ">",
                f"> **Protected:** "
                f"{'Yes' if row.get('protected_from_exclusion') else 'No'}",
                ">",
                f"> **Protection flags:** {flags_text}",
                ">",
                f"> **Approval:** "
                f"`{row.get('approval_status')}` "
                f"({row.get('approval_role')})",
                ">",
                f"> **Reason:** {reasons_text}",
                "",
            ]
        )

    return "\n".join(lines)


def _governance_decision(
    classification: str,
    protected_from_exclusion: bool,
    residual_risk: str,
    high_risk_exclusion_prohibited: bool,
) -> str:
    if classification != "EXCLUDE":
        return "RETAIN_TEST"

    if protected_from_exclusion:
        return "REJECT_EXCLUSION"

    if (
        residual_risk == "HIGH"
        and high_risk_exclusion_prohibited
    ):
        return "REJECT_EXCLUSION"

    if residual_risk == "LOW":
        return "APPROVE_EXCLUSION"

    return "PENDING_APPROVAL"


def _build_exclusion_reasons(
    result: dict[str, Any],
    protected_from_exclusion: bool,
    protection_flags: set[str],
    governance_decision: str,
) -> list[str]:
    reasons: list[str] = []

    for reason in result.get(
        "reasons",
        [],
    )[:3]:
        if reason:
            reasons.append(
                str(reason)
            )

    if protected_from_exclusion:
        reasons.append(
            "Exclusion prohibited by protection rule"
        )

    for flag in sorted(
        protection_flags
    ):
        reasons.append(flag)

    if governance_decision == "APPROVE_EXCLUSION":
        reasons.append(
            "Low residual risk supports exclusion"
        )
    elif governance_decision == "PENDING_APPROVAL":
        reasons.append(
            "Residual risk requires governance approval"
        )
    elif governance_decision == "REJECT_EXCLUSION":
        reasons.append(
            "Governance rejected the proposed exclusion"
        )

    return list(
        dict.fromkeys(reasons)
    )


def _likelihood_from_score(
    score: float,
) -> str:
    if score >= 60:
        return "HIGH"

    if score >= 40:
        return "MEDIUM"

    return "LOW"


def _business_impact_from_tier(
    tier: str,
) -> str:
    return {
        "TIER_1": "HIGH",
        "TIER_2": "MEDIUM",
        "TIER_3": "MEDIUM",
        "TIER_4": "LOW",
    }.get(
        tier,
        "MEDIUM",
    )


def _calculate_residual_risk(
    likelihood: str,
    business_impact: str,
    protected_from_exclusion: bool,
) -> str:
    if protected_from_exclusion:
        return "HIGH"

    risk_matrix = {
        ("HIGH", "HIGH"): "HIGH",
        ("HIGH", "MEDIUM"): "HIGH",
        ("HIGH", "LOW"): "MEDIUM",
        ("MEDIUM", "HIGH"): "HIGH",
        ("MEDIUM", "MEDIUM"): "MEDIUM",
        ("MEDIUM", "LOW"): "LOW",
        ("LOW", "HIGH"): "MEDIUM",
        ("LOW", "MEDIUM"): "LOW",
        ("LOW", "LOW"): "LOW",
    }

    return risk_matrix.get(
        (
            likelihood,
            business_impact,
        ),
        "MEDIUM",
    )


def _approval_role(
    residual_risk: str,
    classification: str,
    governance_decision: str,
    require_approval: bool,
    configured_role: str = "QA_LEAD",
) -> str:
    if classification != "EXCLUDE":
        return "NONE"

    if governance_decision == "REJECT_EXCLUSION":
        return "NONE"

    # Approval is controlled by the release/policy setting. Low-risk exclusions
    # do not automatically bypass approval when exclusion approval is required.
    if not require_approval:
        return "NONE"

    base_role = configured_role or "QA_LEAD"

    if residual_risk == "HIGH":
        if "BUSINESS_OWNER" in base_role:
            return base_role
        return f"{base_role}_AND_BUSINESS_OWNER"

    return base_role


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
            receiver='Exclusion Risk & Governance Agent',
            message_types={
                'GOVERNANCE_REQUEST',
                "AGENT_QUERY",
            },
        )

        release_id = request.release_id

        if request.message_type == "AGENT_QUERY":

            return make_response(
                request,
                sender='Exclusion Risk & Governance Agent',
                data=answer_agent_question(
                    question=str(
                        data.get("question")
                        or ""
                    ),
                    context=data.get(
                        "agent_context",
                        data,
                    ),
                ),
            )

        result = evaluate_exclusion_governance(
            scoring=data.get(
                "scoring",
                {},
            ),
            policy=data.get(
                "policy",
                {},
            ),
        )

        return make_response(
            request,
            sender='Exclusion Risk & Governance Agent',
            data=result,
        )

    except Exception as exc:

        trace_error(
            "GOVERNANCE_AGENT_FAILED",
            agent="Exclusion Risk & Governance Agent",
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
    "GOVERNANCE_AGENT_QUERY",
    agent="Exclusion Risk & Governance Agent",
    stage="GOVERNANCE",
    status="SUCCESS",
    question=question,
    )
    return {
        "status": "success",
        "agent": 'Exclusion Risk & Governance Agent',
        "question": question,
        "context": context,
        "markdown": _agent_question_markdown(question, context),
    }


def _agent_question_markdown(question: str, context: dict[str, Any]) -> str:
    import json
    output = context.get("agent_output", context)
    return "\n".join([
        f"# {'Exclusion Risk & Governance Agent'}",
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



