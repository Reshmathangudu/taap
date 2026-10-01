# from __future__ import annotations

# import importlib
# import json
# import re
# from datetime import datetime, timezone
# from pathlib import Path
# from typing import Any, Callable
# import logging
# import random
# import time
 
# logger = logging.getLogger(__name__)

# from app.agents.criticality_agent.tools import (
#     classify_application_criticality,
# )
# from app.agents.feature_change_agent.tools import (
#     analyze_release_scope,
# )
# from app.agents.governance_agent.tools import (
#     evaluate_exclusion_governance,
# )
# from app.agents.historical_agent.tools import (
#     analyze_historical_execution,
# )
# from app.agents.policy_agent.tools import (
#     calibrate_risk_policy,
# )
# from app.agents.scoring_agent.tools import (
#     DEFAULT_THRESHOLDS,
#     DEFAULT_WEIGHTS,
#     calculate_test_selection,
# )
# from app.config import Settings, get_settings
# from app.models import A2AResponse, AgentRun, PipelineState
# from app.reports import ReportGenerator
# from app.integrations.mcp_jira_client import MCPJiraClient
# from app.integrations.jira_link import parse_jira_link
# from app.services import InMemoryMessageBus
# from app.services.a2a import make_request




# # Post-run query cache.
# # The ADK conversational process creates a fresh orchestrator wrapper for each
# # tool call, so completed pipeline state and the exact Master-owned Jira snapshot
# # must live at module scope. This prevents drill-down questions from re-running
# # the complete six-agent pipeline.
# _PIPELINE_STATE_CACHE: dict[str, PipelineState] = {}
# _PIPELINE_SOURCE_CACHE: dict[str, dict[str, list[dict[str, Any]]]] = {}

# # Jira-source cache: reuse a release's Jira/MCP snapshot across separate
# # execute() calls within a bounded TTL (settings.jira_source_cache_ttl_seconds)
# # instead of re-running the full paginated project-wide issue fetch + dynamic
# # field discovery every time — that load alone can take many minutes on a
# # large project. Deliberately separate from _PIPELINE_SOURCE_CACHE above,
# # which is only populated after a FULLY successful run; this one is populated
# # right after the Jira fetch itself succeeds, so a retry after a later-stage
# # failure (e.g. a bad Release_Type) still benefits from it. Keyed by
# # (jira_project_key, release_id) since a fresh orchestrator is constructed
# # per request and could in principle target a different Jira project.
# #
# # Trade-off, by design: within the TTL window, a re-run of the same release
# # will NOT pick up intervening Jira changes (new/removed test cases, an
# # edited Release_Type, etc.) — this intentionally relaxes the "always fetch
# # a fresh snapshot" guarantee described in app/prompts/master_orchestrator.md,
# # in exchange for not re-paying the full Jira load on every request.
# _JIRA_SOURCE_CACHE: dict[tuple[str, str], tuple[float, dict[str, list[dict[str, Any]]]]] = {}


# def _query_snapshot_path(output_dir: str | Path, release_id: str) -> Path:
#     """Return the durable post-run query snapshot path."""
#     normalized = str(release_id or "").strip().upper()
#     if not normalized:
#         raise ValueError("release_id cannot be empty.")
#     return Path(output_dir) / f"{normalized}_master_query_snapshot.json"


# def _write_query_snapshot(
#     output_dir: str | Path,
#     state: PipelineState,
#     source_data: dict[str, list[dict[str, Any]]],
# ) -> None:
#     """Persist the completed Master state for cross-process ADK queries.

#     ADK tool calls are not guaranteed to execute in the same Python process, so
#     an in-memory module cache alone is insufficient. The snapshot contains the
#     completed PipelineState plus the exact Master-owned Jira logical blocks used
#     by the pipeline.
#     """
#     path = _query_snapshot_path(output_dir, state.release_id)
#     path.parent.mkdir(parents=True, exist_ok=True)

#     payload = {
#         "release_id": state.release_id,
#         "state": state.model_dump(mode="json"),
#         "source_data": {
#             str(key): list(value)
#             for key, value in source_data.items()
#             if isinstance(value, list)
#         },
#     }

#     temp_path = path.with_suffix(".json.tmp")
#     temp_path.write_text(
#         json.dumps(payload, ensure_ascii=False, default=str),
#         encoding="utf-8",
#     )
#     temp_path.replace(path)


# def _load_query_snapshot(
#     output_dir: str | Path,
#     release_id: str,
# ) -> tuple[PipelineState | None, dict[str, list[dict[str, Any]]]]:
#     """Load a durable query snapshot, falling back to the generated report."""
#     path = _query_snapshot_path(output_dir, release_id)
#     if not path.is_file():
#         # Backward-compatible fallback for runs produced before the durable
#         # query snapshot was introduced. The report contains the full pipeline
#         # state, including scoring results and change-impact IDs.
#         report_path = path.parent / f"{str(release_id).strip().upper()}_risk_tier_report.json"
#         if not report_path.is_file():
#             return None, {}
#         try:
#             report_payload = json.loads(report_path.read_text(encoding="utf-8"))
#             state = PipelineState.model_validate(report_payload)
#             return state, {}
#         except Exception:
#             return None, {}

#     try:
#         payload = json.loads(path.read_text(encoding="utf-8"))
#         state_payload = payload.get("state", payload)
#         state = PipelineState.model_validate(state_payload)
#         raw_source = payload.get("source_data", {})
#         source_data = {
#             str(key): list(value)
#             for key, value in raw_source.items()
#             if isinstance(value, list)
#         } if isinstance(raw_source, dict) else {}
#         return state, source_data
#     except Exception:
#         return None, {}


# JIRA_SOURCE_BLOCKS = {
#     "releases", "modules", "epics", "stories", "requirements", "rtm",
#     "test_cases", "release_scope", "dependencies", "out_of_scope",
#     "criticality_factors", "tier_change_log", "executions", "defects",
#     "flaky_tests", "policies", "regulatory_tests", "release_rules",
# }

# FEATURE_INPUT_BLOCKS: tuple[str, ...] = (
#     "releases",
#     "epics",
#     "stories",
#     "requirements",
#     "rtm",
#     "test_cases",
#     "release_scope",
#     "dependencies",
#     "out_of_scope",
# )

# CRITICALITY_INPUT_BLOCKS: tuple[str, ...] = (
#     "modules",
#     "test_cases",
# )

# HISTORICAL_INPUT_BLOCKS: tuple[str, ...] = (
#     "test_cases",
#     "executions",
#     "defects",
#     "flaky_tests",
# )

# POLICY_INPUT_BLOCKS: tuple[str, ...] = (
#     "policies",
#     "regulatory_tests",
#     "release_rules",
# )

# SCORING_INPUT_BLOCKS: tuple[str, ...] = (
#     "test_cases",
# )


# class RiskTierMasterOrchestrator:
#     """
#     Coordinate all Risk Tier stages in the required business order.

#     The Master Orchestrator coordinates Jira/MCP-backed raw data only. Each specialist stage receives serializable logical data
#     blocks and/or structured outputs from earlier stages.

#     Execution order:

#     1. Feature / Epic Change Impact
#     2. Application Criticality
#     3. Historical Execution Intelligence
#     4. Policy / Risk Appetite
#     5. Decision Engine / Risk Scoring
#     6. Exclusion Risk & Governance
#     7. Report Generation
#     """

#     name = "Risk Tier Master Orchestrator"

#     def __init__(
#         self,
#         output_dir: str | Path,
#         jira_client: MCPJiraClient | None = None,
#         jira_project_key: str = "",
#         jira_release_label: str = "",
#     ):
#         self.output_dir = Path(output_dir)
#         self.output_dir.mkdir(parents=True, exist_ok=True)

#         self.jira_client = jira_client
#         self.jira_project_key = str(jira_project_key or "").strip()
#         self.jira_release_label = str(jira_release_label or "").strip()
#         self._jira_field_ids: dict[str, str] | None = None
#         self._jira_source_data: dict[str, list[dict[str, Any]]] = {}

#         # Optional real-time progress callback for AG-UI streaming. Set per
#         # execute() call; a no-op for every existing caller that doesn't pass
#         # one (CLI, plain REST /analyze). agent_name is the human-readable
#         # name of whichever agent this update is about (e.g. "Feature / Epic
#         # Change Impact Agent"), separate from stage_key's stable routing id.
#         self._on_stage: Callable[[str, str, str, str | None], None] | None = None

#         self.message_bus = InMemoryMessageBus()
#         self.report_generator = ReportGenerator(self.output_dir)

#     def _emit_stage(
#         self,
#         stage_key: str,
#         status: str,
#         text: str,
#         agent_name: str | None = None,
#     ) -> None:
#         """Best-effort progress emit; never let a UI callback break a run."""
#         if self._on_stage is None:
#             return
#         try:
#             self._on_stage(stage_key, status, text, agent_name)
#         except Exception:
#             logger.debug("on_stage callback raised", exc_info=True)

#     @classmethod
#     def from_settings(
#         cls,
#         settings: Settings | None = None,
#         jira_link: str | None = None,
#     ) -> "RiskTierMasterOrchestrator":
#         """Create a Jira/MCP-only orchestrator."""
#         resolved_settings = settings or get_settings()
#         link_ctx = parse_jira_link(jira_link) if jira_link else None

#         resolved_project_key = (
#             link_ctx.project_key
#             if link_ctx and link_ctx.project_key
#             else resolved_settings.jira_project_key
#         )
#         resolved_release_label = (
#             (link_ctx.release_label if link_ctx and link_ctx.release_label else None)
#             or resolved_settings.default_release
#         )

#         if not resolved_project_key:
#             raise RuntimeError(
#                 "JIRA_PROJECT_KEY or a Jira link containing the project key is required."
#             )

#         return cls(
#             output_dir=resolved_settings.output_dir,
#             jira_client=MCPJiraClient(),
#             jira_project_key=str(resolved_project_key),
#             jira_release_label=str(resolved_release_label or ""),
#         )

#     @classmethod
#     def for_query(cls) -> "RiskTierMasterOrchestrator":
#         """Create a lightweight orchestrator wrapper for internal helpers.

#         Conversational follow-up questions are handled by the direct query
#         tools registered in ``app.orchestrator.tools``. This wrapper remains
#         available for backward compatibility and for internal callers that
#         need access to the Master caches without creating a Jira client.
#         """
#         settings = get_settings()
#         return cls(output_dir=settings.output_dir)

#     @classmethod
#     def get_cached_state(
#         cls,
#         release_id: str,
#     ) -> PipelineState | None:
#         normalized = str(release_id or "").strip().upper()
#         state = _PIPELINE_STATE_CACHE.get(normalized)
#         if state is not None:
#             return state

#         # Cross-process fallback: ADK may invoke the follow-up tool in another
#         # worker, so recover the completed state from the durable snapshot.
#         settings = get_settings()
#         loaded_state, loaded_source = _load_query_snapshot(
#             settings.output_dir,
#             normalized,
#         )
#         if loaded_state is not None:
#             _PIPELINE_STATE_CACHE[normalized] = loaded_state
#             _PIPELINE_SOURCE_CACHE[normalized] = loaded_source
#         return loaded_state

#     @classmethod
#     def get_cached_source_data(
#         cls,
#         release_id: str,
#     ) -> dict[str, list[dict[str, Any]]]:
#         normalized = str(release_id or "").strip().upper()
#         source_data = _PIPELINE_SOURCE_CACHE.get(normalized)
#         if source_data:
#             return source_data

#         settings = get_settings()
#         loaded_state, loaded_source = _load_query_snapshot(
#             settings.output_dir,
#             normalized,
#         )
#         if loaded_state is not None:
#             _PIPELINE_STATE_CACHE[normalized] = loaded_state
#             _PIPELINE_SOURCE_CACHE[normalized] = loaded_source
#         return loaded_source

#     @staticmethod
#     def _compact_row(row: Any, keys: tuple[str, ...]) -> dict[str, Any]:
#         if not isinstance(row, dict):
#             return {"value": str(row)}
#         compact: dict[str, Any] = {}
#         for key in keys:
#             value = row.get(key)
#             if value not in (None, "", [], {}):
#                 compact[key] = value
#         return compact

#     @staticmethod
#     def _question_kind(question: str) -> str:
#         q = str(question or "").lower()
#         if "epic" in q and "story" in q and "test" in q:
#             return "traceability"
#         if "optional" in q and ("score" in q or "composite" in q):
#             return "optional_scores"
#         if "directly impacted" in q and ("classified" in q or "difference" in q or "only" in q):
#             return "population_reconciliation"
#         if "new-feature" in q or "new feature" in q:
#             return "new_feature_tests"
#         if "flaky" in q:
#             return "flaky"
#         if "insufficient history" in q or "insufficient-history" in q:
#             return "insufficient_history"
#         if "defect protected" in q or "confirmed defect" in q:
#             return "defect_protection"
#         # "tier" alone is too broad a signal: a scoring/protection question
#         # like "which Tier-1 tests were prevented from being downgraded
#         # during scoring?" mentions a tier but is not a criticality-tier-
#         # matrix question — only classify as "criticality" on a bare "tier"
#         # mention when nothing else marks it as a scoring/protection/
#         # exclusion question instead (those are handled by their own agent).
#         if "criticality" in q or (
#             "tier" in q
#             and not any(
#                 keyword in q
#                 for keyword in ("scor", "protect", "downgrad", "exclu", "govern", "flag")
#             )
#         ):
#             return "criticality"
#         if "policy" in q or "regulatory" in q or "mandatory" in q:
#             return "policy"
#         if "governance" in q or "approval" in q:
#             return "governance"
#         return "general"

#     def get_cached_agent_context(
#         self,
#         release_id: str,
#         agent: str,
#         question: str = "",
#     ) -> dict[str, Any]:
#         """Return a compact, question-specific projection of completed pipeline cache.

#         This method never queries Jira and never reruns the pipeline. It is deliberately
#         bounded so its result cannot flood the ADK/LLM context window.
#         """
#         normalized_release_id = str(release_id or "").strip().upper()
#         normalized_agent = str(agent or "").strip().lower()
#         state = self.get_cached_state(normalized_release_id)
#         if state is None:
#             raise RuntimeError(
#                 f"No completed pipeline cache exists for {normalized_release_id}. "
#                 "Run execute_risk_tier_pipeline first."
#             )

#         kind = self._question_kind(question)
#         change = self._unwrap_agent_output(state.change_impact)
#         criticality = self._unwrap_agent_output(state.criticality)
#         history = self._unwrap_agent_output(state.history)
#         policy = self._unwrap_agent_output(state.policy)
#         scoring = self._unwrap_agent_output(state.scoring)
#         governance = self._unwrap_agent_output(state.governance)
#         cached_source = self.get_cached_source_data(normalized_release_id)

#         result: dict[str, Any] = {
#             "source": "MASTER_PIPELINE_CACHE",
#             "cache_only": True,
#             "release_id": normalized_release_id,
#             "agent": normalized_agent,
#             "question_kind": kind,
#         }

#         if kind == "traceability":
#             epics = []
#             for row in cached_source.get("epics", []):
#                 epics.append(self._compact_row(row, ("Epic_ID", "Epic ID", "work_item_id", "issue_key", "summary", "Epic_Name", "Epic Name")))
#             stories = []
#             for row in cached_source.get("stories", []):
#                 stories.append(self._compact_row(row, ("User_Story_ID", "Story_ID", "User Story ID", "work_item_id", "issue_key", "Epic_ID", "Epic ID", "summary", "User_Story_Name", "Story Name")))
#             requirements = []
#             for row in cached_source.get("requirements", []):
#                 requirements.append(self._compact_row(row, ("Requirement_ID", "Requirement ID", "work_item_id", "issue_key", "User_Story_ID", "Story_ID", "User Story ID", "summary", "Requirement_Name", "Requirement Name")))
#             rtm = []
#             for row in cached_source.get("rtm", []):
#                 rtm.append(self._compact_row(row, ("Requirement_ID", "Requirement ID", "Test_Case_ID", "Test Case ID", "Mapping_Type", "Mapping Type", "Mapping_Status", "Mapping Status")))
#             result["traceability"] = {
#                 "epics": epics,
#                 "stories": stories,
#                 "requirements": requirements,
#                 "rtm": rtm,
#             }

#         elif kind == "optional_scores":
#             rows = []
#             for row in scoring.get("results", []):
#                 if isinstance(row, dict) and str(row.get("classification") or "").strip().upper() == "OPTIONAL":
#                     rows.append(self._compact_row(row, (
#                         "test_case_id", "test_name", "classification", "base_classification",
#                         "composite_score", "change_impact_factor", "criticality_factor",
#                         "historical_value_score", "historical_value_factor", "release_risk_factor",
#                         "tier", "risk_band", "protection_flags", "reasons",
#                     )))
#             scores = [float(r["composite_score"]) for r in rows if r.get("composite_score") not in (None, "")]
#             result["optional_scores"] = rows
#             result["summary"] = {
#                 "count": len(rows),
#                 "min": min(scores) if scores else None,
#                 "max": max(scores) if scores else None,
#                 "average": (sum(scores) / len(scores)) if scores else None,
#             }

#         elif kind == "population_reconciliation":
#             direct_ids = sorted({self._normalize_test_id(v) for v in change.get("direct_test_ids", []) if self._normalize_test_id(v)})
#             scored_rows = [r for r in scoring.get("results", []) if isinstance(r, dict)]
#             scored_ids = sorted({self._normalize_test_id(r.get("test_case_id")) for r in scored_rows if self._normalize_test_id(r.get("test_case_id"))})
#             result["population_reconciliation"] = {
#                 "direct_count": len(direct_ids),
#                 "scored_count": len(scored_ids),
#                 "missing_from_scoring": sorted(set(direct_ids) - set(scored_ids)),
#                 "outside_direct_impact": sorted(set(scored_ids) - set(direct_ids)),
#             }

#         elif kind == "new_feature_tests":
#             result["new_feature_test_ids"] = sorted({self._normalize_test_id(v) for v in change.get("new_feature_test_ids", []) if self._normalize_test_id(v)})
#             result["summary"] = change.get("summary", {})

#         elif kind == "flaky":
#             ids = change_ids = history.get("flaky_test_ids", [])
#             result["flaky_test_ids"] = sorted({self._normalize_test_id(v) for v in ids if self._normalize_test_id(v)})
#             result["summary"] = history.get("summary", {})

#         elif kind == "insufficient_history":
#             result["insufficient_history_test_ids"] = sorted({self._normalize_test_id(v) for v in history.get("insufficient_history_test_ids", []) if self._normalize_test_id(v)})
#             result["summary"] = history.get("summary", {})

#         elif kind == "defect_protection":
#             result["defect_protected_test_ids"] = sorted({self._normalize_test_id(v) for v in history.get("defect_protected_test_ids", []) if self._normalize_test_id(v)})
#             result["summary"] = history.get("summary", {})

#         elif kind == "criticality":
#             result["criticality"] = {
#                 "summary": criticality.get("summary", {}),
#                 "module_assignments": criticality.get("module_assignments", {}),
#                 "test_tags": criticality.get("test_tags", {}),
#             }

#         elif kind == "policy":
#             result["policy"] = {
#                 "summary": policy.get("summary", {}),
#                 "release_type": policy.get("release_type"),
#                 "mandatory_test_ids": policy.get("mandatory_test_ids", []),
#                 "regulatory_test_ids": policy.get("regulatory_test_ids", []),
#             }

#         elif kind == "governance":
#             result["governance"] = {"summary": governance.get("summary", {})}

#         # Always attach the targeted agent's own raw output, regardless of
#         # `kind` — `kind` only controls which EXTRA cross-cutting summary
#         # gets bolted on above for topic-specific questions (flaky, policy,
#         # criticality, etc.). Previously this only ran in the `else` (i.e.
#         # "kind is none of the above") branch, so any question that matched
#         # one of those specific kinds silently never got agent_output at
#         # all — regardless of which agent was actually targeted. That
#         # caused _answer_single_agent_question's own validation (which
#         # different agents check via different key names, several of them
#         # via "agent_output") to fail even though a real cached result
#         # existed. See e.g. a scoring/protection question that happens to
#         # mention "tier" and gets classified kind="criticality".
#         if normalized_agent in {"scoring", "selection"}:
#             result["agent_output"] = scoring
#         elif normalized_agent in {"history", "historical"}:
#             result["agent_output"] = history
#         elif normalized_agent in {"feature", "change"}:
#             result["agent_output"] = change
#         elif normalized_agent == "criticality":
#             result["agent_output"] = criticality
#         elif normalized_agent in {"policy", "risk"}:
#             result["agent_output"] = policy
#         elif normalized_agent in {"governance", "exclusion"}:
#             result["agent_output"] = governance

#         serialized = json.dumps(result, ensure_ascii=False, default=str)
#         if len(serialized) > 100000:
#             # Last-resort hard guard. Return only compact summary/counts.
#             return {
#                 "source": "MASTER_PIPELINE_CACHE",
#                 "cache_only": True,
#                 "release_id": normalized_release_id,
#                 "agent": normalized_agent,
#                 "question_kind": kind,
#                 "warning": "The cached result was larger than the conversational safety limit; only summary metadata was returned.",
#                 "summary": result.get("summary", {}),
#                 "counts": {
#                     "optional": len(result.get("optional_scores", [])),
#                     "new_feature": len(result.get("new_feature_test_ids", [])),
#                     "flaky": len(result.get("flaky_test_ids", [])),
#                     "insufficient_history": len(result.get("insufficient_history_test_ids", [])),
#                     "defect_protected": len(result.get("defect_protected_test_ids", [])),
#                 },
#             }
#         return result

#     @classmethod
#     def _cache_completed_pipeline(
#         cls,
#         state: PipelineState,
#         source_data: dict[str, list[dict[str, Any]]],
#     ) -> None:
#         release_id = str(state.release_id or "").strip().upper()
#         if not release_id:
#             return
#         normalized_source = {
#             key: list(value)
#             for key, value in source_data.items()
#             if isinstance(value, list)
#         }
#         _PIPELINE_STATE_CACHE[release_id] = state
#         _PIPELINE_SOURCE_CACHE[release_id] = normalized_source

#         # Make the completed state durable so subsequent ADK workers can answer
#         # questions even after the original pipeline process has ended.
#         _write_query_snapshot(
#             output_dir=get_settings().output_dir,
#             state=state,
#             source_data=normalized_source,
#         )

        

#     def _load_source_data(
#         self,
#         block_names: tuple[str, ...],
#     ) -> dict[
#         str,
#         list[dict[str, Any]],
#     ]:
#         """
#         Load logical data blocks from the current Jira/MCP snapshot.

#         Sub-agents receive only plain dictionaries and lists. They do not
#         receive Jira/MCP client objects or any other infrastructure object.
#         """

#         if not block_names:
#             return {}

#         source_data: dict[
#             str,
#             list[dict[str, Any]],
#         ] = {}

#         for block_name in block_names:
#             rows = self._load_data_block(
#                 block_name
#             )

#             if not isinstance(
#                 rows,
#                 list,
#             ):
#                 raise TypeError(
#                     f"Data block {block_name!r} returned "
#                     f"{type(rows).__name__}; expected list."
#                 )

#             source_data[block_name] = rows

#         return source_data

#     def _prepare_jira_source_data(
#         self,
#         release_id: str,
#     ) -> None:
#         """
#         Load the Jira-backed input blocks for this execution.

#         Reuses a recently-cached snapshot for this exact (project, release)
#         within settings.jira_source_cache_ttl_seconds instead of re-running
#         the full Jira fetch — see _JIRA_SOURCE_CACHE above for the trade-off.
#         """

#         normalized_release_id = str(release_id or "").strip().upper()
#         cache_key = (self.jira_project_key, normalized_release_id)
#         ttl_seconds = get_settings().jira_source_cache_ttl_seconds

#         if ttl_seconds > 0:
#             cached = _JIRA_SOURCE_CACHE.get(cache_key)
#             if cached is not None:
#                 cached_at, cached_source_data = cached
#                 age_seconds = time.time() - cached_at
#                 if age_seconds < ttl_seconds:
#                     self._jira_source_data = cached_source_data
#                     self._emit_stage(
#                         "orchestrator", "running",
#                         f"Reusing Jira snapshot cached {int(age_seconds)}s ago for "
#                         f"{normalized_release_id} (cache TTL {ttl_seconds}s)…",
#                         agent_name="Master Orchestrator",
#                     )
#                     return

#         self._jira_source_data = self._load_jira_source_data(
#             release_id
#         )
#         _JIRA_SOURCE_CACHE[cache_key] = (time.time(), self._jira_source_data)

#     def _load_data_block(
#         self,
#         block_name: str,
#     ) -> list[dict[str, Any]]:
#         """Return one logical block from the Jira/MCP snapshot."""
#         normalized = str(block_name or "").strip()
#         rows = self._jira_source_data.get(normalized, [])
#         if not isinstance(rows, list):
#             raise TypeError(
#                 f"Jira data block {normalized!r} returned "
#                 f"{type(rows).__name__}; expected list."
#             )
#         return rows

#     def _load_jira_source_data(
#         self,
#         release_id: str,
#     ) -> dict[str, list[dict[str, Any]]]:
#         """Load all Jira/MCP-backed logical blocks required by the pipeline."""
#         if not self.jira_client or not self.jira_project_key:
#             raise RuntimeError("MCP Jira client and JIRA_PROJECT_KEY are required.")

#         # This method is where essentially all of a run's wall-clock time is
#         # actually spent — every later stage reads from data already loaded
#         # into memory here, with no further Jira/network calls. Emitting
#         # sub-progress under stage_key="orchestrator" keeps that dominant
#         # phase from looking like a single opaque spinner.
#         self._emit_stage(
#             "orchestrator", "running",
#             "Resolving Jira custom field mappings…",
#             agent_name="Master Orchestrator",
#         )
#         field_ids = self._resolve_jira_field_ids()
#         fields_to_fetch = [
#             "summary",
#             "description",
#             "issuetype",
#             "labels",
#             "status",
#             "parent",
#             "priority",
#             "key",
#             "id",
#             "issuelinks",
#             "fixVersions",
#         ]
#         for value in field_ids.values():
#             if isinstance(value, (list, tuple, set)):
#                 fields_to_fetch.extend(str(item) for item in value if item)
#             elif value:
#                 fields_to_fetch.append(str(value))
#         unique_fields = list(dict.fromkeys(fields_to_fetch))

#         project_clause = f'project = "{self.jira_project_key}"'
#         self._emit_stage(
#             "orchestrator", "running",
#             f"Querying Jira project {self.jira_project_key!r} for all issues…",
#             agent_name="Master Orchestrator",
#         )
#         all_issues = self._fetch_jira_issues(
#             f"{project_clause} ORDER BY key ASC",
#             unique_fields,
#         )
#         self._emit_stage(
#             "orchestrator", "running",
#             f"Fetched {len(all_issues)} Jira issues — categorizing and building release scope…",
#             agent_name="Master Orchestrator",
#         )

#         rows: list[dict[str, Any]] = []
#         issue_by_key: dict[str, dict[str, Any]] = {}

#         for issue in all_issues:
#             row = self._jira_issue_to_row(issue, field_ids)
#             rows.append(row)
#             key = str(row.get("issue_key") or "").strip()
#             if key:
#                 issue_by_key[key] = row

#         # Categorize first so parent traversal can identify parent types.
#         for row in rows:
#             row["category"] = self._jira_issue_category(row)

#         # Multiple passes ensure TC -> Story -> Epic is fully enriched even if
#         # Jira key ordering puts a child before its ancestor.
#         for _ in range(3):
#             for row in rows:
#                 self._enrich_jira_row_with_hierarchy(
#                     row=row,
#                     issue_by_key=issue_by_key,
#                 )

#         # Reclassify after enrichment because some rows may only become
#         # identifiable through inherited logical IDs.
#         for row in rows:
#             row["category"] = self._jira_issue_category(row)

#         def by_cat(category: str) -> list[dict[str, Any]]:
#             return [r for r in rows if r.get("category") == category]

#         releases = by_cat("releases")
#         modules = by_cat("modules")
#         epics_all = by_cat("epics")
#         stories_all = by_cat("stories")
#         requirements_all = by_cat("requirements")
#         test_cases_all = by_cat("test_cases")
#         executions = by_cat("executions")
#         defects = by_cat("defects")
#         flaky_tests = by_cat("flaky_tests")
#         policies = by_cat("policies")
#         release_rules = by_cat("release_rules")

#         rid = str(release_id or "").strip().upper()
#         rid_normalized = self._normalize_key(rid)

#         def identity_tokens(row: dict[str, Any]) -> set[str]:
#             vals = set(self._row_identity_tokens(row))

#             for candidate in (
#                 row.get("Release_ID"),
#                 row.get("Release ID"),
#                 row.get("work_item_id"),
#                 row.get("issue_key"),
#             ):
#                 normalized = self._normalize_key(candidate)
#                 if normalized:
#                     vals.add(normalized)

#             labels = row.get("labels") or []

#             if isinstance(labels, (list, tuple, set)):
#                 for label in labels:
#                     normalized = self._normalize_key(label)
#                     if normalized:
#                         vals.add(normalized)
#             else:
#                 normalized = self._normalize_key(labels)
#                 if normalized:
#                     vals.add(normalized)

#             fix_versions = (row.get("Fix_Versions") or row.get("fixVersions") or [])

#             if isinstance(fix_versions, (list, tuple, set)):
#                 version_values = fix_versions
#             else:
#                 version_values = [fix_versions]

#             for version in version_values:
#                 if isinstance(version, dict):
#                     version_name = version.get("name") or version.get("value") or ""
#                 else:
#                     version_name = version

#                 normalized = self._normalize_key(version_name)

#                 if normalized:
#                     vals.add(normalized)

#             return vals

#         def release_match(row: dict[str, Any]) -> bool:
#             tokens = identity_tokens(row)
#             summary = self._normalize_key(row.get("summary"))

#             return (
#                 rid_normalized in tokens
#                 or rid_normalized in summary
#             )

#         matching_releases = [row for row in releases if release_match(row)]

#         if not matching_releases:

#             fix_version_matches: list[dict[str, Any]] = []

#             for row in rows:

#                 fix_versions = (row.get("Fix_Versions") or row.get("fixVersions") or [])

#                 if not isinstance(fix_versions, (list, tuple, set)):
#                     fix_versions = [fix_versions]

#                 for version in fix_versions:

#                     if isinstance(version, dict):
#                         version_name = version.get("name") or version.get("value") or ""
#                     else:
#                         version_name = version

#                     if self._normalize_key(version_name) == rid_normalized:
#                         fix_version_matches.append(row)
#                         break

#             if fix_version_matches:

#                 matching_releases = [{
#                     "category": "releases",
#                     "Release_ID": rid,
#                     "Release Name": rid,
#                     "summary": rid,
#                     "release_source": "jira_fix_version",
#                     "source_issue_count": len(fix_version_matches),
#                 }]

#                 releases.extend(matching_releases)

#         if not matching_releases:

#             available = set()

#             for row in releases:

#                 candidate = (
#                     row.get("Release_ID")
#                     or row.get("work_item_id")
#                     or self._strip_work_item_prefix(str(row.get("summary") or ""))
#                 )

#                 if candidate:
#                     available.add(str(candidate).strip())

#                 fix_versions = (row.get("Fix_Versions") or row.get("fixVersions") or [])

#                 if not isinstance(fix_versions, (list, tuple, set)):
#                     fix_versions = [fix_versions]

#                 for version in fix_versions:

#                     if isinstance(version, dict):
#                         name = version.get("name") or version.get("value") or ""
#                     else:
#                         name = version

#                     if name:
#                         available.add(str(name).strip())

#             raise ValueError(
#                 f"Release {rid!r} was not found "
#                 "in Jira release data or Fix Versions. "
#                 f"Available releases/fixVersions: "
#                 f"{sorted(available)}"
#             )

#         # Seed scope from every Jira issue that explicitly references this
#         # release via label, Release_ID, summary, or Fix Version.
#         scoped_keys: set[str] = set()
#         for row in rows:
#             if release_match(row):
#                 key = str(row.get("issue_key") or "").strip()
#                 if key:
#                     scoped_keys.add(key)

#         # Expand in BOTH directions. This is important for this project because
#         # the release label is sometimes on the Epic, while reusable descendants
#         # may not carry the label themselves. It also lets a release-labelled
#         # child bring its parent Story/Epic into the logical scope.
#         changed = True
#         while changed:
#             changed = False
#             for row in rows:
#                 issue_key = str(row.get("issue_key") or "").strip()
#                 parent_key = str(row.get("parent_key") or "").strip()

#                 # Parent -> child
#                 if issue_key and parent_key and parent_key in scoped_keys and issue_key not in scoped_keys:
#                     scoped_keys.add(issue_key)
#                     changed = True

#                 # Child -> parent
#                 if issue_key in scoped_keys and parent_key and parent_key not in scoped_keys:
#                     scoped_keys.add(parent_key)
#                     changed = True

#         def in_scope(row: dict[str, Any]) -> bool:
#             issue_key = str(row.get("issue_key") or "").strip()
#             if issue_key in scoped_keys:
#                 return True
#             return bool(identity_tokens(row) & {
#                 self._normalize_key(rid),
#             })

#         epics = [r for r in epics_all if in_scope(r)]
#         stories = [r for r in stories_all if in_scope(r)]
#         requirements = [r for r in requirements_all if in_scope(r)]

#         # Resolve dependencies before broadening test-case scope so downstream
#         # module tests are available to the Feature Agent.
#         dependencies = self._build_module_dependencies(
#             modules,
#             issue_by_key,
#         )

#         release_scoped_test_cases = [
#             r
#             for r in test_cases_all
#             if in_scope(r)
#         ]

#         dependent_module_ids_for_scope = {
#             str(dependency.get("Dependent_Module_ID") or "").strip()
#             for dependency in dependencies
#             if str(dependency.get("Dependent_Module_ID") or "").strip()
#         }

#         dependency_module_test_cases = [
#             r
#             for r in test_cases_all
#             if str(
#                 r.get("Module_ID")
#                 or r.get("Module ID")
#                 or ""
#             ).strip() in dependent_module_ids_for_scope
#             and str(
#                 r.get("Test_Status")
#                 or r.get("Test Status")
#                 or r.get("status")
#                 or "ACTIVE"
#             ).strip().upper()
#             not in {
#                 "INACTIVE",
#                 "DISABLED",
#                 "RETIRED",
#                 "DEPRECATED",
#             }
#         ]

#         test_case_rows_by_key: dict[str, dict[str, Any]] = {}
#         for row in (
#             release_scoped_test_cases
#             + dependency_module_test_cases
#         ):
#             key = str(
#                 row.get("issue_key")
#                 or row.get("Test_Case_ID")
#                 or row.get("Test Case ID")
#                 or row.get("work_item_id")
#                 or ""
#             ).strip()
#             if key:
#                 test_case_rows_by_key[key] = row

#         test_cases = list(test_case_rows_by_key.values())

#         # Reconstruct RTM from Test Case fields. Requirements are NOT Jira
#         # parents in this project; Requirement_ID on the Test Case is the RTM
#         # source of truth.
#         rtm: list[dict[str, Any]] = []
#         seen_rtm: set[tuple[str, str]] = set()
#         for row in test_cases:
#             tc = str(
#                 row.get("Test_Case_ID")
#                 or row.get("Test Case ID")
#                 or row.get("work_item_id")
#                 or ""
#             ).strip()
#             req = str(
#                 row.get("Requirement_ID")
#                 or row.get("Requirement ID")
#                 or ""
#             ).strip()
#             if not tc or not req:
#                 continue

#             mapping_type = str(
#                 row.get("Mapping_Type")
#                 or row.get("Mapping Type")
#                 or "PRIMARY"
#             ).strip().upper()
#             mapping_status = str(
#                 row.get("Mapping_Status")
#                 or row.get("Mapping Status")
#                 or "ACTIVE"
#             ).strip().upper()

#             signature = (self._normalize_key(req), self._normalize_key(tc))
#             if signature in seen_rtm:
#                 continue
#             seen_rtm.add(signature)

#             rtm.append({
#                 "Requirement_ID": req,
#                 "Test_Case_ID": tc,
#                 "Mapping_Type": mapping_type,
#                 "Mapping_Status": mapping_status,
#             })

#         # Reconstruct release scope for the Feature Agent. Epic/Story/Requirement
#         # rows are each represented explicitly, while the same IDs are repeated
#         # where useful for downstream joins.
#         release_scope: list[dict[str, Any]] = []
#         seen_scope: set[tuple[str, str, str]] = set()
#         for collection_name, collection in (
#             ("epics", epics),
#             ("stories", stories),
#             ("requirements", requirements),
#         ):
#             for row in collection:
#                 epic_id = str(
#                     row.get("Epic_ID")
#                     or row.get("Epic ID")
#                     or row.get("work_item_id")
#                     if collection_name == "epics"
#                     else ""
#                 ).strip()
#                 story_id = str(
#                     row.get("User_Story_ID")
#                     or row.get("Story_ID")
#                     or row.get("User Story ID")
#                     or row.get("work_item_id")
#                     if collection_name == "stories"
#                     else ""
#                 ).strip()
#                 requirement_id = str(
#                     row.get("Requirement_ID")
#                     or row.get("Requirement ID")
#                     or row.get("work_item_id")
#                     if collection_name == "requirements"
#                     else ""
#                 ).strip()

#                 # Fill inherited IDs from the normalized hierarchy.
#                 epic_id = epic_id or str(row.get("Epic_ID") or row.get("Epic ID") or "").strip()
#                 story_id = story_id or str(row.get("User_Story_ID") or row.get("Story_ID") or "").strip()
#                 requirement_id = requirement_id or str(row.get("Requirement_ID") or row.get("Requirement ID") or "").strip()

#                 item_id = requirement_id or story_id or epic_id or str(row.get("work_item_id") or row.get("issue_key") or "").strip()
#                 signature = (collection_name, self._normalize_key(item_id), rid_normalized)
#                 if not item_id or signature in seen_scope:
#                     continue
#                 seen_scope.add(signature)

#                 release_scope.append({
#                     "Release_ID": rid,
#                     "Epic_ID": epic_id,
#                     "User_Story_ID": story_id,
#                     "Requirement_ID": requirement_id,
#                     "Change_Type": row.get("Change_Type") or row.get("Change_Status") or "MODIFIED",
#                     "Scope_Status": row.get("Scope_Status") or row.get("Scope Status") or "IN_SCOPE",
#                     "Change_Description": row.get("Change_Description") or row.get("Change Description") or row.get("description") or "",
#                     "Module_ID": row.get("Module_ID") or row.get("Module ID") or "",
#                 })


#         normalized_executions: list[dict[str, Any]] = []
#         for row in executions:
#             normalized_executions.append({
#                 **row,
#                 "Execution_ID": row.get("Execution_ID") or row.get("Execution ID") or row.get("work_item_id") or "",
#                 "Test_Case_ID": row.get("Test_Case_ID") or row.get("Test Case ID") or "",
#                 "Release_ID": row.get("Release_ID") or row.get("Release ID") or "",
#                 "Execution_Date": row.get("Execution_Date") or row.get("Execution Date") or "",
#                 "Status": row.get("Execution_Status") or row.get("Execution Status") or row.get("Status") or row.get("status") or "",
#                 "Failure_Type": row.get("Failure_Type") or row.get("Failure Type") or "",
#                 "Is_Flaky": row.get("Is_Flaky") or row.get("Is Flaky") or "NO",
#                 "Environment": row.get("Environment") or "",
#                 "Test_Phase": row.get("Test_Phase") or row.get("Test Phase") or "",
#             })

#         import re as _re

#         def _text_tc_id(row: dict[str, Any]) -> str:
#             for field_name in ("Test_Case_ID", "Test Case ID", "summary", "Summary", "description", "Description"):
#                 value = row.get(field_name)
#                 if value is None:
#                     continue
#                 match = _re.search(r"\bTC-\d+\b", str(value), _re.IGNORECASE)
#                 if match:
#                     return match.group(0).upper()
#             return ""

#         normalized_defects: list[dict[str, Any]] = []
#         for row in defects:
#             normalized = dict(row)
#             normalized["Test_Case_ID"] = normalized.get("Test_Case_ID") or normalized.get("Test Case ID") or _text_tc_id(normalized)
#             if not normalized.get("Confirmed"):
#                 status_value = str(normalized.get("Status") or normalized.get("status") or "CONFIRMED").strip().upper()
#                 if status_value not in {"REJECTED", "DUPLICATE", "INVALID", "CANCELLED", "NOT_A_DEFECT"}:
#                     normalized["Confirmed"] = "YES"
#             normalized_defects.append(normalized)

#         normalized_flaky: list[dict[str, Any]] = []
#         for row in flaky_tests:
#             normalized = dict(row)
#             normalized["Test_Case_ID"] = normalized.get("Test_Case_ID") or normalized.get("Test Case ID") or _text_tc_id(normalized)
#             normalized_flaky.append(normalized)

#         regulatory_tests = [
#             r for r in test_cases
#             if str(
#                 r.get("Regulatory_Flag")
#                 or r.get("Regulatory Flag")
#                 or r.get("Regulatory_Status")
#                 or r.get("Regulatory Status")
#                 or ""
#             ).strip().upper() in {"YES", "Y", "TRUE", "1", "ACTIVE", "REGULATORY"}
#         ]

#         self._emit_stage(
#             "orchestrator", "running",
#             f"Release scope resolved — {len(test_cases)} test cases in scope.",
#             agent_name="Master Orchestrator",
#         )

#         return {
#             "releases": matching_releases,
#             "modules": modules,
#             "epics": epics,
#             "stories": stories,
#             "requirements": requirements,
#             "rtm": rtm,
#             "test_cases": test_cases,
#             "release_scope": release_scope,
#             "dependencies": dependencies,
#             "out_of_scope": [],
#             "executions": normalized_executions,
#             "defects": normalized_defects,
#             "flaky_tests": normalized_flaky,
#             "policies": policies,
#             "regulatory_tests": regulatory_tests,
#             "release_rules": release_rules,
#         }

#     def _build_module_dependencies(
#         self,
#         modules: list[dict[str, Any]],
#         issue_by_key: dict[str, dict[str, Any]],
#     ) -> list[dict[str, Any]]:
#         """
#         Build downstream Module-to-Module dependencies from Jira issue links.

#         Business rule:

#             A --blocks--> B

#         is considered a downstream dependency only when the relationship is
#         *one-way*. If Jira also contains:

#             B --blocks--> A

#         then the pair is bidirectional/circular and MUST NOT be treated as a
#         downstream dependency in either direction.

#         Therefore:

#             A -> B only       => keep A -> B as downstream
#             A -> B and B -> A => exclude both directions
#             B -> A only       => keep B -> A as downstream

#         The dependent module does not need to be in the release scope. It only
#         needs to resolve to a real Jira Module. This allows a changed MOD-104
#         to propagate to downstream MOD-109.
#         """

#         def resolve_module_id(
#             issue_key: str,
#             row: dict[str, Any] | None = None,
#             link_issue: dict[str, Any] | None = None,
#         ) -> str:
#             """Resolve a Module ID from normalized Jira data, then summary."""
#             candidates: list[Any] = []

#             if row:
#                 candidates.extend(
#                     [
#                         row.get("Module_ID"),
#                         row.get("Module ID"),
#                         row.get("work_item_id"),
#                         row.get("summary"),
#                     ]
#                 )

#             if link_issue:
#                 link_fields = link_issue.get("fields") or {}
#                 if isinstance(link_fields, dict):
#                     candidates.extend(
#                         [
#                             link_fields.get("Module_ID"),
#                             link_fields.get("Module ID"),
#                             link_fields.get("summary"),
#                         ]
#                     )
#                 candidates.extend(
#                     [
#                         link_issue.get("summary"),
#                         link_issue.get("key"),
#                     ]
#                 )

#             candidates.append(issue_key)

#             for value in candidates:
#                 text = str(value or "").strip()
#                 if not text:
#                     continue

#                 match = re.search(
#                     r"\bMOD-\d+\b",
#                     text,
#                     re.IGNORECASE,
#                 )
#                 if match:
#                     return match.group(0).upper()

#             return ""

#         module_keys: dict[str, str] = {}
#         for row in modules:
#             jira_key = str(row.get("issue_key") or "").strip()
#             if not jira_key:
#                 continue

#             module_id = resolve_module_id(
#                 jira_key,
#                 row=row,
#             )
#             if module_id:
#                 module_keys[jira_key] = module_id

#         known_module_ids = set(module_keys.values())

#         # First collect ALL directed BLOCKS edges. Do not immediately add them
#         # to the downstream result because we must first detect reverse edges.
#         directed_edges: dict[tuple[str, str], dict[str, Any]] = {}

#         for module in modules:
#             current_key = str(
#                 module.get("issue_key") or ""
#             ).strip()
#             if not current_key:
#                 continue

#             current_module_id = module_keys.get(
#                 current_key,
#             ) or resolve_module_id(
#                 current_key,
#                 row=module,
#             )

#             if not current_module_id:
#                 continue

#             links = (
#                 module.get("Issue_Links")
#                 or module.get("issuelinks")
#                 or []
#             )
#             if not isinstance(links, list):
#                 continue

#             for link in links:
#                 if not isinstance(link, dict):
#                     continue

#                 link_type = link.get("type") or {}
#                 if not isinstance(link_type, dict):
#                     continue

#                 outward_desc = self._normalize_key(
#                     link_type.get("outward") or ""
#                 )
#                 inward_desc = self._normalize_key(
#                     link_type.get("inward") or ""
#                 )

#                 outward_issue = link.get("outwardIssue") or {}
#                 inward_issue = link.get("inwardIssue") or {}

#                 outward_key = str(
#                     outward_issue.get("key") or ""
#                 ).strip()
#                 inward_key = str(
#                     inward_issue.get("key") or ""
#                 ).strip()

#                 source_key = ""
#                 dependent_key = ""
#                 source_issue_payload: dict[str, Any] | None = None
#                 dependent_issue_payload: dict[str, Any] | None = None

#                 # A --blocks--> B
#                 if (
#                     outward_key
#                     and outward_key != current_key
#                     and "BLOCKS" in outward_desc
#                 ):
#                     source_key = current_key
#                     dependent_key = outward_key
#                     source_issue_payload = issue_by_key.get(
#                         current_key,
#                         module,
#                     )
#                     dependent_issue_payload = outward_issue

#                 # B --blocks--> A, observed while inspecting A.
#                 elif (
#                     inward_key
#                     and inward_key != current_key
#                     and "BLOCKED_BY" in inward_desc
#                 ):
#                     source_key = inward_key
#                     dependent_key = current_key
#                     source_issue_payload = inward_issue
#                     dependent_issue_payload = issue_by_key.get(
#                         current_key,
#                         module,
#                     )

#                 if not source_key or not dependent_key:
#                     continue

#                 source_row = issue_by_key.get(source_key)
#                 dependent_row = issue_by_key.get(dependent_key)

#                 source_module_id = resolve_module_id(
#                     source_key,
#                     row=source_row,
#                     link_issue=source_issue_payload,
#                 )
#                 dependent_module_id = resolve_module_id(
#                     dependent_key,
#                     row=dependent_row,
#                     link_issue=dependent_issue_payload,
#                 )

#                 # Final Jira lookup if a dependent row was not present in the
#                 # normalized project snapshot.
#                 if not dependent_module_id and self.jira_client:
#                     try:
#                         hydrated = self.jira_client.get_issue(
#                             dependent_key,
#                             [
#                                 "summary",
#                                 "issuetype",
#                             ],
#                         )
#                     except Exception:
#                         hydrated = {}

#                     dependent_module_id = resolve_module_id(
#                         dependent_key,
#                         row=(
#                             hydrated.get("fields", {})
#                             if isinstance(hydrated, dict)
#                             else None
#                         ),
#                         link_issue=hydrated,
#                     )

#                 if not source_module_id or not dependent_module_id:
#                     continue

#                 # Source must be a known Module. The dependent module may be
#                 # outside direct release scope but must resolve to MOD-xxxx.
#                 if source_module_id not in known_module_ids:
#                     continue

#                 # Dependent/downstream modules may be outside direct release
#                 # scope; they must still participate when Jira resolves them.

#                 if source_module_id == dependent_module_id:
#                     continue

#                 signature = (
#                     source_module_id,
#                     dependent_module_id,
#                 )

#                 # Preserve the first normalized record for this direction.
#                 if signature not in directed_edges:
#                     directed_edges[signature] = {
#                         "Source_Module_ID": source_module_id,
#                         "Dependent_Module_ID": dependent_module_id,
#                         "Dependency_Type": "BLOCKS",
#                         "Description": (
#                             f"{source_module_id} blocks "
#                             f"{dependent_module_id}"
#                         ),
#                     }

#         # A pair is a valid downstream dependency ONLY when it is one-way.
#         # Reciprocal BLOCKS relationships are treated as bidirectional/circular
#         # and are excluded in both directions.
#         dependencies: list[dict[str, Any]] = []
#         for (source_module_id, dependent_module_id), dependency in directed_edges.items():
#             reverse_signature = (
#                 dependent_module_id,
#                 source_module_id,
#             )

#             if reverse_signature in directed_edges:
#                 continue

#             dependencies.append(dependency)

#         dependencies.sort(
#             key=lambda row: (
#                 str(row.get("Source_Module_ID") or ""),
#                 str(row.get("Dependent_Module_ID") or ""),
#             )
#         )

#         return dependencies

#     def _fetch_jira_issues(
#         self,
#         jql: str,
#         fields: list[str],
#     ) -> list[dict[str, Any]]:
#         """Fetch Jira issues and surface MCP/Jira errors."""
#         if not self.jira_client:
#             raise RuntimeError("MCP Jira client is not configured.")

#         try:
#             issues = self.jira_client.search(jql, fields)
#         except Exception as exc:
#             raise RuntimeError(
#                 f"MCP/Jira search failed. JQL={jql!r}; "
#                 f"Error={type(exc).__name__}: {exc}"
#             ) from exc

#         if not isinstance(issues, list):
#             raise TypeError(
#                 f"MCP/Jira search returned {type(issues).__name__}; expected list."
#             )

#         return issues

#     def _row_identity_tokens(
#         self,
#         row: dict[str, Any],
#     ) -> set[str]:
#         """Build normalized identity/release-scope tokens for a Jira row."""

#         token_fields = (
#             "issue_key",
#             "work_item_id",
#             "Epic_ID",
#             "User_Story_ID",
#             "Requirement_ID",
#             "Epic ID",
#             "Story_ID",
#             "User Story ID",
#             "Requirement ID",
#             "parent_key",
#             "Test_Case_ID",
#             "Test Case ID",
#             "Release_ID",
#             "Release ID",
#         )

#         tokens: set[str] = set()
#         for field_name in token_fields:
#             value = row.get(field_name)
#             if value is None:
#                 continue
#             if isinstance(value, (list, tuple, set)):
#                 values = value
#             else:
#                 values = (value,)
#             for item in values:
#                 normalized = self._normalize_key(item)
#                 if normalized:
#                     tokens.add(normalized)

#         labels = row.get("labels") or []
#         if isinstance(labels, (list, tuple, set)):
#             label_values = labels
#         else:
#             label_values = (labels,)
#         for label in label_values:
#             normalized = self._normalize_key(label)
#             if normalized:
#                 tokens.add(normalized)

#         # Fix Versions may also be used as release-scope metadata.
#         for version in row.get("Fix_Versions") or row.get("fixVersions") or []:
#             if isinstance(version, dict):
#                 version_name = version.get("name") or version.get("value") or ""
#             else:
#                 version_name = version
#             normalized = self._normalize_key(version_name)
#             if normalized:
#                 tokens.add(normalized)

#         return tokens

#     def _row_belongs_to_release(
#         self,
#         row: dict[str, Any],
#         release_scope_tokens: set[str],
#     ) -> bool:
#         """
#         Determine whether a row is part of the current release scope.

#         For epics / stories / requirements this is straightforward because the
#         rows themselves are loaded from the release-scoped Jira query.
#         For test cases we require a relationship to one of the release-scoped
#         identifiers so reusable unlabeled tests can still be included.
#         """

#         if not release_scope_tokens:
#             return True

#         row_tokens = self._row_identity_tokens(row)
#         if row_tokens & release_scope_tokens:
#             return True

#         parent_key = self._normalize_key(row.get("parent_key"))
#         if parent_key and parent_key in release_scope_tokens:
#             return True

#         return False

#     def _resolve_jira_field_ids(
#         self,
#     ) -> dict[str, str]:
#         """
#         Resolve Jira custom field IDs dynamically by semantic field name.

#         Jira can contain duplicate custom fields with the same display name.
#         For example, this project has two "Release Type" fields. In that
#         situation, select the candidate that is actually populated on the
#         relevant Jira work type instead of relying on dictionary overwrite
#         order or hard-coded customfield IDs.
#         """
#         if self._jira_field_ids is not None:
#             return self._jira_field_ids

#         field_ids: dict[str, str] = {
#             "epic_id": "",
#             "story_id": "",
#             "module_id": "",
#             "change_status": "",
#             "requirement_id": "",
#             "test_case_id": "",
#             "test_status": "",
#             "business_priority": "",
#             "automation_status": "",
#             "execution_minutes": "",
#             "regulatory_flag": "",
#             "requirement_description": "",
#             "test_name": "",
#             "story_name": "",
#             "epic_name": "",
#             "release_id": "",
#             "execution_id": "",
#             "execution_date": "",
#             "execution_status": "",
#             "failure_type": "",
#             "is_flaky": "",
#             "environment": "",
#             "test_phase": "",
#             "defect_id": "",
#             "severity": "",
#             "confirmed": "",
#             "production_escape": "",
#             "detected_date": "",
#             "mapping_type": "",
#             "mapping_status": "",
#             "release_type": "",
#             "rule_name": "",
#             "rule_value": "",
#             "mandatory_reason": "",
#             "policy_reference": "",
#             "policy_status": "",
#             "release_name": "",
#             "release_status": "",
#             "scope_freeze_date": "",
#             "planned_release_date": "",
#             "module_name": "",
#             "regulatory_score": "",
#             "financial_score": "",
#             "customer_score": "",
#             "sla_score": "",
#             "incident_score": "",
#             "change_type": "",
#             "scope_status": "",
#             "change_description": "",
#             "flaky_status": "",
#             "flaky_total_runs": "",
#             "flaky_failures": "",
#             "flaky_rate": "",
#             "remediation_action": "",
#             "minimum_coverage": "",
#             "tier_max_exclusion": "",
#             "overall_max_exclusion": "",
#             "over_cap_approval_role": "",
#             "rule_status": "",
#             "rule_type": "",
#         }

#         if not self.jira_client:
#             self._jira_field_ids = field_ids
#             return field_ids

#         try:
#             all_fields = self.jira_client.list_fields()
#         except Exception:
#             all_fields = []

#         # Keep every field ID for a semantic name instead of overwriting a
#         # duplicate name with the last ID returned by Jira.
#         lookup: dict[str, list[str]] = {}
#         for field in all_fields:
#             field_id = str(
#                 field.get("id")
#                 or field.get("key")
#                 or ""
#             ).strip()
#             if not field_id:
#                 continue

#             names: list[str] = []
#             raw_name = field.get("name")
#             if raw_name:
#                 names.append(str(raw_name))

#             clause_names = field.get("clauseNames") or []
#             if isinstance(clause_names, list):
#                 names.extend(
#                     str(clause_name)
#                     for clause_name in clause_names
#                     if clause_name
#                 )

#             for name in names:
#                 key = self._normalize_key(name)
#                 if not key:
#                     continue
#                 ids = lookup.setdefault(key, [])
#                 if field_id not in ids:
#                     ids.append(field_id)

#         # Work-type probes used only when a semantic name maps to multiple
#         # custom fields. These are Jira issue-type names, not custom field IDs.
#         probe_types: dict[str, tuple[str, ...]] = {
#             "release": ("Release",),
#             "module": ("Module",),
#             "test_case": ("Test Case", "Test"),
#             "requirement": ("Requirement", "Requirment"),
#             "execution": ("Test Execution", "Execution"),
#             "defect": ("Bug", "Defect"),
#             "policy": ("Risk Policy", "Policy"),
#             "release_rule": ("Release Rule", "Rule"),
#             "flaky": ("Flaky Test", "Flaky Test Record", "Flaky_Test"),
#         }

#         probe_cache: dict[str, list[dict[str, Any]]] = {}

#         def probe_issue_type(type_names: tuple[str, ...]) -> list[dict[str, Any]]:
#             cache_key = "|".join(type_names)
#             if cache_key in probe_cache:
#                 return probe_cache[cache_key]

#             issues: list[dict[str, Any]] = []
#             for type_name in type_names:
#                 jql = (
#                     f'project = "{self.jira_project_key}" '
#                     f'AND issuetype = "{type_name}" ORDER BY key ASC'
#                 )
#                 try:
#                     candidate_issues = self.jira_client.search(
#                         jql,
#                         ["key", "summary"],
#                     )
#                 except Exception:
#                     candidate_issues = []

#                 if candidate_issues:
#                     issues.extend(candidate_issues)

#             # Preserve order and remove duplicate Jira keys.
#             seen: set[str] = set()
#             unique: list[dict[str, Any]] = []
#             for issue in issues:
#                 key = str(issue.get("key") or "").strip()
#                 if key and key in seen:
#                     continue
#                 if key:
#                     seen.add(key)
#                 unique.append(issue)

#             probe_cache[cache_key] = unique[:20]
#             return probe_cache[cache_key]

#         def _candidate_values(
#             candidate_ids: list[str],
#             issue_types: tuple[str, ...] | None,
#         ) -> dict[str, int]:
#             """Count populated values for candidate fields on probe issues."""
#             scores = {candidate_id: 0 for candidate_id in candidate_ids}
#             if len(candidate_ids) <= 1 or not issue_types:
#                 return scores

#             probe_issues = probe_issue_type(issue_types)
#             if not probe_issues:
#                 return scores

#             # Fetch the candidate fields directly from the probe issues.
#             for issue in probe_issues:
#                 issue_key = str(issue.get("key") or "").strip()
#                 if not issue_key:
#                     continue
#                 try:
#                     hydrated = self.jira_client.get_issue(
#                         issue_key,
#                         candidate_ids,
#                     )
#                 except Exception:
#                     continue

#                 fields = hydrated.get("fields", {}) if isinstance(hydrated, dict) else {}
#                 if not isinstance(fields, dict):
#                     continue

#                 for candidate_id in candidate_ids:
#                     value = fields.get(candidate_id)
#                     if value is None or value == "":
#                         continue
#                     if isinstance(value, (list, dict)) and not value:
#                         continue
#                     # Jira option objects are populated if they contain a
#                     # value/name/id. Any non-empty scalar is populated too.
#                     if isinstance(value, dict) and not any(
#                         value.get(k) for k in ("value", "name", "id", "key")
#                     ):
#                         continue
#                     scores[candidate_id] += 1

#             return scores

#         semantic_probe_group: dict[str, tuple[str, ...] | None] = {
#             "release_id": probe_types["release"],
#             "release_type": probe_types["release"],
#             "module_id": probe_types["module"],
#             "test_case_id": probe_types["test_case"],
#             "test_status": probe_types["test_case"],
#             "automation_status": probe_types["test_case"],
#             "execution_minutes": probe_types["test_case"],
#             "regulatory_flag": probe_types["test_case"],
#             "requirement_id": probe_types["requirement"],
#             "requirement_description": probe_types["requirement"],
#             "execution_id": probe_types["execution"],
#             "execution_date": probe_types["execution"],
#             "execution_status": probe_types["execution"],
#             "failure_type": probe_types["execution"],
#             "is_flaky": probe_types["execution"],
#             "environment": probe_types["execution"],
#             "test_phase": probe_types["execution"],
#             "defect_id": probe_types["defect"],
#             "severity": probe_types["defect"],
#             "confirmed": probe_types["defect"],
#             "production_escape": probe_types["defect"],
#             "detected_date": probe_types["defect"],
#             "release_type": probe_types["release"],
#             "rule_name": probe_types["release_rule"],
#             "rule_value": probe_types["release_rule"],
#             "mandatory_reason": probe_types["policy"],
#             "policy_reference": probe_types["policy"],
#             "policy_status": probe_types["policy"],
#             "minimum_coverage": probe_types["policy"],
#             "tier_max_exclusion": probe_types["policy"],
#             "overall_max_exclusion": probe_types["policy"],
#             "over_cap_approval_role": probe_types["policy"],
#             "rule_status": probe_types["release_rule"],
#             "rule_type": probe_types["release_rule"],
#             "release_name": probe_types["release"],
#             "release_status": probe_types["release"],
#             "scope_freeze_date": probe_types["release"],
#             "planned_release_date": probe_types["release"],
#             "module_name": probe_types["module"],
#             "regulatory_score": probe_types["module"],
#             "financial_score": probe_types["module"],
#             "customer_score": probe_types["module"],
#             "sla_score": probe_types["module"],
#             "incident_score": probe_types["module"],
#             "change_type": None,
#             "scope_status": None,
#             "change_description": None,
#             "flaky_status": probe_types["flaky"],
#             "flaky_total_runs": probe_types["flaky"],
#             "flaky_failures": probe_types["flaky"],
#             "flaky_rate": probe_types["flaky"],
#             "remediation_action": probe_types["flaky"],
#         }

#         def find(field_key: str, *candidates: str) -> str:
#             candidate_ids: list[str] = []
#             seen_ids: set[str] = set()
#             for candidate in candidates:
#                 ids = lookup.get(self._normalize_key(candidate), [])
#                 for candidate_id in ids:
#                     if candidate_id not in seen_ids:
#                         seen_ids.add(candidate_id)
#                         candidate_ids.append(candidate_id)

#             if not candidate_ids:
#                 return ""
#             if len(candidate_ids) == 1:
#                 return candidate_ids[0]

#             scores = _candidate_values(
#                 candidate_ids,
#                 semantic_probe_group.get(field_key),
#             )

#             # Highest populated score wins. If tied, preserve Jira's returned
#             # order instead of selecting a random duplicate.
#             best_id = candidate_ids[0]
#             best_score = scores.get(best_id, 0)
#             for candidate_id in candidate_ids[1:]:
#                 score = scores.get(candidate_id, 0)
#                 if score > best_score:
#                     best_id = candidate_id
#                     best_score = score

#             return best_id

#         field_ids["requirement_id"] = find(
#             "requirement_id",
#             "Requirement ID",
#             "RequirementId",
#             "Requirement_ID",
#             "Req ID",
#             "Req_ID",
#         )
#         field_ids["test_case_id"] = find(
#             "test_case_id",
#             "Test Case ID",
#             "TestCase ID",
#             "Test_Case_ID",
#             "TestCase_ID",
#             "TC ID",
#             "TC_ID",
#         )
#         field_ids["test_status"] = find("test_status", "Test Status", "Test_Status", "TestStatus")
#         field_ids["business_priority"] = find("business_priority", "Business Priority", "Business_Priority")
#         field_ids["automation_status"] = find("automation_status", "Automation Status", "Automation_Status")
#         field_ids["execution_minutes"] = find("execution_minutes", "Execution Minutes", "Execution_Minutes", "Duration Minutes", "Duration")
#         field_ids["regulatory_flag"] = find("regulatory_flag", "Regulatory Flag", "Regulatory_Flag")
#         field_ids["requirement_description"] = find("requirement_description", "Requirement Description", "Requirement_Description", "Description")
#         field_ids["test_name"] = find("test_name", "Test Name", "Test_Name")
#         field_ids["story_name"] = find("story_name", "Story Name", "User Story Name", "User_Story_Name")
#         field_ids["epic_name"] = find("epic_name", "Epic Name", "Epic_Name")
#         field_ids["release_id"] = find("release_id", "Release ID", "ReleaseId", "Release_ID")
#         field_ids["execution_id"] = find("execution_id", "Execution ID", "ExecutionId", "Execution_ID")
#         field_ids["execution_date"] = find("execution_date", "Execution Date", "ExecutionDate", "Execution_Date")
#         field_ids["execution_status"] = find("execution_status", "Execution Status", "ExecutionStatus", "Execution_Status")
#         field_ids["failure_type"] = find("failure_type", "Failure Type", "FailureType", "Failure_Type")
#         field_ids["is_flaky"] = find("is_flaky", "Is Flaky", "IsFlaky", "Is_Flaky")
#         field_ids["environment"] = find("environment", "Environment")
#         field_ids["test_phase"] = find("test_phase", "Test Phase", "TestPhase", "Test_Phase")
#         field_ids["defect_id"] = find("defect_id", "Defect ID", "DefectId", "Defect_ID")
#         field_ids["severity"] = find("severity", "Severity")
#         field_ids["confirmed"] = find("confirmed", "Confirmed")
#         field_ids["production_escape"] = find("production_escape", "Production Escape", "Production_Escape")
#         field_ids["detected_date"] = find("detected_date", "Detected Date", "Detected_Date")
#         field_ids["mapping_type"] = find("mapping_type", "Mapping Type", "Mapping_Type")
#         field_ids["mapping_status"] = find("mapping_status", "Mapping Status", "Mapping_Status")
#         field_ids["release_type"] = find("release_type", "Release Type", "Release_Type")
#         field_ids["rule_name"] = find("rule_name", "Rule Name", "Rule_Name")
#         field_ids["rule_value"] = find("rule_value", "Rule Value", "Rule_Value")
#         field_ids["mandatory_reason"] = find("mandatory_reason", "Mandatory Reason", "Mandatory_Reason")
#         field_ids["policy_reference"] = find("policy_reference", "Policy Reference", "Policy_Reference")
#         field_ids["policy_status"] = find(
#             "policy_status",
#             "Policy Status",
#             "Policy_Status",
#             "PolicyStatus",
#         )
#         field_ids["minimum_coverage"] = find(
#             "minimum_coverage",
#             "Minimum Coverage",
#             "Minimum_Coverage",
#             "Min Coverage",
#             "Min_Coverage",
#         )
#         field_ids["tier_max_exclusion"] = find(
#             "tier_max_exclusion",
#             "Tier Max Exclusion",
#             "Tier_Max_Exclusion",
#         )
#         field_ids["overall_max_exclusion"] = find(
#             "overall_max_exclusion",
#             "Overall Max Exclusion",
#             "Overall_Max_Exclusion",
#         )
#         field_ids["over_cap_approval_role"] = find(
#             "over_cap_approval_role",
#             "Over Cap Approval Role",
#             "Over_Cap_Approval_Role",
#         )
#         field_ids["rule_status"] = find(
#             "rule_status",
#             "Rule Status",
#             "Rule_Status",
#         )
#         field_ids["rule_type"] = find(
#             "rule_type",
#             "Rule Type",
#             "Rule_Type",
#         )

#         field_ids["release_name"] = find(
#             "release_name",
#             "Release Name",
#             "Release_Name",
#         )
#         field_ids["release_status"] = find(
#             "release_status",
#             "Release Status",
#             "Release_Status",
#         )
#         field_ids["scope_freeze_date"] = find(
#             "scope_freeze_date",
#             "Scope Freeze Date",
#             "Scope_Freeze_Date",
#         )
#         field_ids["planned_release_date"] = find(
#             "planned_release_date",
#             "Planned Release Date",
#             "Planned_Release_Date",
#         )

#         field_ids["module_name"] = find(
#             "module_name",
#             "Module Name",
#             "Module_Name",
#         )
#         field_ids["regulatory_score"] = find(
#             "regulatory_score",
#             "Regulatory Score",
#             "Regulatory_Score",
#         )
#         field_ids["financial_score"] = find(
#             "financial_score",
#             "Financial Score",
#             "Financial_Score",
#         )
#         field_ids["customer_score"] = find(
#             "customer_score",
#             "Customer Score",
#             "Customer_Score",
#         )
#         field_ids["sla_score"] = find(
#             "sla_score",
#             "SLA Score",
#             "SLA_Score",
#         )
#         field_ids["incident_score"] = find(
#             "incident_score",
#             "Incident Score",
#             "Incident_Score",
#         )

#         field_ids["flaky_status"] = find(
#             "flaky_status",
#             "Flaky Status",
#             "Flaky_Status",
#         )
#         field_ids["flaky_total_runs"] = find(
#             "flaky_total_runs",
#             "Total Runs",
#             "Total_Runs",
#         )
#         field_ids["flaky_failures"] = find(
#             "flaky_failures",
#             "Flaky Failures",
#             "Flaky_Failures",
#         )
#         field_ids["flaky_rate"] = find(
#             "flaky_rate",
#             "Flaky Rate",
#             "Flaky_Rate",
#         )
#         field_ids["remediation_action"] = find(
#             "remediation_action",
#             "Remediation Action",
#             "Remediation_Action",
#         )

#         # Explicitly resolve the remaining hierarchy fields too. These names
#         # can also be duplicated between historical/custom fields.
#         field_ids["epic_id"] = find("epic_id", "Epic ID", "EpicId", "Epic_ID")
#         field_ids["story_id"] = find("story_id", "Story ID", "StoryId", "Story_ID", "User Story ID", "User_Story_ID")
#         field_ids["module_id"] = find("module_id", "Module ID", "ModuleId", "Module_ID")
#         field_ids["change_status"] = find("change_status", "Change Status", "ChangeStatus", "Change_Status")

#         self._jira_field_ids = field_ids
#         return field_ids

#     def _jira_issue_to_row(
#         self,
#         issue: dict[str, Any],
#         field_ids: dict[str, str],
#     ) -> dict[str, Any]:
#         """
#         Convert one Jira issue into a normalized row.
#         """

#         fields = issue.get(
#             "fields",
#             {},
#         )
#         if not isinstance(
#             fields,
#             dict,
#         ):
#             fields = {}

#         issue_key = str(
#             issue.get("key") or ""
#         ).strip()
#         issue_type = str(
#             (
#                 fields.get("issuetype", {}) or {}
#             ).get("name")
#             or ""
#         ).strip()
#         summary = str(
#             fields.get("summary")
#             or ""
#         ).strip()
#         description = fields.get(
#             "description",
#             "",
#         )
#         if description is None:
#             description = ""
#         status = str(
#             (
#                 fields.get("status", {}) or {}
#             ).get("name")
#             or ""
#         ).strip()
#         labels = fields.get(
#             "labels",
#             [],
#         )
#         if not isinstance(
#             labels,
#             list,
#         ):
#             labels = [labels]
#         parent = fields.get(
#             "parent",
#             {},
#         )
#         parent_key = str(
#             (
#                 parent or {}
#             ).get("key")
#             or ""
#         ).strip()

#         work_item_id = self._extract_work_item_id(
#             summary=summary,
#             issue_key=issue_key,
#         )

#         row: dict[str, Any] = {
#             "issue_key": issue_key,
#             "issue_type": issue_type,
#             "summary": summary,
#             "description": description,
#             "status": status,
#             "labels": labels,
#             "parent_key": parent_key,
#             "work_item_id": work_item_id,
#             "Epic_ID": self._field_text(fields, field_ids.get("epic_id")),
#             "User_Story_ID": self._field_text(fields, field_ids.get("story_id")),
#             "Requirement_ID": self._field_text(fields, field_ids.get("requirement_id")),
#             "Test_Case_ID": self._field_text(fields, field_ids.get("test_case_id")),
#             "Module_ID": self._field_text(fields, field_ids.get("module_id")),
#             "Change_Status": self._field_text(fields, field_ids.get("change_status")),
#             "Business_Priority": self._field_text(fields, field_ids.get("business_priority")),
#             "Test_Status": self._field_text(fields, field_ids.get("test_status")),
#             "Automation_Status": self._field_text(fields, field_ids.get("automation_status")),
#             "Execution_Minutes": self._field_text(fields, field_ids.get("execution_minutes")),
#             "Regulatory_Flag": self._field_text(fields, field_ids.get("regulatory_flag")),
#             "Requirement_Description": self._field_text(fields, field_ids.get("requirement_description")),
#             "Test_Name": self._field_text(fields, field_ids.get("test_name")),
#             "User_Story_Name": self._field_text(fields, field_ids.get("story_name")),
#             "Epic_Name": self._field_text(fields, field_ids.get("epic_name")),
#             "Release_ID": self._field_text(fields, field_ids.get("release_id")),
#             "Execution_ID": self._field_text(fields, field_ids.get("execution_id")),
#             "Execution_Date": self._field_text(fields, field_ids.get("execution_date")),
#             "Execution_Status": self._field_text(fields, field_ids.get("execution_status")),
#             "Failure_Type": self._field_text(fields, field_ids.get("failure_type")),
#             "Is_Flaky": self._field_text(fields, field_ids.get("is_flaky")),
#             "Environment": self._field_text(fields, field_ids.get("environment")),
#             "Test_Phase": self._field_text(fields, field_ids.get("test_phase")),
#             "Defect_ID": self._field_text(fields, field_ids.get("defect_id")),
#             "Severity": self._field_text(fields, field_ids.get("severity")),
#             "Confirmed": self._field_text(fields, field_ids.get("confirmed")),
#             "Production_Escape": self._field_text(fields, field_ids.get("production_escape")),
#             "Detected_Date": self._field_text(fields, field_ids.get("detected_date")),
#             "Mapping_Type": self._field_text(fields, field_ids.get("mapping_type")),
#             "Mapping_Status": self._field_text(fields, field_ids.get("mapping_status")),
#             "Release_Type": self._field_text(fields, field_ids.get("release_type")),
#             "Rule_Name": self._field_text(fields, field_ids.get("rule_name")),
#             "Rule_Value": self._field_text(fields, field_ids.get("rule_value")),
#             "Mandatory_Reason": self._field_text(fields, field_ids.get("mandatory_reason")),
#             "Policy_Reference": self._field_text(fields, field_ids.get("policy_reference")),
#             "Policy_Status": self._field_text(fields, field_ids.get("policy_status")),
#             "Release_Name": self._field_text(fields, field_ids.get("release_name")),
#             "Release_Status": self._field_text(fields, field_ids.get("release_status")),
#             "Scope_Freeze_Date": self._field_text(fields, field_ids.get("scope_freeze_date")),
#             "Planned_Release_Date": self._field_text(fields, field_ids.get("planned_release_date")),
#             "Module_Name": self._field_text(fields, field_ids.get("module_name")),
#             "Regulatory_Score": self._field_text(fields, field_ids.get("regulatory_score")),
#             "Financial_Score": self._field_text(fields, field_ids.get("financial_score")),
#             "Customer_Score": self._field_text(fields, field_ids.get("customer_score")),
#             "SLA_Score": self._field_text(fields, field_ids.get("sla_score")),
#             "Incident_Score": self._field_text(fields, field_ids.get("incident_score")),
#             "Change_Type": self._field_text(fields, field_ids.get("change_type")),
#             "Scope_Status": self._field_text(fields, field_ids.get("scope_status")),
#             "Change_Description": self._field_text(fields, field_ids.get("change_description")),
#             "Flaky_Status": self._field_text(fields, field_ids.get("flaky_status")),
#             "Total_Runs": self._field_text(fields, field_ids.get("flaky_total_runs")),
#             "Flaky_Failures": self._field_text(fields, field_ids.get("flaky_failures")),
#             "Flaky_Rate": self._field_text(fields, field_ids.get("flaky_rate")),
#             "Remediation_Action": self._field_text(fields, field_ids.get("remediation_action")),
#             "Minimum_Coverage": self._field_text(fields, field_ids.get("minimum_coverage")),
#             "Tier_Max_Exclusion": self._field_text(fields, field_ids.get("tier_max_exclusion")),
#             "Overall_Max_Exclusion": self._field_text(fields, field_ids.get("overall_max_exclusion")),
#             "Over_Cap_Approval_Role": self._field_text(fields, field_ids.get("over_cap_approval_role")),
#             "Rule_Status": self._field_text(fields, field_ids.get("rule_status")),
#             "Rule_Type": self._field_text(fields, field_ids.get("rule_type")),
#             "Issue_Links": fields.get("issuelinks", []),
#             "Fix_Versions": fields.get("fixVersions", []),
#         }

#         # Fill obvious name fields from the summary when a dedicated field is
#         # not available.
#         stripped_summary = self._strip_work_item_prefix(
#             summary
#         )
#         row["Epic_Name"] = row["Epic_Name"] or stripped_summary
#         row["User_Story_Name"] = row["User_Story_Name"] or stripped_summary
#         row["Requirement_Name"] = row.get("Requirement_Name") or stripped_summary
#         row["Test_Name"] = row["Test_Name"] or stripped_summary

#         # Convenience aliases used by the downstream tools.
#         row["Epic ID"] = row["Epic_ID"]
#         row["Story_ID"] = row["User_Story_ID"]
#         row["User Story ID"] = row["User_Story_ID"]
#         row["Requirement ID"] = row["Requirement_ID"]
#         row["Test Case ID"] = row["Test_Case_ID"]
#         row["Test Case Name"] = row["Test_Name"]
#         row["Module ID"] = row["Module_ID"]
#         row["Change Status"] = row["Change_Status"]
#         row["Business Priority"] = row["Business_Priority"]
#         row["Test Status"] = row["Test_Status"]
#         row["Automation Status"] = row["Automation_Status"]
#         row["Execution Minutes"] = row["Execution_Minutes"]
#         row["Regulatory Flag"] = row["Regulatory_Flag"]
#         row["Requirement Description"] = row["Requirement_Description"]
#         row["Test Name"] = row["Test_Name"]
#         row["Story Name"] = row["User_Story_Name"]
#         row["Epic Name"] = row["Epic_Name"]
#         row["Release ID"] = row.get("Release_ID", "")
#         row["Execution ID"] = row.get("Execution_ID", "")
#         row["Execution Status"] = row.get("Execution_Status", "")
#         row["Failure Type"] = row.get("Failure_Type", "")
#         row["Is Flaky"] = row.get("Is_Flaky", "")
#         row["Environment"] = row.get("Environment", "")
#         row["Test Phase"] = row.get("Test_Phase", "")
#         row["Defect ID"] = row.get("Defect_ID", "")
#         row["Severity"] = row.get("Severity", "")
#         row["Confirmed"] = row.get("Confirmed", "")
#         row["Production Escape"] = row.get("Production_Escape", "")
#         row["Detected Date"] = row.get("Detected_Date", "")
#         row["Mapping Type"] = row.get("Mapping_Type", "")
#         row["Mapping Status"] = row.get("Mapping_Status", "")
#         row["Release Type"] = row.get("Release_Type", "")
#         row["Rule Name"] = row.get("Rule_Name", "")
#         row["Rule Value"] = row.get("Rule_Value", "")
#         row["Mandatory Reason"] = row.get("Mandatory_Reason", "")
#         row["Policy Reference"] = row.get("Policy_Reference", "")
#         row["Policy Status"] = row.get("Policy_Status", "")
#         row["Release Name"] = row.get("Release_Name", "")
#         row["Release Status"] = row.get("Release_Status", "")
#         row["Scope Freeze Date"] = row.get("Scope_Freeze_Date", "")
#         row["Planned Release Date"] = row.get("Planned_Release_Date", "")
#         row["Module Name"] = row.get("Module_Name", "")
#         row["Regulatory Score"] = row.get("Regulatory_Score", "")
#         row["Financial Score"] = row.get("Financial_Score", "")
#         row["Customer Score"] = row.get("Customer_Score", "")
#         row["SLA Score"] = row.get("SLA_Score", "")
#         row["Incident Score"] = row.get("Incident_Score", "")
#         row["Change Type"] = row.get("Change_Type", "")
#         row["Scope Status"] = row.get("Scope_Status", "")
#         row["Change Description"] = row.get("Change_Description", "")
#         row["Flaky Status"] = row.get("Flaky_Status", "")
#         row["Total Runs"] = row.get("Total_Runs", "")
#         row["Flaky Failures"] = row.get("Flaky_Failures", "")
#         row["Flaky Rate"] = row.get("Flaky_Rate", "")
#         row["Remediation Action"] = row.get("Remediation_Action", "")
#         row["Minimum Coverage"] = row.get("Minimum_Coverage", "")
#         row["Tier Max Exclusion"] = row.get("Tier_Max_Exclusion", "")
#         row["Overall Max Exclusion"] = row.get("Overall_Max_Exclusion", "")
#         row["Over Cap Approval Role"] = row.get("Over_Cap_Approval_Role", "")
#         row["Rule Status"] = row.get("Rule_Status", "")
#         row["Rule Type"] = row.get("Rule_Type", "")

#         if (
#             self._normalize_key(issue_type) in {"TEST_CASE", "TEST", "SUBTASK", "SUB_TASK"}
#             or str(row.get("work_item_id") or "").upper().startswith("TC-")
#         ) and not row["Test_Status"]:
#             row["Test_Status"] = "ACTIVE"
#             row["Test Status"] = "ACTIVE"

#         # Release Type is a Jira custom field. If field metadata discovery is
#         # unavailable, still recover a configured release type from the raw
#         # field payload without hard-coding a customfield_XXXXX ID.
#         if not row["Release_Type"] and self._normalize_key(issue_type) == "RELEASE":
#             inferred_release_type = self._infer_release_type_from_fields(fields)
#             if inferred_release_type:
#                 row["Release_Type"] = inferred_release_type
#                 row["Release Type"] = inferred_release_type

#         if not row["Release_ID"] and row.get("work_item_id", "").upper().startswith("REL-"):
#             row["Release_ID"] = row["work_item_id"]

#         row["category"] = self._jira_issue_category(
#             row
#         )

#         return row

#     def _infer_release_type_from_fields(
#         self,
#         fields: dict[str, Any],
#     ) -> str:
#         """Infer MAJOR/MINOR/HOTFIX from raw Jira Release fields safely."""
#         allowed = {"MAJOR", "MINOR", "HOTFIX"}

#         def walk(value: Any) -> str:
#             if isinstance(value, dict):
#                 for key in ("value", "name", "key"):
#                     candidate = value.get(key)
#                     normalized = self._normalize_key(candidate)
#                     if normalized in allowed:
#                         return str(candidate).strip().upper()
#                 for nested in value.values():
#                     found = walk(nested)
#                     if found:
#                         return found
#                 return ""

#             if isinstance(value, (list, tuple, set)):
#                 for nested in value:
#                     found = walk(nested)
#                     if found:
#                         return found
#                 return ""

#             normalized = self._normalize_key(value)
#             return str(value).strip().upper() if normalized in allowed else ""

#         for field_id, value in fields.items():
#             if not str(field_id).startswith("customfield_"):
#                 continue
#             found = walk(value)
#             if found:
#                 return found

#         return ""

#     def _enrich_jira_row_with_hierarchy(
#         self,
#         row: dict[str, Any],
#         issue_by_key: dict[str, dict[str, Any]],
#     ) -> None:
#         """
#         Propagate the complete Jira parent hierarchy into one normalized row.

#         Project model:
#             Epic -> Story -> Test Case (subtask)

#         Requirements are not Jira parents in this project. A Test Case carries
#         Requirement_ID directly, so that field is preserved as the source of
#         truth for RTM. Parent traversal is used only for Epic/Story/Module and
#         other hierarchy metadata that can be inherited safely.
#         """

#         current = row
#         visited: set[str] = set()
#         depth = 0

#         while depth < 10:
#             parent_key = str(current.get("parent_key") or "").strip()
#             if not parent_key or parent_key in visited:
#                 break
#             visited.add(parent_key)

#             parent = issue_by_key.get(parent_key)
#             if not parent:
#                 break

#             # Inherit fields only when the child does not already have the
#             # value. Direct fields on Test Cases therefore remain authoritative.
#             for field_name in (
#                 "Epic_ID",
#                 "User_Story_ID",
#                 "Module_ID",
#                 "Change_Status",
#             ):
#                 if not row.get(field_name) and parent.get(field_name):
#                     row[field_name] = parent.get(field_name)

#             # Story parent -> Epic.
#             if self._normalize_key(parent.get("issue_type")) == "EPIC":
#                 row["Epic_ID"] = (
#                     row.get("Epic_ID")
#                     or parent.get("Epic_ID")
#                     or parent.get("work_item_id")
#                     or parent_key
#                 )

#             # Test Case / subtask parent -> Story.
#             if self._normalize_key(parent.get("issue_type")) in {
#                 "STORY",
#                 "TASK",
#             } or str(parent.get("work_item_id") or "").upper().startswith("US-"):
#                 row["User_Story_ID"] = (
#                     row.get("User_Story_ID")
#                     or parent.get("User_Story_ID")
#                     or parent.get("work_item_id")
#                     or parent_key
#                 )
#                 row["Epic_ID"] = (
#                     row.get("Epic_ID")
#                     or parent.get("Epic_ID")
#                 )

#             # Continue walking so TC -> Story -> Epic is fully inherited.
#             current = parent
#             depth += 1

#         # Keep direct Requirement_ID untouched. Requirements are a logical
#         # relationship from the Test Case, not a Jira parent in this project.
#         row["Story_ID"] = row.get("User_Story_ID", "")
#         row["User Story ID"] = row.get("User_Story_ID", "")
#         row["Requirement ID"] = row.get("Requirement_ID", "")
#         row["Epic ID"] = row.get("Epic_ID", "")
#         row["Module ID"] = row.get("Module_ID", "")
#         row["Change Status"] = row.get("Change_Status", "")

#     def _jira_issue_category(
#         self,
#         row: dict[str, Any],
#     ) -> str:
#         """Classify Jira issues into the logical blocks used by the agents."""

#         work_item_id = str(row.get("work_item_id") or "").strip().upper()
#         issue_type = self._normalize_key(row.get("issue_type"))

#         if issue_type in {"TEST_EXECUTION", "EXECUTION"} or work_item_id.startswith("EX-"):
#             return "executions"
#         if issue_type in {"FLAKY_TEST_RECORD", "FLAKY_TEST"} or work_item_id.startswith("FLAKY-"):
#             return "flaky_tests"
#         if issue_type in {"BUG", "DEFECT"} or work_item_id.startswith("DEF-"):
#             return "defects"
#         if issue_type == "MODULE" or work_item_id.startswith("MOD-"):
#             return "modules"
#         if issue_type == "RELEASE" or work_item_id.startswith("REL-"):
#             return "releases"
#         if issue_type in {"RISK_POLICY", "POLICY"} or work_item_id.startswith("POL-"):
#             return "policies"
#         if issue_type in {"RELEASE_RULE", "RULE"} or work_item_id.startswith("RULE-"):
#             return "release_rules"

#         # Test Case issues are subtasks in this project. Check this before the
#         # requirement fallback because Test Cases also carry Requirement_ID.
#         if (
#             work_item_id.startswith("TC-")
#             or row.get("Test_Case_ID")
#             or row.get("Test_Status")
#             or row.get("Automation_Status")
#             or issue_type in {"SUBTASK", "SUB_TASK", "TEST", "TEST_CASE"}
#         ):
#             return "test_cases"

#         if issue_type == "EPIC" or work_item_id.startswith("EP-"):
#             return "epics"
#         if issue_type == "STORY" or work_item_id.startswith("US-"):
#             return "stories"

#         # Jira work type in this project is literally spelled "Requirment".
#         if (
#             work_item_id.startswith("REQ-")
#             or row.get("Requirement_ID")
#             or row.get("Business_Priority")
#             or issue_type in {"REQUIREMENT", "REQUIRMENT"}
#         ):
#             return "requirements"

#         if row.get("Requirement_ID"):
#             return "requirements"
#         if row.get("User_Story_ID"):
#             return "stories"
#         return "epics"

#     def _extract_work_item_id(
#         self,
#         summary: str,
#         issue_key: str,
#     ) -> str:
#         match = re.search(
#             r"\[\s*([A-Za-z]{2,10}-\d+(?:\.\d+)?)\s*\]",
#             summary or "",
#         )
#         if match:
#             return match.group(1).strip()
#         return issue_key

#     def _strip_work_item_prefix(
#         self,
#         summary: str,
#     ) -> str:
#         cleaned = re.sub(
#             r"^\s*\[[^\]]+\]\s*",
#             "",
#             summary or "",
#         ).strip()
#         return cleaned or (summary or "").strip()

#     def _field_text(
#         self,
#         fields_or_value: dict[str, Any] | Any,
#         field_id: str | None = None,
#     ) -> str:
#         """
#         Convert Jira field values into normalized text.

#         Supports both ``_field_text(fields, field_id)`` and
#         ``_field_text(value)``. Jira custom fields may return strings,
#         option dictionaries, lists of options, or scalar values.
#         """
#         value = (
#             fields_or_value.get(field_id, "")
#             if field_id is not None and isinstance(fields_or_value, dict)
#             else fields_or_value
#         )
#         return self._normalize_jira_field_text(value)

#     @staticmethod
#     def _normalize_jira_field_text(value: Any) -> str:
#         """Normalize a raw Jira field value into stable text."""
#         if value is None:
#             return ""

#         if isinstance(value, str):
#             return value.strip()

#         if isinstance(value, dict):
#             for key in ("value", "name", "displayName", "key"):
#                 if value.get(key) is not None:
#                     return str(value[key]).strip()
#             return str(value).strip()

#         if isinstance(value, list):
#             values: list[str] = []
#             for item in value:
#                 if isinstance(item, dict):
#                     extracted: str | None = None
#                     for key in ("value", "name", "displayName", "key"):
#                         if item.get(key) is not None:
#                             extracted = str(item[key]).strip()
#                             break
#                     if extracted:
#                         values.append(extracted)
#                 elif item is not None:
#                     item_text = str(item).strip()
#                     if item_text:
#                         values.append(item_text)
#             return ", ".join(values)

#         return str(value).strip()

#     def _normalize_key(
#         self,
#         value: Any,
#     ) -> str:
#         return (
#             str(value or "")
#             .strip()
#             .upper()
#             .replace(" ", "_")
#             .replace("-", "_")
#         )


#     def _run_stage(
#         self,
#         state: PipelineState,
#         agent_name: str,
#         function: Callable[
#             [],
#             A2AResponse,
#         ],
#         stage_key: str | None = None,
#     ) -> A2AResponse:
#         """
#         Execute one pipeline stage and record its audit status.
#         """

#         started_at = datetime.now(
#             timezone.utc
#         )

#         if stage_key:
#             self._emit_stage(stage_key, "running", f"Running {agent_name}…", agent_name=agent_name)

#         try:
#             result = function()

#             if not isinstance(
#                 result,
#                 A2AResponse
#             ):
#                 raise TypeError(
#                     f"{agent_name} returned "
#                     f"{type(result).__name__}; "
#                     "expected A2AResponse."
#                 )

#             state.audit_log.append(
#                 AgentRun(
#                     agent=agent_name,
#                     status="COMPLETED",
#                     summary={
#                         "records": (
#                             self._result_size(
#                                 result.data
#                             )
#                         )
#                     },
#                     started_at=started_at,
#                     completed_at=datetime.now(
#                         timezone.utc
#                     ),
#                 )
#             )

#             if stage_key:
#                 self._emit_stage(stage_key, "finished", f"{agent_name} complete.", agent_name=agent_name)

#             return result

#         except Exception as exc:
#             state.audit_log.append(
#                 AgentRun(
#                     agent=agent_name,
#                     status="FAILED",
#                     summary={
#                         "error_type": (
#                             type(exc).__name__
#                         ),
#                         "error": str(exc),
#                     },
#                     started_at=started_at,
#                     completed_at=datetime.now(
#                         timezone.utc
#                     ),
#                 )
#             )

#             if stage_key:
#                 self._emit_stage(stage_key, "failed", f"{agent_name} failed: {exc}", agent_name=agent_name)

#             raise

#     @staticmethod
#     def _result_size(
#         result: dict[str, Any],
#     ) -> int:
#         """
#         Estimate how many records an agent produced.
#         """

#         candidate_keys = (
#             "results",
#             "records",
#             "test_summaries",
#             "test_tags",
#             "module_assignments",
#             "direct_impacts",
#             "changed_requirements",
#             "regulatory_tests",
#             "release_rules",
#         )

#         for key in candidate_keys:
#             value = result.get(
#                 key
#             )

#             if isinstance(
#                 value,
#                 (list, dict),
#             ):
#                 return len(value)

#         return len(result)

#     @staticmethod
#     def _require_mapping_key(
#         mapping: dict[str, Any],
#         key: str,
#         context: str,
#     ) -> Any:
#         """
#         Return a required mapping value or raise a clear error.
#         """

#         value = mapping.get(
#             key
#         )

#         if value is None:
#             raise KeyError(
#                 f"{context} did not provide required "
#                 f"field {key!r}."
#             )

#         return value

#     def _send_message(
#         self,
#         sender: str,
#         receiver: str,
#         message_type: str,
#         payload: dict[str, Any],
#     ) -> None:
#         """
#         Send one structured message through the in-memory message bus.
#         """

#         # A2A: Persist the same serializable envelope used by the specialist
#         # boundary so audit history contains explicit sender/receiver/type/data.
#         envelope = make_request(
#             sender=sender,
#             receiver=receiver,
#             message_type=message_type,
#             release_id=str(payload.get("release_id") or "").strip().upper(),
#             data=payload,
#         )
#         self.message_bus.send(
#             sender,
#             receiver,
#             message_type,
#             envelope.model_dump(mode="json"),
#         )

#     # A2A: Query routing uses the same Master-owned Jira snapshot and specialist
#     # outputs as the pipeline. The specialist never reads Jira directly.
#     _AGENT_QUERY_SPECS: dict[str, dict[str, Any]] = {
#         "feature": {
#             "name": "Feature / Epic Change Impact Agent",
#             "module": "app.agents.feature_change_agent.tools",
#             "source_blocks": FEATURE_INPUT_BLOCKS,
#             "state_attr": "change_impact",
#         },
#         "change": {
#             "name": "Feature / Epic Change Impact Agent",
#             "module": "app.agents.feature_change_agent.tools",
#             "source_blocks": FEATURE_INPUT_BLOCKS,
#             "state_attr": "change_impact",
#         },
#         "criticality": {
#             "name": "Application Criticality Classification Agent",
#             "module": "app.agents.criticality_agent.tools",
#             "source_blocks": ("modules", "test_cases", "tier_change_log"),
#             "state_attr": "criticality",
#         },
#         "history": {
#             "name": "Historical Execution Intelligence Agent",
#             "module": "app.agents.historical_agent.tools",
#             "source_blocks": HISTORICAL_INPUT_BLOCKS,
#             "state_attr": "history",
#         },
#         "historical": {
#             "name": "Historical Execution Intelligence Agent",
#             "module": "app.agents.historical_agent.tools",
#             "source_blocks": HISTORICAL_INPUT_BLOCKS,
#             "state_attr": "history",
#         },
#         "policy": {
#             "name": "Policy / Risk Appetite Calibration Agent",
#             "module": "app.agents.policy_agent.tools",
#             "source_blocks": POLICY_INPUT_BLOCKS,
#             "state_attr": "policy",
#         },
#         "risk": {
#             "name": "Policy / Risk Appetite Calibration Agent",
#             "module": "app.agents.policy_agent.tools",
#             "source_blocks": POLICY_INPUT_BLOCKS,
#             "state_attr": "policy",
#         },
#         "scoring": {
#             "name": "Decision Engine / Risk Scoring Agent",
#             "module": "app.agents.scoring_agent.tools",
#             "source_blocks": SCORING_INPUT_BLOCKS,
#             "state_attr": "scoring",
#         },
#         "selection": {
#             "name": "Decision Engine / Risk Scoring Agent",
#             "module": "app.agents.scoring_agent.tools",
#             "source_blocks": SCORING_INPUT_BLOCKS,
#             "state_attr": "scoring",
#         },
#         "governance": {
#             "name": "Exclusion Risk & Governance Agent",
#             "module": "app.agents.governance_agent.tools",
#             "source_blocks": (),
#             "state_attr": "governance",
#         },
#         "exclusion": {
#             "name": "Exclusion Risk & Governance Agent",
#             "module": "app.agents.governance_agent.tools",
#             "source_blocks": (),
#             "state_attr": "governance",
#         },
#     }

#     def _agent_query_source_data(
#         self,
#         agent_key: str,
#         state: PipelineState,
#     ) -> dict[str, list[dict[str, Any]]]:
#         """Return only the source blocks needed by one specialist query."""
#         spec = self._AGENT_QUERY_SPECS.get(agent_key)
#         if not spec:
#             raise ValueError(
#                 f"Unknown agent {agent_key!r}. Supported agents: "
#                 f"{sorted(self._AGENT_QUERY_SPECS)}"
#             )

#         # A2A: Post-run specialist queries receive the exact source blocks used
#         # by the completed pipeline. Do not reload Jira for a conversational query.
#         cached_source = self.get_cached_source_data(state.release_id)
#         if not cached_source and agent_key not in {"scoring", "selection", "governance", "exclusion"}:
#             raise RuntimeError(
#                 f"No completed Master source snapshot is available for release "
#                 f"{state.release_id}. Run the release pipeline after installing the updated Master Orchestrator."
#             )

#         source_data = {
#             block: list(cached_source.get(block, []))
#             for block in spec["source_blocks"]
#             if block in cached_source
#         }

#         # A2A: Downstream agents receive earlier specialist outputs as structured
#         # data, never as hidden objects or infrastructure references.
#         if agent_key in {"scoring", "selection"}:
#             source_data = dict(source_data)
#             source_data["change_impact"] = [state.change_impact]
#             source_data["criticality"] = [state.criticality]
#             source_data["history"] = [state.history]
#             source_data["policy"] = [state.policy]
#             # Keep post-run scoring queries compatible with both the current
#             # optional-input Scoring Agent and older runtimes that validate these
#             # configuration blocks at the orchestrator boundary.
#             policy_payload = state.policy.get("agent_output", state.policy) if isinstance(state.policy, dict) else {}
#             configured_weights = policy_payload.get("scoring_weights") or policy_payload.get("weights") or []
#             configured_thresholds = policy_payload.get("thresholds") or policy_payload.get("risk_thresholds") or []
#             if not configured_weights:
#                 configured_weights = [{"Factor": factor, "Weight": value} for factor, value in DEFAULT_WEIGHTS.items()]
#             if not configured_thresholds:
#                 configured_thresholds = [{"Classification": cls, "Minimum_Score": value} for cls, value in DEFAULT_THRESHOLDS.items()]
#             source_data["scoring_weights"] = configured_weights if isinstance(configured_weights, list) else []
#             source_data["thresholds"] = configured_thresholds if isinstance(configured_thresholds, list) else []
#         elif agent_key in {"governance", "exclusion"}:
#             source_data = {
#                 "scoring": [state.scoring],
#                 "policy": [state.policy],
#             }

#         return source_data

#     # A raw chat query is classified here, and only here — the frontend
#     # forwards whatever the user typed unchanged; the Master alone decides
#     # whether it needs a full pipeline run or a cached-context answer.
#     _PIPELINE_RUN_RELEASE_TOKEN_RE = re.compile(r"\b(?:REL-?|R)?\d{1,3}\.\d+\b", re.IGNORECASE)
#     _PIPELINE_RUN_TRIGGER_VERB_RE = re.compile(
#         r"\b(analy[sz]e|run|start|trigger|kick off|execute)\b", re.IGNORECASE
#     )

#     @classmethod
#     def detect_pipeline_run_request(cls, query: str) -> str | None:
#         """Decide whether a raw user query is asking to run the full Risk
#         Tier pipeline for a specific release, or is a conversational
#         drill-down question instead.

#         Returns the extracted release id for a pipeline-run request, or None
#         if the query should be answered from cached pipeline state instead.
#         A bare token (e.g. "R25.4") counts as a run request on its own; any
#         other phrasing needs an explicit trigger verb alongside a release
#         token (e.g. "analyze release R25.4").
#         """
#         trimmed = str(query or "").strip()
#         if not trimmed:
#             return None

#         if len(trimmed) <= 20 and len(trimmed.split()) <= 2:
#             bare_match = cls._PIPELINE_RUN_RELEASE_TOKEN_RE.search(trimmed)
#             if bare_match:
#                 return bare_match.group(0).upper()

#         if cls._PIPELINE_RUN_TRIGGER_VERB_RE.search(trimmed):
#             match = cls._PIPELINE_RUN_RELEASE_TOKEN_RE.search(trimmed)
#             if match:
#                 return match.group(0).upper()

#         return None

#     @staticmethod
#     def _detect_query_agents(question: str) -> list[str]:
#         """Infer one or more specialist agents from the user's question.

#         ADK should not choose the specialist. The Master owns routing so a
#         cross-agent question can consult multiple authoritative pipeline stages.
#         """
#         text = str(question or "").strip().lower()
#         if not text:
#             return ["scoring"]

#         scores: dict[str, int] = {
#             "feature": 0,
#             "criticality": 0,
#             "history": 0,
#             "policy": 0,
#             "scoring": 0,
#             "governance": 0,
#         }

#         keyword_groups = {
#             "feature": (
#                 "feature", "change impact", "changed epic", "epic", "user story",
#                 "story", "requirement", "traceability", "downstream", "directly impacted",
#                 "new feature", "mapping", "scope",
#             ),
#             "criticality": (
#                 "criticality", "critical", "tier 1", "tier-1", "tier 2", "tier-2",
#                 "tier 3", "tier-3", "tier 4", "tier-4", "module tier", "application tier",
#             ),
#             "history": (
#                 "historical", "history", "execution", "executions", "pass rate", "passed",
#                 "failed", "defect", "defects", "flaky", "recency", "insufficient history",
#                 "consistent pass", "zero defect", "historical value",
#             ),
#             "policy": (
#                 "policy", "risk appetite", "regulatory", "mandatory", "exclusion prohibited",
#                 "maximum exclusion", "exclusion cap", "approval role", "qa lead", "business owner",
#                 "release type",
#             ),
#             "scoring": (
#                 "score", "scoring", "classification", "must-test", "must test", "recommended",
#                 "optional", "exclude candidate", "exclude", "composite", "risk band",
#                 "risk scoring", "selected tests", "selection", "why only", "difference between",
#             ),
#             "governance": (
#                 "governance", "approval", "approved exclusion", "pending approval",
#                 "residual risk", "risk statement", "waiver",
#             ),
#         }

#         for agent_key, keywords in keyword_groups.items():
#             for keyword in keywords:
#                 if keyword in text:
#                     scores[agent_key] += 1

#         # Questions about totals/selection differences normally require both the
#         # upstream impact source and the final scoring result. Historical context
#         # is also useful when the wording asks why a population changed.
#         if (
#             ("how many" in text or "why only" in text or "difference" in text or "why" in text)
#             and "test" in text
#         ):
#             scores["scoring"] += 2
#             scores["feature"] += 1

#         ordered = sorted(
#             (key for key, value in scores.items() if value > 0),
#             key=lambda key: (-scores[key], ("feature", "criticality", "history", "policy", "scoring", "governance").index(key)),
#         )

#         # If no specialist-specific signal exists, answer from scoring because it
#         # is the final decision stage and has the compact classification result.
#         return ordered or ["scoring"]

#     def _answer_single_agent_question(
#         self,
#         normalized_release_id: str,
#         agent_key: str,
#         question_text: str,
#         state: PipelineState,
#     ) -> dict[str, Any]:
#         """Query one specialist through the Master-owned A2A boundary."""
#         if agent_key not in self._AGENT_QUERY_SPECS:
#             raise ValueError(
#                 f"Unknown agent {agent_key!r}. Supported agents: "
#                 f"{sorted(self._AGENT_QUERY_SPECS)}"
#             )

#         spec = self._AGENT_QUERY_SPECS[agent_key]
#         agent_output = getattr(state, spec["state_attr"]) or {}
#         if not isinstance(agent_output, dict):
#             agent_output = {"value": agent_output}
#         compact_context = self.get_cached_agent_context(
#             normalized_release_id,
#             agent_key,
#             question_text,
#         )
#         # get_cached_agent_context always attaches the targeted agent's own
#         # raw output under "agent_output" (see that method), independent of
#         # whatever extra topic-specific summary `question_kind` bolts on —
#         # so a single check here covers every agent uniformly instead of
#         # each one checking a different, `kind`-coupled key name that only
#         # happened to be present for some question phrasings.
#         if "agent_output" not in compact_context:
#             raise RuntimeError(
#                 f"{spec['name']} context is missing agent_output."
#             )
#         source_data = compact_context.get("traceability", {}) if isinstance(compact_context, dict) else {}

#         request = make_request(
#             sender=self.name,
#             receiver=spec["name"],
#             message_type="AGENT_QUERY",
#             release_id=normalized_release_id,
#             data={
#                 "question": question_text,
#                 "agent_context": compact_context,
#             },
#         )

#         response: A2AResponse | None = None
#         handler_error: Exception | None = None
#         try:
#             module = importlib.import_module(spec["module"])
#             handler = getattr(module, "handle_a2a_request", None)
#             if not callable(handler):
#                 raise RuntimeError(
#                     f"{spec['name']} does not expose an A2A handle_a2a_request function."
#                 )
#             candidate = handler(request)
#             if not isinstance(candidate, A2AResponse):
#                 raise TypeError(
#                     f"{spec['name']} returned {type(candidate).__name__} for AGENT_QUERY; expected A2AResponse."
#                 )
#             response = candidate
#         except Exception as exc:
#             handler_error = exc
#             response = None

#         if self._is_traceability_mapping_question(question_text) and agent_key in {"feature", "change"}:
#             trace = compact_context.get("traceability", {}) if isinstance(compact_context, dict) else {}
#             markdown = self._format_feature_traceability_mapping(
#                 state=state,
#                 source_data=trace,
#             )
#         else:
#             response_data = (
#                 response.data
#                 if isinstance(response, A2AResponse)
#                 else {}
#             )
#             if not isinstance(response_data, dict):
#                 response_data = {"answer": str(response_data)}
#             markdown = response_data.get("markdown")
#             if not isinstance(markdown, str) or self._looks_like_context_dump(markdown):
#                 markdown = self._format_agent_query_answer(
#                     agent_key=agent_key,
#                     question=question_text,
#                     state=state,
#                     agent_output=agent_output,
#                     source_data=source_data,
#                 )

#         return {
#             "agent_key": agent_key,
#             "agent": spec["name"],
#             "markdown": markdown,
#             "a2a_handler_fallback": bool(handler_error),
#         }

#     def answer_agent_question(
#         self,
#         release_id: str,
#         question: str,
#         agent: str | None = None,
#         model_id: str = "gpt-5-mini",
#     ) -> dict[str, Any]:
#         """Answer a post-run question using Master-owned automatic routing.

#         ``agent`` is retained as an optional backward-compatible override for
#         internal callers, but ADK-facing callers should omit it. The Master
#         automatically detects one or more specialists and merges their evidence.
#         """
#         normalized_release_id = str(release_id or "").strip().upper()
#         question_text = str(question or "").strip()

#         if not normalized_release_id:
#             raise ValueError("release_id cannot be empty.")
#         if not question_text:
#             raise ValueError("question is required.")

#         state = self.get_cached_state(normalized_release_id)
#         if state is None:
#             raise RuntimeError(
#                 f"No completed pipeline state is available for {normalized_release_id}. "
#                 "Run execute_risk_tier_pipeline once before asking drill-down questions."
#             )

#         agent_keys = [str(agent).strip().lower()] if agent else self._detect_query_agents(question_text)
#         agent_keys = [key for key in agent_keys if key in self._AGENT_QUERY_SPECS]
#         if not agent_keys:
#             agent_keys = ["scoring"]

#         # De-duplicate aliased routing keys while preserving order.
#         seen: set[str] = set()
#         deduplicated_agent_keys: list[str] = []
#         for key in agent_keys:
#             if key in seen:
#                 continue
#             seen.add(key)
#             deduplicated_agent_keys.append(key)
#         agent_keys = deduplicated_agent_keys

#         results = [
#             self._answer_single_agent_question(
#                 normalized_release_id=normalized_release_id,
#                 agent_key=key,
#                 question_text=question_text,
#                 state=state,
#             )
#             for key in agent_keys
#         ]

#         if len(results) == 1:
#             markdown = results[0]["markdown"]
#         else:
#             lines = [
#                 f"## Risk Tier Master Answer — {normalized_release_id}",
#                 "",
#                 f"**Question:** {question_text}",
#                 "",
#                 "The Master Orchestrator consulted the following specialist agents:",
#                 "",
#             ]
#             for result in results:
#                 lines.extend([
#                     f"- {result['agent']}",
#                 ])
#             lines.append("")
#             for result in results:
#                 lines.extend([
#                     "---",
#                     "",
#                     f"### {result['agent']}",
#                     "",
#                     str(result["markdown"]),
#                     "",
#                 ])
#             markdown = "\n".join(lines).strip()

#         return {
#             "status": "success",
#             "release_id": normalized_release_id,
#             "agents_consulted": [self._AGENT_QUERY_SPECS[key]["name"] for key in agent_keys],
#             "message_type": "AGENT_QUERY",
#             "markdown": markdown,
#             "a2a_handler_fallback": any(result["a2a_handler_fallback"] for result in results),
#         }

#     @staticmethod
#     def _looks_like_context_dump(markdown: str) -> bool:
#         """Detect the old generic JSON context-dump response."""
#         lowered = markdown.lower()
#         return (
#             "## specialist context" in lowered
#             or "```json" in lowered and "agent_output" in lowered
#             or '"question":' in lowered and '"context":' in lowered
#         )

#     @staticmethod
#     def _is_traceability_mapping_question(question: str) -> bool:
#         lowered = str(question or "").lower()
#         return (
#             ("epic" in lowered and "story" in lowered and "requirement" in lowered and "test" in lowered)
#             or "epic -> story" in lowered
#             or "epic → story" in lowered
#             or ("traceability" in lowered and "mapping" in lowered)
#         )

#     @staticmethod
#     def _first_text(row: dict[str, Any], *keys: str) -> str:
#         for key in keys:
#             value = row.get(key)
#             if value not in (None, ""):
#                 text = str(value).strip()
#                 if text:
#                     return text
#         return ""

#     def _format_feature_traceability_mapping(
#         self,
#         state: PipelineState,
#         source_data: dict[str, list[dict[str, Any]]],
#     ) -> str:
#         """Render authoritative Epic -> Story -> Requirement -> Tests data.

#         A2A: This formatter consumes the same structured blocks the Master sent
#         to the Feature Agent. It does not infer relationships from scoring.
#         """
#         epics = source_data.get("epics", [])
#         stories = source_data.get("stories", [])
#         requirements = source_data.get("requirements", [])
#         rtm = source_data.get("rtm", [])

#         tests_by_requirement: dict[str, list[str]] = {}
#         for mapping in rtm:
#             req_id = self._first_text(mapping, "Requirement_ID", "Requirement ID")
#             tc_id = self._first_text(mapping, "Test_Case_ID", "Test Case ID")
#             if req_id and tc_id:
#                 tests_by_requirement.setdefault(req_id, []).append(tc_id)

#         requirements_by_story: dict[str, list[dict[str, Any]]] = {}
#         for requirement in requirements:
#             story_id = self._first_text(
#                 requirement,
#                 "User_Story_ID",
#                 "Story_ID",
#                 "User Story ID",
#             )
#             if story_id:
#                 requirements_by_story.setdefault(story_id, []).append(requirement)

#         epic_by_issue_key: dict[str, str] = {}
#         for epic in epics:
#             epic_key = self._first_text(epic, "issue_key", "work_item_id", "Epic_ID", "Epic ID")
#             epic_id = self._first_text(epic, "Epic_ID", "Epic ID", "work_item_id", "issue_key")
#             if epic_key and epic_id:
#                 epic_by_issue_key[epic_key] = epic_id

#         stories_by_epic: dict[str, list[dict[str, Any]]] = {}
#         for story in stories:
#             epic_id = self._first_text(
#                 story,
#                 "Epic_ID",
#                 "Epic ID",
#             )
#             if not epic_id:
#                 parent_key = self._first_text(story, "parent_key")
#                 epic_id = epic_by_issue_key.get(parent_key, "")
#             if epic_id:
#                 stories_by_epic.setdefault(epic_id, []).append(story)

#         lines = [
#             f"## Epic → Story → Requirement → Tests — {state.release_id}",
#             "",
#             "Source: completed Master Orchestrator release snapshot.",
#             "",
#         ]

#         if not epics:
#             lines.append("No in-scope Epic records were supplied by the Master Orchestrator.")
#             return "\n".join(lines)

#         for epic in epics:
#             epic_id = self._first_text(
#                 epic,
#                 "Epic_ID",
#                 "Epic ID",
#                 "work_item_id",
#                 "issue_key",
#             )
#             epic_name = self._first_text(
#                 epic,
#                 "Epic_Name",
#                 "Epic Name",
#                 "summary",
#             )
#             lines.append(
#                 f"### `{epic_id}`"
#                 + (f" — {epic_name}" if epic_name and epic_name != epic_id else "")
#             )

#             epic_stories = stories_by_epic.get(epic_id, [])
#             if not epic_stories:
#                 lines.append("- No mapped stories found in the release snapshot.")
#                 lines.append("")
#                 continue

#             for story in epic_stories:
#                 story_id = self._first_text(
#                     story,
#                     "User_Story_ID",
#                     "Story_ID",
#                     "User Story ID",
#                     "work_item_id",
#                     "issue_key",
#                 )
#                 story_name = self._first_text(
#                     story,
#                     "User_Story_Name",
#                     "Story Name",
#                     "summary",
#                 )
#                 lines.append(
#                     f"- **Story `{story_id}`**"
#                     + (f" — {story_name}" if story_name and story_name != story_id else "")
#                 )

#                 story_requirements = requirements_by_story.get(story_id, [])
#                 if not story_requirements:
#                     lines.append("  - No mapped requirements found in the release snapshot.")
#                     continue

#                 for requirement in story_requirements:
#                     req_id = self._first_text(
#                         requirement,
#                         "Requirement_ID",
#                         "Requirement ID",
#                         "work_item_id",
#                         "issue_key",
#                     )
#                     req_name = self._first_text(
#                         requirement,
#                         "Requirement_Name",
#                         "Requirement Name",
#                         "summary",
#                         "Requirement_Description",
#                     )
#                     lines.append(
#                         f"  - **Requirement `{req_id}`**"
#                         + (f" — {req_name}" if req_name and req_name != req_id else "")
#                     )
#                     test_ids = sorted(set(tests_by_requirement.get(req_id, [])))
#                     if test_ids:
#                         lines.append(
#                             "    - Tests: " + ", ".join(f"`{tc}`" for tc in test_ids)
#                         )
#                     else:
#                         lines.append("    - Tests: **TRACEABILITY GAP**")

#             lines.append("")

#         return "\n".join(lines).strip()

#     @staticmethod
#     def _unwrap_agent_output(value: Any) -> dict[str, Any]:
#         if not isinstance(value, dict):
#             return {}
#         nested = value.get("agent_output")
#         return nested if isinstance(nested, dict) else value

#     @staticmethod
#     def _normalize_test_id(value: Any) -> str:
#         return str(value or "").strip().upper()

#     def _format_population_reconciliation(
#         self,
#         state: PipelineState,
#         question: str,
#     ) -> str:
#         """Explain direct-impact vs scoring population using exact cached IDs."""
#         change = self._unwrap_agent_output(state.change_impact)
#         scoring = self._unwrap_agent_output(state.scoring)
#         direct_ids = {
#             self._normalize_test_id(value)
#             for value in change.get("direct_test_ids", [])
#             if self._normalize_test_id(value)
#         }
#         results = scoring.get("results", [])
#         classified_ids = {
#             self._normalize_test_id(row.get("test_case_id"))
#             for row in results
#             if isinstance(row, dict) and self._normalize_test_id(row.get("test_case_id"))
#         }
#         missing = sorted(direct_ids - classified_ids)
#         extra = sorted(classified_ids - direct_ids)

#         lines = [
#             f"### Direct Impact vs Final Classification — {state.release_id}",
#             f"- Directly impacted test cases: **{len(direct_ids)}**",
#             f"- Test cases present in final scoring results: **{len(classified_ids)}**",
#             f"- Direct-impact tests missing from scoring: **{len(missing)}**",
#             f"- Classified tests not in direct-impact set: **{len(extra)}**",
#         ]

#         if missing:
#             lines.extend(["", "**Direct-impact IDs missing from scoring:**"])
#             source_rows = {}
#             for row in self.get_cached_source_data(state.release_id).get("test_cases", []):
#                 if isinstance(row, dict):
#                     key = self._normalize_test_id(
#                         row.get("Test_Case_ID")
#                         or row.get("Test Case ID")
#                         or row.get("work_item_id")
#                         or row.get("issue_key")
#                     )
#                     if key:
#                         source_rows[key] = row
#             for test_id in missing:
#                 row = source_rows.get(test_id)
#                 if not row:
#                     lines.append(f"- `{test_id}` — no matching test-case row exists in the persisted Master source snapshot.")
#                     continue
#                 status = str(
#                     row.get("Test_Status")
#                     or row.get("Test Status")
#                     or row.get("status")
#                     or ""
#                 ).strip()
#                 lines.append(
#                     f"- `{test_id}` — source snapshot status=`{status or 'not populated'}`; it was not present in final scoring results."
#                 )
#         if extra:
#             lines.extend(["", "**Scoring tests outside the direct-impact set:**"])
#             lines.append("- " + ", ".join(f"`{item}`" for item in extra))

#         lines.extend(["", "This reconciliation uses the exact IDs emitted by the Change Impact and Scoring stages; it does not infer a count from prose."])
#         return "\n".join(lines)

#     def _format_optional_score_answer(
#         self,
#         state: PipelineState,
#         question: str,
#     ) -> str:
#         scoring = self._unwrap_agent_output(state.scoring)
#         results = [
#             row for row in scoring.get("results", [])
#             if isinstance(row, dict) and str(row.get("classification") or "").strip().upper() == "OPTIONAL"
#         ]
#         scores = [
#             float(row["composite_score"])
#             for row in results
#             if row.get("composite_score") not in (None, "")
#         ]
#         lines = [
#             f"### Optional Test Composite Scores — {state.release_id}",
#             f"- Optional test count: **{len(results)}**",
#         ]
#         if scores:
#             ordered = sorted(scores)
#             avg = sum(scores) / len(scores)
#             median = ordered[len(ordered) // 2] if len(ordered) % 2 else (ordered[len(ordered)//2 - 1] + ordered[len(ordered)//2]) / 2
#             lines.extend([
#                 f"- Minimum composite score: **{min(scores):.2f}**",
#                 f"- Maximum composite score: **{max(scores):.2f}**",
#                 f"- Average composite score: **{avg:.2f}**",
#                 f"- Median composite score: **{median:.2f}**",
#                 "",
#                 "| Test Case | Composite Score |",
#                 "|---|---:|",
#             ])
#             for row in sorted(results, key=lambda item: self._normalize_test_id(item.get("test_case_id"))):
#                 score = row.get("composite_score")
#                 lines.append(f"| `{row.get('test_case_id')}` | {float(score):.2f} |")
#         else:
#             lines.append("- No numeric composite scores were stored for the Optional classification rows.")
#         return "\n".join(lines)

#     def _format_protection_flag_answer(
#         self,
#         state: PipelineState,
#         question: str,
#         agent_output: dict[str, Any],
#     ) -> str:
#         """Answer "which tests were prevented from being downgraded, and by which flag?".

#         A row qualifies when its final classification differs from what the
#         raw composite score alone would have produced
#         (``classification_overridden``, set by the Scoring Agent itself —
#         see app/agents/scoring_agent/tools.py) and it actually carries at
#         least one protection flag — i.e. a hard protection rule changed the
#         outcome, not just a scoring-band boundary. Optionally scoped to one
#         tier if the question names one (e.g. "Tier-1").
#         """
#         question_lower = question.lower()
#         rows = self._flatten_result_rows(agent_output)

#         tier_filter: int | None = None
#         tier_match = re.search(r"\btier[\s-]*([1-4])\b", question_lower)
#         if tier_match:
#             tier_filter = int(tier_match.group(1))

#         protected_rows = [
#             row for row in rows
#             if row.get("classification_overridden")
#             and row.get("protection_flags")
#             and (tier_filter is None or str(row.get("tier")) == str(tier_filter))
#         ]

#         scope_label = f"Tier-{tier_filter} " if tier_filter else ""
#         lines = [
#             f"### {scope_label}Tests Protected From Downgrade — {state.release_id}",
#             f"**Question:** {question}",
#             "",
#         ]

#         if not protected_rows:
#             lines.append(
#                 f"No {scope_label}tests were found where a protection flag changed the "
#                 "final classification away from the raw composite score."
#             )
#             return "\n".join(lines)

#         lines.append(f"- Count: **{len(protected_rows)}**")
#         lines.append("")
#         lines.append("| Test Case | Final Classification | Would-Have-Been | Triggering Protection Flag(s) |")
#         lines.append("|---|---|---|---|")
#         for row in sorted(protected_rows, key=lambda r: self._normalize_test_id(r.get("test_case_id"))):
#             flags = ", ".join(f"`{flag}`" for flag in row.get("protection_flags", []))
#             lines.append(
#                 f"| `{row.get('test_case_id')}` | **{row.get('classification')}** | "
#                 f"`{row.get('base_classification')}` | {flags} |"
#             )
#         return "\n".join(lines)

#     def _format_agent_query_answer(
#         self,
#         agent_key: str,
#         question: str,
#         state: PipelineState,
#         agent_output: dict[str, Any],
#         source_data: dict[str, list[dict[str, Any]]],
#     ) -> str:
#         """Render compact, question-oriented evidence for ADK."""
#         lines = [
#             f"## {self._AGENT_QUERY_SPECS[agent_key]['name']} — {state.release_id}",
#             "",
#             f"**Question:** {question}",
#             "",
#         ]

#         question_lower = question.lower()
#         result_rows = self._flatten_result_rows(agent_output)

#         # Common test-specific lookup for "why", classification, protection and
#         # similar questions. The CSV-backed result is already in pipeline state.
#         requested_test_ids = set(
#             match.upper()
#             for match in re.findall(r"\bTC-\d+\b", question, re.IGNORECASE)
#         )

#         if agent_key in {"scoring", "selection"} and "optional" in question_lower and ("composite" in question_lower or "score" in question_lower):
#             return self._format_optional_score_answer(state, question)

#         if agent_key in {"scoring", "selection"} and (
#             ("prevented" in question_lower or "protect" in question_lower)
#             and ("downgrad" in question_lower or "protection flag" in question_lower or "triggering" in question_lower)
#         ):
#             return self._format_protection_flag_answer(state, question, agent_output)

#         if agent_key in {"scoring", "selection"} and ("directly impacted" in question_lower or "direct impact" in question_lower) and ("classified" in question_lower or "classification" in question_lower or "only" in question_lower or "difference" in question_lower):
#             return self._format_population_reconciliation(state, question)

#         if agent_key in {"scoring", "selection"} and requested_test_ids:
#             matches = [
#                 row for row in result_rows
#                 if str(row.get("test_case_id") or "").upper() in requested_test_ids
#             ]
#             if matches:
#                 lines.append("### Test-level result")
#                 for row in matches[:10]:
#                     lines.append(
#                         f"- `{row.get('test_case_id')}`: "
#                         f"**{row.get('classification', 'UNKNOWN')}**; "
#                         f"tier=`{row.get('tier', 'N/A')}`; "
#                         f"score=`{row.get('composite_score', 'N/A')}`"
#                     )
#                     reasons = row.get("reasons") or []
#                     if isinstance(reasons, str):
#                         reasons = [reasons]
#                     for reason in list(reasons)[:8]:
#                         lines.append(f"  - {reason}")
#                 return "\n".join(lines)

#         # Feature / Change Impact evidence.
#         if agent_key in {"feature", "change"}:
#             summary = agent_output.get("summary", {}) if isinstance(agent_output, dict) else {}
#             lines.extend([
#                 "### Change Impact",
#                 f"- In-scope epics: {summary.get('in_scope_epics', 0)}",
#                 f"- Changed user stories: {summary.get('changed_user_stories', 0)}",
#                 f"- Changed requirements: {summary.get('changed_requirements', 0)}",
#                 f"- Directly impacted tests: {summary.get('direct_test_cases', 0)}",
#                 f"- Downstream dependencies: {summary.get('downstream_dependencies', 0)}",
#                 f"- Downstream module test cases: {summary.get('downstream_module_test_cases', 0)}",
#                 f"- Additional downstream tests: {len(set(map(str, agent_output.get('downstream_test_ids', []))))}",
#                 f"- New-feature tests: {summary.get('new_feature_tests', 0)}",
#                 f"- Traceability gaps: {summary.get('traceability_gaps', 0)}",
#             ])
#             changed_epics = agent_output.get("changed_epics", [])

#             if changed_epics:
#                 lines.append("")
#                 lines.append("### Changed Epics")

#                 for epic in changed_epics:

#                     epic_id = (
#                         epic.get("Epic_ID")
#                         or epic.get("Epic ID")
#                         or epic.get("work_item_id")
#                         or epic.get("issue_key")
#                         or "Unknown"
#                     )

#                     epic_name = (
#                         epic.get("Epic_Name")
#                         or epic.get("Epic Name")
#                         or epic.get("summary")
#                         or ""
#                     )

#                     if epic_name:
#                         lines.append(f"- {epic_id} : {epic_name}")
#                     else:
#                         lines.append(f"- {epic_id}")

#             if requested_test_ids:
#                 for test_id in sorted(requested_test_ids):
#                     if test_id in set(map(str.upper, agent_output.get("direct_test_ids", []))):
#                         lines.append(f"- `{test_id}` is in the direct-impact set.")
#                     elif test_id in set(map(str.upper, agent_output.get("downstream_test_ids", []))):
#                         lines.append(f"- `{test_id}` is in the additional downstream-impact set.")
#                     else:
#                         lines.append(f"- `{test_id}` is not present in the Feature Agent impact lists.")
#             if "br-chg" in question_lower or "business rule" in question_lower or "validate" in question_lower:
#                 lines.extend([
#                     "",
#                     "### Business-rule evidence",
#                     "- BR-CHG-01: evidence comes from release-scope Epic/Story linkage and out-of-scope handling.",
#                     "- BR-CHG-02: evidence comes from changed Requirement IDs and RTM Requirement-to-Test mappings.",
#                     "- BR-CHG-03: evidence comes from normalized one-way downstream dependencies and downstream test IDs.",
#                     "- BR-CHG-04: evidence requires the requirement-level impact map; summary counts alone are not treated as proof.",
#                     "- BR-CHG-05: evidence comes from new-requirement/new-epic protection and first-release coverage actions.",
#                 ])
#                 lines.append(f"- Source blocks supplied to the Feature Agent: {', '.join(sorted(source_data))}.")
#             return "\n".join(lines)

#         # Criticality evidence.
#         if agent_key == "criticality":
#             summary = agent_output.get("summary", {}) if isinstance(agent_output, dict) else {}
#             lines.extend([
#                 "### Criticality",
#                 f"- Tier 1 modules: {summary.get('tier_1_modules', 0)}",
#                 f"- Tier 2 modules: {summary.get('tier_2_modules', 0)}",
#                 f"- Tier 3 modules: {summary.get('tier_3_modules', 0)}",
#                 f"- Tier 4 modules: {summary.get('tier_4_modules', 0)}",
#                 f"- Test tags produced: {len(agent_output.get('test_tags', {})) if isinstance(agent_output.get('test_tags'), dict) else 0}",
#             ])
#             assignments = agent_output.get("module_assignments", {})
#             if isinstance(assignments, dict):
#                 for module_id, assignment in list(sorted(assignments.items()))[:20]:
#                     if isinstance(assignment, dict):
#                         lines.append(
#                             f"- `{module_id}` -> `{assignment.get('final_tier', assignment.get('tier', 'N/A'))}`"
#                         )
#                     else:
#                         lines.append(f"- `{module_id}` -> `{assignment}`")
#             if "br-crit" in question_lower or "business rule" in question_lower or "validate" in question_lower:
#                 lines.extend([
#                     "",
#                     "### Business-rule checks",
#                     "- BR-CRIT-01: weighted module factors determine Tier 1-4.",
#                     "- BR-CRIT-02: each test inherits its mapped module tier; no independent lower test tier is allowed.",
#                     "- BR-CRIT-03: Tier 1 requires 100% coverage; Tier 2 requires at least 70%; Tier 3/4 remain risk-based.",
#                     "- BR-CRIT-04: qualifying production incidents require escalation; de-escalation requires approved governance evidence.",
#                 ])
#                 lines.append(f"- Source blocks supplied: {', '.join(sorted(source_data))}.")
#             return "\n".join(lines)

#         # Historical evidence.
#         if agent_key in {"history", "historical"}:
#             summary = agent_output.get("summary", {}) if isinstance(agent_output, dict) else {}
#             lines.extend([
#                 "### Historical Execution",
#                 f"- Test cases analysed: {summary.get('total_test_cases', summary.get('test_cases_analysed', 0))}",
#                 f"- Executions: {summary.get('total_execution_records', summary.get('historical_executions', 0))}",
#                 f"- Passed: {summary.get('passed_executions', 0)}",
#                 f"- Failed: {summary.get('failed_executions', 0)}",
#                 f"- Confirmed defects: {summary.get('confirmed_defects', 0)}",
#                 f"- Defect-protected tests: {summary.get('defect_protected_tests', 0)}",
#                 f"- Flaky tests: {summary.get('flaky_test_count', summary.get('flaky_tests', 0))}",
#                 f"- Insufficient-history tests: {summary.get('tests_with_insufficient_history', 0)}",
#                 f"- Consistent-pass/zero-defect eligible tests: {summary.get('consistent_pass_zero_defect_eligible_tests', 0)}",
#             ])
#             for key, label in (
#                 ("defect_protected_test_ids", "Defect-protected tests"),
#                 ("flaky_test_ids", "Flaky tests"),
#                 ("insufficient_history_test_ids", "Insufficient-history tests"),
#                 ("consistent_pass_zero_defect_candidate_ids", "Consistent-pass candidates"),
#             ):
#                 values = agent_output.get(key, [])
#                 if isinstance(values, (list, tuple, set)) and values:
#                     lines.append(f"- {label}: {', '.join(map(str, sorted(values))) }")
#             if "br-hist" in question_lower or "business rule" in question_lower or "validate" in question_lower:
#                 lines.extend([
#                     "",
#                     "### Business-rule checks",
#                     "- Recent confirmed-defect protection is retained and must not be removed by score alone.",
#                     "- Flakiness is remediation-only and does not reduce Historical Value Score.",
#                     "- Insufficient history is an inclusion safeguard, not a reason for exclusion.",
#                     "- Consistent-pass/zero-defect eligibility is limited to the configured Tier 3/4 conditions.",
#                     "- Recency decay is applied before Historical Value Score contribution.",
#                 ])
#             return "\n".join(lines)

#         # Policy evidence.
#         if agent_key in {"policy", "risk"}:
#             summary = agent_output.get("summary", {}) if isinstance(agent_output, dict) else {}
#             lines.extend([
#                 "### Risk Appetite / Policy",
#                 f"- Release type: {summary.get('release_type', agent_output.get('release_type', 'UNKNOWN'))}",
#                 f"- Regulatory tests: {summary.get('regulatory_test_count', 0)}",
#                 f"- Mandatory tests: {summary.get('mandatory_test_count', 0)}",
#                 f"- Exclusion-prohibited tests: {summary.get('exclusion_prohibited_test_count', 0)}",
#                 f"- Maximum overall exclusion: {summary.get('overall_max_exclusion_percent', agent_output.get('overall_max_exclusion', 0))}",
#                 f"- Approval required: {summary.get('require_approval_for_exclusion', summary.get('approval_required', True))}",
#             ])
#             if "br-risk" in question_lower or "business rule" in question_lower or "validate" in question_lower:
#                 lines.extend([
#                     "",
#                     "### Business-rule checks",
#                     "- Regulatory/compliance tests are non-negotiable Must-Test.",
#                     "- Release-type posture controls the applicable risk thresholds.",
#                     "- Overall exclusion cannot exceed the configured cap without required leadership approval.",
#                     "- Tier-specific exclusion tolerances are published with the policy result.",
#                 ])
#             return "\n".join(lines)

#         # Governance evidence.
#         if agent_key in {"governance", "exclusion"}:
#             summary = agent_output.get("summary", {}) if isinstance(agent_output, dict) else {}
#             lines.extend([
#                 "### Governance",
#                 f"- Exclusion candidates: {summary.get('exclusion_candidates', 0)}",
#                 f"- Approved exclusions: {summary.get('approved_exclusions', 0)}",
#                 f"- Pending approvals: {summary.get('pending_approvals', 0)}",
#                 f"- Exclusion rate: {summary.get('exclusion_rate_percent', summary.get('exclusion_rate', 0))}",
#                 f"- Maximum allowed exclusion: {summary.get('maximum_allowed_exclusion_percent', summary.get('maximum_allowed_exclusion_rate', 0))}",
#                 f"- Cap exceeded: {summary.get('over_cap', summary.get('exclusion_cap_exceeded', False))}",
#             ])
#             if "br-gov" in question_lower or "business rule" in question_lower or "validate" in question_lower:
#                 lines.extend([
#                     "",
#                     "### Business-rule checks",
#                     "- Each exclusion candidate requires an auditable risk statement.",
#                     "- Medium residual-risk exclusions require QA Lead approval.",
#                     "- High residual-risk exclusions require QA Lead and Business Owner approval.",
#                     "- The aggregate exclusion set must remain within the approved risk-appetite cap.",
#                 ])
#             return "\n".join(lines)

#         lines.append("### Available answer")
#         lines.append("The specialist A2A query completed and the answer above is grounded in the current Master Orchestrator state.")
#         return "\n".join(lines)

#     @staticmethod
#     def _flatten_result_rows(agent_output: dict[str, Any]) -> list[dict[str, Any]]:
#         if not isinstance(agent_output, dict):
#             return []
#         for key in ("results", "classification_results", "test_results"):
#             value = agent_output.get(key)
#             if isinstance(value, list) and all(isinstance(item, dict) for item in value):
#                 return value
#         nested = agent_output.get("agent_output")
#         if isinstance(nested, dict):
#             return RiskTierMasterOrchestrator._flatten_result_rows(nested)
#         return []

#     def execute(
#         self,
#         release_id: str,
#         on_stage: Callable[[str, str, str, str | None, dict[str, Any] | None], None] | None = None,
#     ) -> PipelineState:
#         """
#         Execute the complete Risk Tier pipeline for one release.

#         ``on_stage(stage_key, status, text, agent_name)`` is an optional
#         real-time progress callback used by the AG-UI streaming agent
#         (app/agents/pipeline_stream_agent.py). ``stage_key`` is one of
#         "orchestrator", "agent1".."agent6", "ledger" (a stable routing id);
#         ``status`` is one of "running", "finished", "failed"; ``agent_name``
#         is the human-readable name to display (e.g. "Feature / Epic Change
#         Impact Agent") and may be sent multiple times per stage_key with
#         different ``text`` — the Jira-loading phase in particular emits
#         several "running" sub-progress updates under stage_key="orchestrator"
#         before it finishes, since that single step is where essentially all
#         of a run's wall-clock time is actually spent (every later stage reads
#         from data already loaded into memory here — no further Jira/network
#         calls happen after this point). Every existing caller that omits
#         on_stage (CLI, plain REST /analyze) is unaffected.
#         """

#         self._on_stage = on_stage
#         _ORCHESTRATOR_NAME = "Master Orchestrator"

#         normalized_release_id = str(
#             release_id or ""
#         ).strip().upper()

#         if not normalized_release_id:
#             raise ValueError(
#                 "release_id cannot be empty."
#             )

#         self._emit_stage("orchestrator", "running", "Freezing release scope, loading Jira data…", agent_name=_ORCHESTRATOR_NAME)

#         try:
#             self._prepare_jira_source_data(
#                 normalized_release_id
#             )
#         except Exception as exc:
#             self._emit_stage("orchestrator", "failed", f"Failed to load Jira data: {exc}", agent_name=_ORCHESTRATOR_NAME)
#             raise

#         self._emit_stage("orchestrator", "finished", "Release scope frozen.", agent_name=_ORCHESTRATOR_NAME)

#         # Start every execution with an empty message bus.
#         self.message_bus = InMemoryMessageBus()

#         state = PipelineState(
#             release_id=normalized_release_id
#         )

#         # =====================================================
#         # Agents 1-4: Feature / Criticality / Historical / Policy
#         # =====================================================
#         # These four stages are mutually independent: each needs only the
#         # already-loaded Jira source data (self._jira_source_data), never
#         # another stage's output. Release/Release_Type — Policy's one input
#         # that used to be read back out of Feature's own echoed response —
#         # is resolved directly from that source data here instead, so Policy
#         # no longer has a data dependency on Feature. They still run one
#         # after another in plain Python, in order 1-4; Scoring (Agent 5)
#         # waits for all four to finish before it runs, which is unchanged.
#         release_rows = self._jira_source_data.get("releases", [])
#         state.release = release_rows[0] if release_rows else {}

#         release_type_value = (
#             state.release.get(
#                 "Release_Type"
#             )
#             or state.release.get(
#                 "Release Type"
#             )
#             or state.release.get(
#                 "release_type"
#             )
#         )

#         if not release_type_value:
#             release_issue_key = state.release.get("issue_key") or "none (no matching Release issue)"
#             release_source = state.release.get("release_source") or "direct Jira Release/label match"
#             release_known_keys = sorted(state.release.keys())
#             raise ValueError(
#                 f"Release {normalized_release_id!r} was found in Jira, but "
#                 "Release_Type could not be read. "
#                 f"Matched Jira issue_key={release_issue_key!r}, "
#                 f"resolved via={release_source!r}, "
#                 f"fields present on the matched release row={release_known_keys}. "
#                 "If issue_key is 'none', R25.4 only exists as a Fix Version on "
#                 "other issues (Epics/Stories) — create a real Jira issue of the "
#                 "'Release' issue type for it instead, with Release_Type populated. "
#                 "If an issue_key IS present, open that Jira issue and confirm its "
#                 "'Release Type' custom field has a value — if the project has "
#                 "duplicate 'Release Type' fields, dynamic field discovery may be "
#                 "resolving to the wrong one."
#             )

#         release_type = str(
#             release_type_value
#         ).strip().upper()

#         feature_source_data = self._load_source_data(FEATURE_INPUT_BLOCKS)
#         criticality_source_data = self._load_source_data(CRITICALITY_INPUT_BLOCKS)
#         historical_source_data = self._load_source_data(HISTORICAL_INPUT_BLOCKS)
#         policy_source_data = self._load_source_data(POLICY_INPUT_BLOCKS)
#         logger.INFO(f"policy_source_data : {policy_source_data }")

#         # A2A: Master -> Feature / Criticality / Historical / Policy Agents.
#         feature_request = make_request(
#             sender="Risk Tier Master Orchestrator",
#             receiver="Feature / Epic Change Impact Agent",
#             message_type="FEATURE_CHANGE_REQUEST",
#             release_id=normalized_release_id,
#             data={"source_data": feature_source_data},
#         )
#         criticality_request = make_request(
#             sender="Risk Tier Master Orchestrator",
#             receiver="Application Criticality Classification Agent",
#             message_type="CRITICALITY_REQUEST",
#             release_id=normalized_release_id,
#             data={"source_data": criticality_source_data},
#         )
#         logger.INFO(f"criticality_source_data : {criticalitycriticality_source_data }")
#         history_request = make_request(
#             sender="Risk Tier Master Orchestrator",
#             receiver="Historical Execution Intelligence Agent",
#             message_type="HISTORICAL_REQUEST",
#             release_id=normalized_release_id,
#             data={"source_data": historical_source_data},
#         )
#         policy_request = make_request(
#             sender="Risk Tier Master Orchestrator",
#             receiver="Policy / Risk Appetite Calibration Agent",
#             message_type="POLICY_REQUEST",
#             release_id=normalized_release_id,
#             data={"source_data": policy_source_data, "release_type": release_type},
#         )
#         logger.INFO(f"policy_source_data : {policy_source_data}")

#         feature_response = self._run_stage(
#             state=state,
#             agent_name="Feature / Epic Change Impact Agent",
#             function=lambda: __import__(
#                 "app.agents.feature_change_agent.tools", fromlist=["handle_a2a_request"]
#             ).handle_a2a_request(feature_request),
#             stage_key="agent1",
#         )
#         criticality_response = self._run_stage(
#             state=state,
#             agent_name="Application Criticality Classification Agent",
#             function=lambda: __import__(
#                 "app.agents.criticality_agent.tools", fromlist=["handle_a2a_request"]
#             ).handle_a2a_request(criticality_request),
#             stage_key="agent2",
#         )
#         history_response = self._run_stage(
#             state=state,
#             agent_name="Historical Execution Intelligence Agent",
#             function=lambda: __import__(
#                 "app.agents.historical_agent.tools", fromlist=["handle_a2a_request"]
#             ).handle_a2a_request(history_request),
#             stage_key="agent3",
#         )
#         policy_response = self._run_stage(
#             state=state,
#             agent_name="Policy / Risk Appetite Calibration Agent",
#             function=lambda: __import__(
#                 "app.agents.policy_agent.tools", fromlist=["handle_a2a_request"]
#             ).handle_a2a_request(policy_request),
#             stage_key="agent4",
#         )

#         logger.INFO(f"policy_source_data : {policy_source_data}")

#         state.change_impact = feature_response.data
#         state.criticality = criticality_response.data
#         state.history = history_response.data
#         state.policy = policy_response.data

#         policy_payload = state.policy.get(
#             "agent_output",
#             state.policy,
#         )

#         self._send_message(
#             sender=(
#                 "Feature / Epic Change Impact Agent"
#             ),
#             receiver=(
#                 "Decision Engine / Risk Scoring Agent"
#             ),
#             message_type="CHANGE_IMPACT_READY",
#             payload={
#                 "release_id": (
#                     normalized_release_id
#                 ),
#                 "direct_test_ids": (
#                     state.change_impact.get(
#                         "direct_test_ids",
#                         [],
#                     )
#                 ),
#                 "downstream_test_ids": (
#                     state.change_impact.get(
#                         "downstream_test_ids",
#                         [],
#                     )
#                 ),
#                 "new_feature_test_ids": (
#                     state.change_impact.get(
#                         "new_feature_test_ids",
#                         [],
#                     )
#                 ),
#                 "changed_requirement_ids": (
#                     state.change_impact.get(
#                         "changed_requirement_ids",
#                         [],
#                     )
#                 ),
#                 "traceability_gaps": (
#                     state.change_impact.get(
#                         "traceability_gaps",
#                         [],
#                     )
#                 ),
#             },
#         )
#         self._send_message(
#             sender=(
#                 "Application Criticality "
#                 "Classification Agent"
#             ),
#             receiver=(
#                 "Decision Engine / Risk Scoring Agent"
#             ),
#             message_type="CRITICALITY_READY",
#             payload={
#                 "release_id": (
#                     normalized_release_id
#                 ),
#                 "test_tags": (
#                     state.criticality.get(
#                         "test_tags",
#                         {},
#                     )
#                 ),
#                 "module_assignments": (
#                     state.criticality.get(
#                         "module_assignments",
#                         {},
#                     )
#                 ),
#             },
#         )
#         self._send_message(
#             sender=(
#                 "Historical Execution "
#                 "Intelligence Agent"
#             ),
#             receiver=(
#                 "Decision Engine / Risk Scoring Agent"
#             ),
#             message_type="HISTORY_READY",
#             payload={
#                 "release_id": (
#                     normalized_release_id
#                 ),
#                 "test_summaries": (
#                     state.history.get(
#                         "test_summaries",
#                         {},
#                     )
#                 ),
#                 "historical_summary": (
#                     state.history.get(
#                         "summary",
#                         {},
#                     )
#                 ),
#             },
#         )
#         self._send_message(
#             sender=(
#                 "Policy / Risk Appetite "
#                 "Calibration Agent"
#             ),
#             receiver=(
#                 "Decision Engine / Risk Scoring Agent"
#             ),
#             message_type="POLICY_READY",
#             payload={
#                 "release_id": (
#                     normalized_release_id
#                 ),
#                 "release_type": (
#                     policy_payload.get(
#                         "release_type",
#                         release_type,
#                     )
#                 ),
#                 "overall_max_exclusion": (
#                     policy_payload.get(
#                         "overall_max_exclusion",
#                         state.policy.get(
#                             "overall_max_exclusion",
#                             0,
#                         ),
#                     )
#                 ),
#                 "regulatory_test_ids": (
#                     policy_payload.get(
#                         "regulatory_test_ids",
#                         sorted(
#                             state.policy.get(
#                                 "regulatory_tests",
#                                 {},
#                             ).keys()
#                         ),
#                     )
#                 ),
#                 "mandatory_test_ids": (
#                     policy_payload.get(
#                         "mandatory_test_ids",
#                         state.policy.get(
#                             "mandatory_test_ids",
#                             [],
#                         ),
#                     )
#                 ),
#             },
#         )

#         # =====================================================
#         # Agent 5: Decision Engine / Risk Scoring
#         # =====================================================
#         # The Scoring Agent historically expected scoring_weights and
#         # thresholds to be present in source_data. The current Scoring Agent
#         # can use internal defaults, but the Master Orchestrator explicitly
#         # supplies a complete configuration here so both contracts work and
#         # the pipeline cannot fail merely because the configuration blocks
#         # were omitted from Jira-backed source data.
#         scoring_source_data = (
#             self._load_source_data(
#                 SCORING_INPUT_BLOCKS
#             )
#         )

#         configured_weights = (
#             policy_payload.get("scoring_weights")
#             or policy_payload.get("weights")
#             or policy_payload.get("risk_score_weights")
#             or []
#         )
#         configured_thresholds = (
#             policy_payload.get("thresholds")
#             or policy_payload.get("risk_thresholds")
#             or []
#         )

#         if isinstance(configured_weights, dict):
#             configured_weights = [
#                 {"Factor": factor, "Weight": value}
#                 for factor, value in configured_weights.items()
#             ]
#         elif not isinstance(configured_weights, list):
#             configured_weights = []

#         if isinstance(configured_thresholds, dict):
#             configured_thresholds = [
#                 {"Classification": classification, "Minimum_Score": value}
#                 for classification, value in configured_thresholds.items()
#             ]
#         elif not isinstance(configured_thresholds, list):
#             configured_thresholds = []

#         # Use documented defaults when the Policy Agent does not provide an
#         # explicit scoring configuration. Convert the dictionaries to row
#         # format because the Scoring Agent supports list-of-row inputs.
#         if not configured_weights:
#             configured_weights = [
#                 {"Factor": factor, "Weight": value}
#                 for factor, value in DEFAULT_WEIGHTS.items()
#             ]
#         if not configured_thresholds:
#             configured_thresholds = [
#                 {"Classification": classification, "Minimum_Score": value}
#                 for classification, value in DEFAULT_THRESHOLDS.items()
#             ]

#         scoring_source_data["scoring_weights"] = configured_weights
#         scoring_source_data["thresholds"] = configured_thresholds

#         # A2A: Master -> Scoring Agent with all required upstream outputs.
#         scoring_request = make_request(
#             sender="Risk Tier Master Orchestrator",
#             receiver="Decision Engine / Risk Scoring Agent",
#             message_type="SCORING_REQUEST",
#             release_id=normalized_release_id,
#             data={
#                 "source_data": scoring_source_data,
#                 "change_impact": state.change_impact,
#                 "criticality": state.criticality,
#                 "history": state.history,
#                 "policy": state.policy,
#             },
#         )
#         logger.INFO(f"scoring_request : {scoring_request }")
#         scoring_response = self._run_stage(
#             state=state,
#             agent_name="Decision Engine / Risk Scoring Agent",
#             function=lambda: __import__(
#                 "app.agents.scoring_agent.tools", fromlist=["handle_a2a_request"]
#             ).handle_a2a_request(scoring_request),
#             stage_key="agent5",
#         )
#         state.scoring = scoring_response.data

#         scoring_payload = state.scoring.get(
#             "agent_output",
#             state.scoring,
#         )

#         scoring_results = scoring_payload.get(
#             "results",
#             state.scoring.get(
#                 "results",
#                 [],
#             ),
#         )
#         logger.INFO(f"scoring_results : {scoring_results }")

#         if not isinstance(
#             scoring_results,
#             list,
#         ):
#             raise TypeError(
#                 "Scoring Agent results must be a list."
#             )

#         # Persist an exact population reconciliation in PipelineState so the
#         # final report and post-run conversational queries can explain any
#         # Change Impact -> Scoring population difference without rerunning Jira.
#         change_payload_for_reconciliation = self._unwrap_agent_output(state.change_impact)
#         direct_ids_for_reconciliation = {
#             self._normalize_test_id(value)
#             for value in change_payload_for_reconciliation.get("direct_test_ids", [])
#             if self._normalize_test_id(value)
#         }
#         scored_ids_for_reconciliation = {
#             self._normalize_test_id(row.get("test_case_id"))
#             for row in scoring_results
#             if isinstance(row, dict) and self._normalize_test_id(row.get("test_case_id"))
#         }
#         state.scoring["population_reconciliation"] = {
#             "direct_test_count": len(direct_ids_for_reconciliation),
#             "scored_test_count": len(scored_ids_for_reconciliation),
#             "missing_from_scoring": sorted(direct_ids_for_reconciliation - scored_ids_for_reconciliation),
#             "outside_direct_impact": sorted(scored_ids_for_reconciliation - direct_ids_for_reconciliation),
#         }

#         # Governance reviews only final EXCLUDE classifications.
#         candidate_test_ids = [
#             row.get(
#                 "test_case_id"
#             )
#             for row in scoring_results
#             if (
#                 row.get(
#                     "classification"
#                 )
#                 == "EXCLUDE"
#                 and row.get(
#                     "test_case_id"
#                 )
#             )
#         ]

#         self._send_message(
#             sender=(
#                 "Decision Engine / Risk Scoring Agent"
#             ),
#             receiver=(
#                 "Exclusion Risk & Governance Agent"
#             ),
#             message_type="SCORING_COMPLETE",
#             payload={
#                 "release_id": (
#                     normalized_release_id
#                 ),
#                 "summary": (
#                     scoring_payload.get(
#                         "summary",
#                         state.scoring.get(
#                             "summary",
#                             {},
#                         ),
#                     )
#                 ),
#                 "candidate_test_ids": (
#                     candidate_test_ids
#                 ),
#             },
#         )

#         # =====================================================
#         # Agent 6: Exclusion Risk & Governance
#         # =====================================================
#         # A2A: Master -> Governance Agent.
#         governance_request = make_request(
#             sender="Risk Tier Master Orchestrator",
#             receiver="Exclusion Risk & Governance Agent",
#             message_type="GOVERNANCE_REQUEST",
#             release_id=normalized_release_id,
#             data={"scoring": state.scoring, "policy": state.policy},
#         )
#         policy_data = state.policy
#         logger.INFO(f"state.policy : {policy_dat}")
#         governance_response = self._run_stage(
#             state=state,
#             agent_name="Exclusion Risk & Governance Agent",
#             function=lambda: __import__(
#                 "app.agents.governance_agent.tools", fromlist=["handle_a2a_request"]
#             ).handle_a2a_request(governance_request),
#             stage_key="agent6",
#         )
#         logger.IFO(f"governance_response : {governance_response }")
#         state.governance = governance_response.data

#         self._send_message(
#             sender=(
#                 "Exclusion Risk & Governance Agent"
#             ),
#             receiver=(
#                 "Risk Tier Master Orchestrator"
#             ),
#             message_type="GOVERNANCE_COMPLETE",
#             payload={
#                 "release_id": (
#                     normalized_release_id
#                 ),
#                 "summary": (
#                     state.governance.get(
#                         "summary",
#                         {},
#                     )
#                 ),
#             },
#         )

#         # Store all A2A-style messages in pipeline state.
#         state.messages = list(
#             self.message_bus.messages
#         )

#         # =====================================================
#         # Report generation
#         # =====================================================
#         report_started_at = datetime.now(
#             timezone.utc
#         )

#         _LEDGER_NAME = "Immutable Audit Ledger"
#         self._emit_stage("ledger", "running", "Writing decisions to the audit ledger…", agent_name=_LEDGER_NAME)

#         try:
#             state.report_files = (
#                 self.report_generator.generate(
#                     state
#                 )
#             )

#             state.audit_log.append(
#                 AgentRun(
#                     agent="Report Generator",
#                     status="COMPLETED",
#                     summary=(
#                         state.report_files
#                     ),
#                     started_at=(
#                         report_started_at
#                     ),
#                     completed_at=datetime.now(
#                         timezone.utc
#                     ),
#                 )
#             )

#         except Exception as exc:
#             state.audit_log.append(
#                 AgentRun(
#                     agent="Report Generator",
#                     status="FAILED",
#                     summary={
#                         "error_type": (
#                             type(exc).__name__
#                         ),
#                         "error": str(exc),
#                     },
#                     started_at=(
#                         report_started_at
#                     ),
#                     completed_at=datetime.now(
#                         timezone.utc
#                     ),
#                 )
#             )

#             self._emit_stage("ledger", "failed", f"Audit ledger write failed: {exc}", agent_name=_LEDGER_NAME)

#             raise

#         # Cache only fully completed pipelines for post-run ADK queries.
#         # A2A: subsequent specialist questions consume this exact snapshot.
#         self._cache_completed_pipeline(
#             state=state,
#             source_data=self._jira_source_data,
#         )

#         self._emit_stage("ledger", "finished", "Audit ledger updated.", agent_name=_LEDGER_NAME)

#         return state

    

# def execute_risk_tier_pipeline(
#     jira_link: str,
#     release_id: str | None = None,
# ) -> dict[str, Any]:
#     """
#     ADK-facing entry point for the complete Risk Tier pipeline.

#     The detailed pipeline state remains inside Python/report files. Only a
#     compact summary is returned to the ADK model so the tool response does not
#     exceed the model message-size limit.
#     """
#     settings = get_settings()

#     normalized_jira_link = str(jira_link or "").strip()
#     if not normalized_jira_link:
#         return {
#             "status": "needs_input",
#             "message": "Please provide the Jira link.",
#         }

#     link_ctx = parse_jira_link(normalized_jira_link)
#     normalized_release_id = str(
#         release_id
#         or (link_ctx.release_label if link_ctx else "")
#         or settings.default_release
#         or ""
#     ).strip().upper()

#     if not normalized_release_id:
#         return {
#             "status": "needs_input",
#             "message": "Please provide the release ID.",
#         }

#     try:
#         state = (
#             RiskTierMasterOrchestrator
#             .from_settings(
#                 settings=settings,
#                 jira_link=normalized_jira_link,
#             )
#             .execute(normalized_release_id)
#         )

#         scoring = state.scoring or {}
#         policy = state.policy or {}
#         history = state.history or {}
#         criticality = state.criticality or {}
#         change_impact = state.change_impact or {}
#         governance = state.governance or {}

#         return {
#             "status": "success",
#             "release_id": state.release_id,
#             "summary": state.summary(),
#             "change_impact_summary": change_impact.get(
#                 "summary", {}
#             ),
#             "criticality_summary": criticality.get(
#                 "summary", {}
#             ),
#             "historical_summary": history.get(
#                 "summary", {}
#             ),
#             "policy_summary": policy.get(
#                 "summary", {}
#             ),
#             "classification_summary": scoring.get(
#                 "summary", {}
#             ),
#             "governance_summary": governance.get(
#                 "summary", {}
#             ),
#             "report_files": state.report_files or {},
#         }

#     except Exception as exc:
#         return {
#             "status": "error",
#             "release_id": normalized_release_id,
#             "error_type": type(exc).__name__,
#             "message": str(exc),
#         }



######################################################################################################################################################






from __future__ import annotations

import importlib
import inspect
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import logging
import random
import time

# Plain logging.getLogger(__name__) has no handler anywhere in this app —
# nothing calls logging.basicConfig(), so every logger.info() call here was
# silently swallowed by Python's WARNING-level "handler of last resort"
# (only logger.warning()/error() ever reached the terminal). get_logger()
# attaches a real stdout StreamHandler at INFO level, the same setup every
# agent tools.py module already uses via app.observability.logger — this
# is what actually makes cached-query logging (get_cached_agent_context,
# answer_agent_question, _detect_query_agents) visible in the terminal.
from app.logging_config import get_logger

logger = get_logger(__name__)

from app.agents.criticality_agent.tools import (
    classify_application_criticality,
)
from app.agents.feature_change_agent.tools import (
    analyze_release_scope,
    derive_release_test_cases,
)
from app.agents.governance_agent.tools import (
    evaluate_exclusion_governance,
)
from app.agents.historical_agent.tools import (
    analyze_historical_execution,
)
from app.agents.policy_agent.tools import (
    calibrate_risk_policy,
)
from app.agents.scoring_agent.tools import (
    DEFAULT_THRESHOLDS,
    DEFAULT_WEIGHTS,
    calculate_test_selection,
)
from google.adk.tools.tool_context import ToolContext

from app.config import Settings, get_settings
from app.models import A2AResponse, AgentRun, PipelineState
from app.reports import ReportGenerator
from app.integrations.mcp_jira_client import MCPJiraClient
from app.integrations.jira_link import parse_jira_link
from app.services import InMemoryMessageBus
from app.services.a2a import make_request
from app.persistence.jira_cache_repository import get_jira_cache_repository
from app.persistence.errors import ReleaseDataUnavailableError
from app import tracing




# Post-run query cache.
# The ADK conversational process creates a fresh orchestrator wrapper for each
# tool call, so completed pipeline state and the exact Master-owned Jira snapshot
# must live at module scope. This prevents drill-down questions from re-running
# the complete six-agent pipeline.
_PIPELINE_STATE_CACHE: dict[str, PipelineState] = {}
_PIPELINE_SOURCE_CACHE: dict[str, dict[str, list[dict[str, Any]]]] = {}

# Jira-source cache: reuse a release's Jira/MCP snapshot across separate
# execute() calls within a bounded TTL (settings.jira_source_cache_ttl_seconds)
# instead of re-running the full paginated project-wide issue fetch + dynamic
# field discovery every time — that load alone can take many minutes on a
# large project. Deliberately separate from _PIPELINE_SOURCE_CACHE above,
# which is only populated after a FULLY successful run; this one is populated
# right after the Jira fetch itself succeeds, so a retry after a later-stage
# failure (e.g. a bad Release_Type) still benefits from it. Keyed by
# (jira_project_key, release_id) since a fresh orchestrator is constructed
# per request and could in principle target a different Jira project.
#
# Trade-off, by design: within the TTL window, a re-run of the same release
# will NOT pick up intervening Jira changes (new/removed test cases, an
# edited Release_Type, etc.) — this intentionally relaxes the "always fetch
# a fresh snapshot" guarantee described in app/prompts/master_orchestrator.md,
# in exchange for not re-paying the full Jira load on every request.
_JIRA_SOURCE_CACHE: dict[tuple[str, str], tuple[float, dict[str, list[dict[str, Any]]]]] = {}


def _query_snapshot_path(output_dir: str | Path, release_id: str) -> Path:
    """Return the durable post-run query snapshot path."""
    normalized = str(release_id or "").strip().upper()
    if not normalized:
        raise ValueError("release_id cannot be empty.")
    return Path(output_dir) / f"{normalized}_master_query_snapshot.json"


def _write_query_snapshot(
    output_dir: str | Path,
    state: PipelineState,
    source_data: dict[str, list[dict[str, Any]]],
) -> None:
    """Persist the completed Master state for cross-process ADK queries.

    ADK tool calls are not guaranteed to execute in the same Python process, so
    an in-memory module cache alone is insufficient. The snapshot contains the
    completed PipelineState plus the exact Master-owned Jira logical blocks used
    by the pipeline.
    """
    path = _query_snapshot_path(output_dir, state.release_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "release_id": state.release_id,
        "state": state.model_dump(mode="json"),
        "source_data": {
            str(key): list(value)
            for key, value in source_data.items()
            if isinstance(value, list)
        },
    }

    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    temp_path.replace(path)


def _load_query_snapshot(
    output_dir: str | Path,
    release_id: str,
) -> tuple[PipelineState | None, dict[str, list[dict[str, Any]]]]:
    """Load a durable query snapshot, falling back to the generated report."""
    path = _query_snapshot_path(output_dir, release_id)
    if not path.is_file():
        # Backward-compatible fallback for runs produced before the durable
        # query snapshot was introduced. The report contains the full pipeline
        # state, including scoring results and change-impact IDs.
        report_path = path.parent / f"{str(release_id).strip().upper()}_risk_tier_report.json"
        if not report_path.is_file():
            return None, {}
        try:
            report_payload = json.loads(report_path.read_text(encoding="utf-8"))
            state = PipelineState.model_validate(report_payload)
            return state, {}
        except Exception:
            return None, {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        state_payload = payload.get("state", payload)
        state = PipelineState.model_validate(state_payload)
        raw_source = payload.get("source_data", {})
        source_data = {
            str(key): list(value)
            for key, value in raw_source.items()
            if isinstance(value, list)
        } if isinstance(raw_source, dict) else {}
        return state, source_data
    except Exception:
        return None, {}


JIRA_SOURCE_BLOCKS = {
    "releases", "modules", "epics", "stories", "requirements", "rtm",
    "test_cases", "release_scope", "dependencies", "out_of_scope",
    "criticality_factors", "tier_change_log", "executions", "defects",
    "flaky_tests", "policies", "regulatory_tests", "release_rules",
}

FEATURE_INPUT_BLOCKS: tuple[str, ...] = (
    "releases",
    "epics",
    "stories",
    "requirements",
    "rtm",
    "test_cases",
    "release_scope",
    "dependencies",
    "out_of_scope",
)

CRITICALITY_INPUT_BLOCKS: tuple[str, ...] = (
    "modules",
    "test_cases",
)

HISTORICAL_INPUT_BLOCKS: tuple[str, ...] = (
    "test_cases",
    "executions",
    "defects",
    "flaky_tests",
)

POLICY_INPUT_BLOCKS: tuple[str, ...] = (
    "policies",
    "regulatory_tests",
    "release_rules",
)

SCORING_INPUT_BLOCKS: tuple[str, ...] = (
    "test_cases",
)

# Fields kept per scored test when a cached-query answer needs the scoring
# results list — drops the verbose per-row extras (score_components,
# execution_minutes, automation_status, ...) that make the full row too
# large to serialize at scale. Shared by get_cached_agent_context's
# "optional_scores" question kind and its scoring/selection agent_output.
_SCORING_RESULT_FIELDS: tuple[str, ...] = (
    "test_case_id", "test_name", "classification", "base_classification",
    "composite_score", "change_impact_factor", "criticality_factor",
    "historical_value_score", "historical_value_factor", "release_risk_factor",
    "tier", "risk_band", "protection_flags", "reasons",
)

# get_cached_agent_context's conversational safety cap. 100k chars (roughly
# 25-30k tokens) was conservative enough that a normal-sized release's full
# scoring results — the largest of any agent's cached output — could tip
# over it even after compaction, silently dropping agent_output entirely
# for a perfectly valid, completed run. Modern LLM context windows hold far
# more than this; the cap only needs to guard against a genuinely
# degenerate payload, not a real release's worth of scored tests.
_CACHED_CONTEXT_MAX_CHARS: int = 250_000


class RiskTierMasterOrchestrator:
    """
    Coordinate all Risk Tier stages in the required business order.

    The Master Orchestrator coordinates Jira/MCP-backed raw data only. Each specialist stage receives serializable logical data
    blocks and/or structured outputs from earlier stages.

    Execution order:

    1. Feature / Epic Change Impact
    2. Application Criticality
    3. Historical Execution Intelligence
    4. Policy / Risk Appetite
    5. Decision Engine / Risk Scoring
    6. Exclusion Risk & Governance
    7. Report Generation
    """

    name = "Risk Tier Master Orchestrator"

    def __init__(
        self,
        output_dir: str | Path,
        jira_client: MCPJiraClient | None = None,
        jira_project_key: str = "",
        jira_release_label: str = "",
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.jira_client = jira_client
        self.jira_project_key = str(jira_project_key or "").strip()
        self.jira_release_label = str(jira_release_label or "").strip()
        self._jira_field_ids: dict[str, str] | None = None
        self._jira_source_data: dict[str, list[dict[str, Any]]] = {}

        # Optional real-time progress callback for AG-UI streaming. Set per
        # execute() call; a no-op for every existing caller that doesn't pass
        # one (CLI, plain REST /analyze). agent_name is the human-readable
        # name of whichever agent this update is about (e.g. "Feature / Epic
        # Change Impact Agent"), separate from stage_key's stable routing id.
        self._on_stage: Callable[[str, str, str, str | None, dict[str, Any] | None], None] | None = None

        # Ordered record of every A2A payload sent to or received from each
        # agent during the most recent execute() call — reset at the start of
        # each run and persisted to <RELEASE>_agent_io_trace.json at the end
        # (see _log_a2a_payload / _write_agent_io_trace), so the exact data
        # exchanged with every agent can be inspected after the fact.
        self._agent_io_trace: list[dict[str, Any]] = []

        self.message_bus = InMemoryMessageBus()
        self.report_generator = ReportGenerator(self.output_dir)

    def _emit_stage(
        self,
        stage_key: str,
        status: str,
        text: str,
        agent_name: str | None = None,
        event_type: str | None = None,
    ) -> None:
        """
        Best-effort progress emit; never let a UI callback break a run.

        event_type feeds the SSE-visible envelope's event_type field,
        alongside run_id/trace_id pulled from self._run_trace — this is
        what lets the frontend see the same run/trace identifiers and
        event vocabulary the backend writes to disk (see
        app/agents/pipeline_stream_agent.py's on_stage). Defaults to
        AGENT_PROGRESS: the structural AGENT_STARTED/AGENT_FINISHED/
        AGENT_FAILED/RUN_STARTED/RUN_FINISHED/RUN_ERROR events are already
        emitted directly by app.tracing (start_agent_trace/
        finish_agent_trace/start_run/finish_run — see _run_stage and
        execute()), so every existing call site here stays exactly what it
        already was: a human-readable narration channel, not a second,
        duplicate structural event for the same moment.
        """
        if self._on_stage is None:
            return

        run_trace = getattr(self, "_run_trace", None)
        envelope: dict[str, Any] = {"event_type": event_type or "AGENT_PROGRESS"}
        if run_trace is not None:
            envelope["run_id"] = run_trace.run_id
            envelope["trace_id"] = run_trace.trace_id

        try:
            self._on_stage(stage_key, status, text, agent_name, envelope)
        except Exception:
            logger.debug("on_stage callback raised", exc_info=True)

    def _record_cache_event(
        self,
        hit: bool,
        cache_name: str,
        key: str,
        **extra: Any,
    ) -> None:
        """Best-effort CACHE_HIT/CACHE_MISS event; never lets a tracing bug
        affect the real cache-resolution logic in _prepare_jira_source_data."""
        run_trace = getattr(self, "_run_trace", None)
        if run_trace is None:
            return
        try:
            tracing.record_cache_event(run_trace, hit=hit, cache_name=cache_name, key=key, **extra)
        except Exception:
            logger.exception("tracing: failed to record cache event for %s", cache_name)

    def _log_a2a_payload(
        self,
        direction: str,
        agent_name: str,
        payload: Any,
    ) -> None:
        """Log the complete A2A payload sent to or returned from an agent.

        Also records it into self._agent_io_trace so the full input/output
        exchanged with every agent in the current run can be persisted to
        disk afterward — see _write_agent_io_trace.
        """
        try:
            if hasattr(payload, "model_dump") and callable(payload.model_dump):
                serializable = payload.model_dump(mode="json", exclude_none=True)
            else:
                serializable = payload

            logger.info("=" * 100)
            logger.info("A2A %s | %s", direction, agent_name)
            logger.info(
                json.dumps(
                    serializable,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
            logger.info("=" * 100)
        except Exception as exc:
            serializable = repr(payload)
            logger.warning(
                "Unable to serialize A2A %s payload for %s: %s",
                direction,
                agent_name,
                exc,
            )
            logger.info("A2A %s | %s | raw=%r", direction, agent_name, payload)

        self._agent_io_trace.append(
            {
                "sequence": len(self._agent_io_trace) + 1,
                "direction": direction,
                "agent": agent_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": serializable,
            }
        )

        run_trace = getattr(self, "_run_trace", None)
        if run_trace is not None:
            # direction is always relative to the specialist named by
            # agent_name here: INPUT = Master -> agent, OUTPUT = agent -> Master.
            source_agent = "Master Orchestrator" if direction == "INPUT" else agent_name
            destination_agent = agent_name if direction == "INPUT" else "Master Orchestrator"
            try:
                tracing.record_a2a(
                    run_trace,
                    "A2A_REQUEST" if direction == "INPUT" else "A2A_RESPONSE",
                    source_agent=source_agent,
                    destination_agent=destination_agent,
                    payload=serializable,
                )
            except Exception:
                logger.exception("tracing: failed to record A2A event for %s/%s", direction, agent_name)

    @staticmethod
    def _agent_slug(agent_name: str) -> str:
        """Filesystem-safe short form of an agent's display name."""
        slug = re.sub(r"[^a-z0-9]+", "_", str(agent_name or "").strip().lower()).strip("_")
        return slug or "agent"

    def _write_agent_io_trace(self, release_id: str) -> Path | None:
        """Persist the current run's full per-agent input/output trace to disk.

        Written as one plain .txt file **per agent** (rather than a single
        combined file) — each one small enough to read on its own — plus a
        short index file listing every agent in execution order with its
        file name, so the overall flow is still visible at a glance without
        opening every file. All files are overwritten on each run.
        """
        if not self._agent_io_trace:
            return None

        normalized = str(release_id or "").strip().upper()

        # Group entries by agent, preserving first-seen (execution) order.
        by_agent: dict[str, list[dict[str, Any]]] = {}
        agent_order: list[str] = []
        for entry in self._agent_io_trace:
            agent = entry["agent"]
            if agent not in by_agent:
                by_agent[agent] = []
                agent_order.append(agent)
            by_agent[agent].append(entry)

        written: list[tuple[str, Path]] = []
        for agent in agent_order:
            slug = self._agent_slug(agent)
            path = self.output_dir / f"{normalized}_agent_io_trace_{slug}.txt"
            lines: list[str] = [
                f"Agent I/O trace — release {normalized}",
                f"Agent: {agent}",
                f"Exchanges: {len(by_agent[agent])}",
                "",
            ]
            for entry in by_agent[agent]:
                lines.append("=" * 100)
                lines.append(
                    f"[{entry['sequence']}] {entry['direction']} | {entry['agent']} | {entry['timestamp']}"
                )
                lines.append("=" * 100)
                try:
                    lines.append(
                        json.dumps(entry["payload"], ensure_ascii=False, indent=2, default=str)
                    )
                except Exception:
                    lines.append(repr(entry["payload"]))
                lines.append("")

            try:
                path.write_text("\n".join(lines), encoding="utf-8")
            except Exception:
                logger.exception("Failed to write agent I/O trace for %s / %s", normalized, agent)
                continue
            written.append((agent, path))

        if not written:
            return None

        index_path = self.output_dir / f"{normalized}_agent_io_trace_index.txt"
        index_lines: list[str] = [
            f"Agent I/O trace index — release {normalized}",
            f"Generated at: {datetime.now(timezone.utc).isoformat()}",
            "Agents, in execution order:",
            "",
        ]
        for position, (agent, path) in enumerate(written, start=1):
            index_lines.append(f"{position}. {agent} -> {path.name}")

        try:
            index_path.write_text("\n".join(index_lines), encoding="utf-8")
        except Exception:
            logger.exception("Failed to write agent I/O trace index for %s", normalized)
            return written[0][1]

        return index_path

    @classmethod
    def from_settings(
        cls,
        settings: Settings | None = None,
        jira_link: str | None = None,
    ) -> "RiskTierMasterOrchestrator":
        """Create a Jira/MCP-only orchestrator."""
        resolved_settings = settings or get_settings()
        link_ctx = parse_jira_link(jira_link) if jira_link else None

        resolved_project_key = (
            link_ctx.project_key
            if link_ctx and link_ctx.project_key
            else resolved_settings.jira_project_key
        )
        resolved_release_label = (
            (link_ctx.release_label if link_ctx and link_ctx.release_label else None)
            or resolved_settings.default_release
        )

        if not resolved_project_key:
            raise RuntimeError(
                "JIRA_PROJECT_KEY or a Jira link containing the project key is required."
            )

        return cls(
            output_dir=resolved_settings.output_dir,
            jira_client=MCPJiraClient(),
            jira_project_key=str(resolved_project_key),
            jira_release_label=str(resolved_release_label or ""),
        )

    @classmethod
    def for_query(cls) -> "RiskTierMasterOrchestrator":
        """Create a lightweight orchestrator wrapper for internal helpers.

        Conversational follow-up questions are handled by the direct query
        tools registered in ``app.orchestrator.tools``. This wrapper remains
        available for backward compatibility and for internal callers that
        need access to the Master caches without creating a Jira client.
        """
        settings = get_settings()
        return cls(output_dir=settings.output_dir)

    @classmethod
    def get_cached_state(
        cls,
        release_id: str,
    ) -> PipelineState | None:
        normalized = str(release_id or "").strip().upper()
        state = _PIPELINE_STATE_CACHE.get(normalized)
        if state is not None:
            return state

        # Cross-process fallback: ADK may invoke the follow-up tool in another
        # worker, so recover the completed state from the durable snapshot.
        settings = get_settings()
        loaded_state, loaded_source = _load_query_snapshot(
            settings.output_dir,
            normalized,
        )
        if loaded_state is not None:
            _PIPELINE_STATE_CACHE[normalized] = loaded_state
            _PIPELINE_SOURCE_CACHE[normalized] = loaded_source
        return loaded_state

    @classmethod
    def get_cached_source_data(
        cls,
        release_id: str,
    ) -> dict[str, list[dict[str, Any]]]:
        normalized = str(release_id or "").strip().upper()
        source_data = _PIPELINE_SOURCE_CACHE.get(normalized)
        if source_data:
            return source_data

        settings = get_settings()
        loaded_state, loaded_source = _load_query_snapshot(
            settings.output_dir,
            normalized,
        )
        if loaded_state is not None:
            _PIPELINE_STATE_CACHE[normalized] = loaded_state
            _PIPELINE_SOURCE_CACHE[normalized] = loaded_source
        return loaded_source

    @staticmethod
    def _compact_row(row: Any, keys: tuple[str, ...]) -> dict[str, Any]:
        if not isinstance(row, dict):
            return {"value": str(row)}
        compact: dict[str, Any] = {}
        for key in keys:
            value = row.get(key)
            if value not in (None, "", [], {}):
                compact[key] = value
        return compact

    @staticmethod
    def _question_kind(question: str) -> str:
        q = str(question or "").lower()
        if "epic" in q and "story" in q and "test" in q:
            return "traceability"
        if "optional" in q and ("score" in q or "composite" in q):
            return "optional_scores"
        if "directly impacted" in q and ("classified" in q or "difference" in q or "only" in q):
            return "population_reconciliation"
        if "new-feature" in q or "new feature" in q:
            return "new_feature_tests"
        if "flaky" in q:
            return "flaky"
        if "insufficient history" in q or "insufficient-history" in q:
            return "insufficient_history"
        if "defect protected" in q or "confirmed defect" in q:
            return "defect_protection"
        # "tier" alone is too broad a signal: a scoring/protection question
        # like "which Tier-1 tests were prevented from being downgraded
        # during scoring?" mentions a tier but is not a criticality-tier-
        # matrix question — only classify as "criticality" on a bare "tier"
        # mention when nothing else marks it as a scoring/protection/
        # exclusion question instead (those are handled by their own agent).
        if "criticality" in q or (
            "tier" in q
            and not any(
                keyword in q
                for keyword in ("scor", "protect", "downgrad", "exclu", "govern", "flag")
            )
        ):
            return "criticality"
        if "policy" in q or "regulatory" in q or "mandatory" in q:
            return "policy"
        if "governance" in q or "approval" in q:
            return "governance"
        return "general"

    def get_cached_agent_context(
        self,
        release_id: str,
        agent: str,
        question: str = "",
    ) -> dict[str, Any]:
        """Return a compact, question-specific projection of completed pipeline cache.

        This method never queries Jira and never reruns the pipeline. It is deliberately
        bounded so its result cannot flood the ADK/LLM context window.
        """
        normalized_release_id = str(release_id or "").strip().upper()
        normalized_agent = str(agent or "").strip().lower()
        logger.info(
            "CACHED_QUERY_STARTED | release=%s | agent=%s | question=%r",
            normalized_release_id, normalized_agent, question,
        )
        state = self.get_cached_state(normalized_release_id)
        if state is None:
            logger.warning(
                "CACHED_QUERY_NO_CACHE | release=%s | agent=%s",
                normalized_release_id, normalized_agent,
            )
            raise RuntimeError(
                f"No completed pipeline cache exists for {normalized_release_id}. "
                "Run execute_risk_tier_pipeline first."
            )

        kind = self._question_kind(question)
        logger.info(
            "CACHED_QUERY_KIND_RESOLVED | release=%s | agent=%s | kind=%s",
            normalized_release_id, normalized_agent, kind,
        )
        change = self._unwrap_agent_output(state.change_impact)
        criticality = self._unwrap_agent_output(state.criticality)
        history = self._unwrap_agent_output(state.history)
        policy = self._unwrap_agent_output(state.policy)
        scoring = self._unwrap_agent_output(state.scoring)
        governance = self._unwrap_agent_output(state.governance)
        cached_source = self.get_cached_source_data(normalized_release_id)

        result: dict[str, Any] = {
            "source": "MASTER_PIPELINE_CACHE",
            "cache_only": True,
            "release_id": normalized_release_id,
            "agent": normalized_agent,
            "question_kind": kind,
        }

        if kind == "traceability":
            epics = []
            for row in cached_source.get("epics", []):
                epics.append(self._compact_row(row, ("Epic_ID", "Epic ID", "work_item_id", "issue_key", "summary", "Epic_Name", "Epic Name")))
            stories = []
            for row in cached_source.get("stories", []):
                stories.append(self._compact_row(row, ("User_Story_ID", "Story_ID", "User Story ID", "work_item_id", "issue_key", "Epic_ID", "Epic ID", "summary", "User_Story_Name", "Story Name")))
            requirements = []
            for row in cached_source.get("requirements", []):
                requirements.append(self._compact_row(row, ("Requirement_ID", "Requirement ID", "work_item_id", "issue_key", "User_Story_ID", "Story_ID", "User Story ID", "summary", "Requirement_Name", "Requirement Name")))
            rtm = []
            for row in cached_source.get("rtm", []):
                rtm.append(self._compact_row(row, ("Requirement_ID", "Requirement ID", "Test_Case_ID", "Test Case ID", "Mapping_Type", "Mapping Type", "Mapping_Status", "Mapping Status")))
            result["traceability"] = {
                "epics": epics,
                "stories": stories,
                "requirements": requirements,
                "rtm": rtm,
            }

        elif kind == "optional_scores":
            rows = []
            for row in scoring.get("results", []):
                if isinstance(row, dict) and str(row.get("classification") or "").strip().upper() == "OPTIONAL":
                    rows.append(self._compact_row(row, _SCORING_RESULT_FIELDS))
            scores = [float(r["composite_score"]) for r in rows if r.get("composite_score") not in (None, "")]
            result["optional_scores"] = rows
            result["summary"] = {
                "count": len(rows),
                "min": min(scores) if scores else None,
                "max": max(scores) if scores else None,
                "average": (sum(scores) / len(scores)) if scores else None,
            }

        elif kind == "population_reconciliation":
            direct_ids = sorted({self._normalize_test_id(v) for v in change.get("direct_test_ids", []) if self._normalize_test_id(v)})
            scored_rows = [r for r in scoring.get("results", []) if isinstance(r, dict)]
            scored_ids = sorted({self._normalize_test_id(r.get("test_case_id")) for r in scored_rows if self._normalize_test_id(r.get("test_case_id"))})
            result["population_reconciliation"] = {
                "direct_count": len(direct_ids),
                "scored_count": len(scored_ids),
                "missing_from_scoring": sorted(set(direct_ids) - set(scored_ids)),
                "outside_direct_impact": sorted(set(scored_ids) - set(direct_ids)),
            }

        elif kind == "new_feature_tests":
            result["new_feature_test_ids"] = sorted({self._normalize_test_id(v) for v in change.get("new_feature_test_ids", []) if self._normalize_test_id(v)})
            result["summary"] = change.get("summary", {})

        elif kind == "flaky":
            ids = change_ids = history.get("flaky_test_ids", [])
            result["flaky_test_ids"] = sorted({self._normalize_test_id(v) for v in ids if self._normalize_test_id(v)})
            result["summary"] = history.get("summary", {})

        elif kind == "insufficient_history":
            result["insufficient_history_test_ids"] = sorted({self._normalize_test_id(v) for v in history.get("insufficient_history_test_ids", []) if self._normalize_test_id(v)})
            result["summary"] = history.get("summary", {})

        elif kind == "defect_protection":
            result["defect_protected_test_ids"] = sorted({self._normalize_test_id(v) for v in history.get("defect_protected_test_ids", []) if self._normalize_test_id(v)})
            result["summary"] = history.get("summary", {})

        elif kind == "criticality":
            result["criticality"] = {
                "summary": criticality.get("summary", {}),
                "module_assignments": criticality.get("module_assignments", {}),
                "test_tags": criticality.get("test_tags", {}),
            }

        elif kind == "policy":
            result["policy"] = {
                "summary": policy.get("summary", {}),
                "release_type": policy.get("release_type"),
                "mandatory_test_ids": policy.get("mandatory_test_ids", []),
                "regulatory_test_ids": policy.get("regulatory_test_ids", []),
            }

        elif kind == "governance":
            result["governance"] = {"summary": governance.get("summary", {})}

        # Always attach the targeted agent's own raw output, regardless of
        # `kind` — `kind` only controls which EXTRA cross-cutting summary
        # gets bolted on above for topic-specific questions (flaky, policy,
        # criticality, etc.). Previously this only ran in the `else` (i.e.
        # "kind is none of the above") branch, so any question that matched
        # one of those specific kinds silently never got agent_output at
        # all — regardless of which agent was actually targeted. That
        # caused _answer_single_agent_question's own validation (which
        # different agents check via different key names, several of them
        # via "agent_output") to fail even though a real cached result
        # existed. See e.g. a scoring/protection question that happens to
        # mention "tier" and gets classified kind="criticality".
        if normalized_agent in {"scoring", "selection"}:
            # Scoring's own agent_output.results carries every scored test
            # with verbose per-row fields (score_components, reasons,
            # protection_flags, ...) — at a few hundred tests this alone
            # already exceeds the 100k-char safety cap below, and the old
            # behavior on hitting that cap was to drop agent_output
            # entirely, making the cache look empty even though the run
            # completed fine. Compact each row to the fields a question
            # actually needs (same fields already used for the
            # "optional_scores" question kind above) so the full
            # per-test list fits comfortably under the cap instead of
            # relying on the last-resort fallback to salvage anything.
            compact_scoring = dict(scoring)
            raw_results = compact_scoring.get("results")
            if isinstance(raw_results, list):
                compact_rows = [
                    self._compact_row(row, _SCORING_RESULT_FIELDS)
                    for row in raw_results
                ]
                # "reasons" is free text (e.g. "No mapped release change
                # impact | Application criticality is TIER_4 | ...") and is
                # by far the biggest remaining contributor once every other
                # field is already compact — at ~150+ tests, the full
                # per-row reasons text alone can still push the whole
                # payload back over the cap below. The classification,
                # score, and protection flags carry the load-bearing
                # information; a shortened reason is still useful context
                # without re-inflating the payload as the suite grows.
                for compact_row in compact_rows:
                    reasons = compact_row.get("reasons")
                    if isinstance(reasons, str) and len(reasons) > 200:
                        compact_row["reasons"] = reasons[:200] + "…"
                compact_scoring["results"] = compact_rows
            result["agent_output"] = compact_scoring
        elif normalized_agent in {"history", "historical"}:
            result["agent_output"] = history
        elif normalized_agent in {"feature", "change"}:
            result["agent_output"] = change
        elif normalized_agent == "criticality":
            result["agent_output"] = criticality
        elif normalized_agent in {"policy", "risk"}:
            result["agent_output"] = policy
        elif normalized_agent in {"governance", "exclusion"}:
            result["agent_output"] = governance

        serialized = json.dumps(result, ensure_ascii=False, default=str)
        if len(serialized) > _CACHED_CONTEXT_MAX_CHARS:
            # Last-resort hard guard for whatever still doesn't fit even
            # after the scoring-results compaction above (e.g. a much
            # larger release). result.get("summary", {}) is only populated
            # for a handful of question kinds (flaky, policy, ...) — for
            # "general" questions it's always {}, so fall back to the
            # targeted agent's own agent_output.summary (every specialist
            # emits one) rather than returning an empty summary alongside
            # the "only summary metadata was returned" warning.
            agent_output = result.get("agent_output")
            agent_summary = (
                agent_output.get("summary", {})
                if isinstance(agent_output, dict)
                else {}
            )
            logger.warning(
                "CACHED_QUERY_TRUNCATED | release=%s | agent=%s | kind=%s | size=%d | cap=%d",
                normalized_release_id, normalized_agent, kind, len(serialized), _CACHED_CONTEXT_MAX_CHARS,
            )
            return {
                "source": "MASTER_PIPELINE_CACHE",
                "cache_only": True,
                "release_id": normalized_release_id,
                "agent": normalized_agent,
                "question_kind": kind,
                "warning": "The cached result was larger than the conversational safety limit; only summary metadata was returned.",
                "summary": result.get("summary") or agent_summary,
                "counts": {
                    "optional": len(result.get("optional_scores", [])),
                    "new_feature": len(result.get("new_feature_test_ids", [])),
                    "flaky": len(result.get("flaky_test_ids", [])),
                    "insufficient_history": len(result.get("insufficient_history_test_ids", [])),
                    "defect_protected": len(result.get("defect_protected_test_ids", [])),
                },
            }
        logger.info(
            "CACHED_QUERY_COMPLETED | release=%s | agent=%s | kind=%s | size=%d | has_agent_output=%s",
            normalized_release_id, normalized_agent, kind, len(serialized), "agent_output" in result,
        )
        return result

    @classmethod
    def _cache_completed_pipeline(
        cls,
        state: PipelineState,
        source_data: dict[str, list[dict[str, Any]]],
    ) -> None:
        release_id = str(state.release_id or "").strip().upper()
        if not release_id:
            return
        normalized_source = {
            key: list(value)
            for key, value in source_data.items()
            if isinstance(value, list)
        }
        _PIPELINE_STATE_CACHE[release_id] = state
        _PIPELINE_SOURCE_CACHE[release_id] = normalized_source

        # Make the completed state durable so subsequent ADK workers can answer
        # questions even after the original pipeline process has ended.
        _write_query_snapshot(
            output_dir=get_settings().output_dir,
            state=state,
            source_data=normalized_source,
        )

        

    def _load_source_data(
        self,
        block_names: tuple[str, ...],
    ) -> dict[
        str,
        list[dict[str, Any]],
    ]:
        """
        Load logical data blocks from the current Jira/MCP snapshot.

        Sub-agents receive only plain dictionaries and lists. They do not
        receive Jira/MCP client objects or any other infrastructure object.
        """

        if not block_names:
            return {}

        source_data: dict[
            str,
            list[dict[str, Any]],
        ] = {}

        for block_name in block_names:
            rows = self._load_data_block(
                block_name
            )

            if not isinstance(
                rows,
                list,
            ):
                raise TypeError(
                    f"Data block {block_name!r} returned "
                    f"{type(rows).__name__}; expected list."
                )

            source_data[block_name] = rows

        return source_data

    def _prepare_jira_source_data(
        self,
        release_id: str,
    ) -> None:
        """
        Resolve this run's Jira-backed input blocks from cache ONLY.

        Two layers, checked in order — each one only reached if the
        previous one misses:
          1. In-memory _JIRA_SOURCE_CACHE (fastest, lost on process restart).
          2. Durable SQLite cache (app/persistence/) — survives restarts,
             shared across worker processes. Read here regardless of
             staleness: freshness is the scheduled sync's job
             (app/persistence/scheduler.py), not something a live request
             enforces.

        Jira is never contacted here. If neither cache has this release,
        this registers it as pending (so the next scheduled sync picks it
        up) and raises ReleaseDataUnavailableError — the caller must not
        run the pipeline or attempt a Jira fetch of its own.
        """

        normalized_release_id = str(release_id or "").strip().upper()
        cache_key = (self.jira_project_key, normalized_release_id)
        ttl_seconds = get_settings().jira_source_cache_ttl_seconds

        if ttl_seconds > 0:
            cached = _JIRA_SOURCE_CACHE.get(cache_key)
            if cached is not None:
                cached_at, cached_source_data = cached
                age_seconds = time.time() - cached_at
                if age_seconds < ttl_seconds:
                    self._jira_source_data = cached_source_data
                    self._record_cache_event(
                        True, "jira_source_cache",
                        f"{self.jira_project_key}/{normalized_release_id}",
                        layer="in_memory", age_seconds=age_seconds,
                    )
                    self._emit_stage(
                        "orchestrator", "running",
                        f"Reusing Jira snapshot cached {int(age_seconds)}s ago for "
                        f"{normalized_release_id} (cache TTL {ttl_seconds}s)…",
                        agent_name="Master Orchestrator",
                    )
                    return

        db_hit = None
        try:
            db_hit = get_jira_cache_repository().get_full_release_any_freshness(
                self.jira_project_key, normalized_release_id
            )
        except Exception:
            logger.exception(
                "Jira cache DB read failed for %s/%s",
                self.jira_project_key, normalized_release_id,
            )

        if db_hit is not None:
            self._jira_source_data = db_hit
            _JIRA_SOURCE_CACHE[cache_key] = (time.time(), db_hit)
            self._record_cache_event(
                True, "jira_source_cache",
                f"{self.jira_project_key}/{normalized_release_id}",
                layer="sqlite",
            )
            self._emit_stage(
                "orchestrator", "running",
                f"Reusing cached release data from local database for {normalized_release_id}…",
                agent_name="Master Orchestrator",
            )
            return

        # An empty project key means this orchestrator was never given a
        # Jira project to search (e.g. a caller that skipped from_settings'
        # own validation) — registering it would create a pending row the
        # scheduler can never sync (it fails "JIRA_PROJECT_KEY is required"
        # forever), so there's nothing useful to register.
        if self.jira_project_key:
            try:
                get_jira_cache_repository().register_pending_release(
                    self.jira_project_key, normalized_release_id
                )
            except Exception:
                logger.exception(
                    "Failed to register %s/%s as pending for scheduled sync",
                    self.jira_project_key, normalized_release_id,
                )
        else:
            logger.warning(
                "Not registering %r as pending: no Jira project key resolved on this orchestrator",
                normalized_release_id,
            )

        self._record_cache_event(
            False, "jira_source_cache",
            f"{self.jira_project_key}/{normalized_release_id}",
            layer="both",
        )

        raise ReleaseDataUnavailableError(normalized_release_id)

    def _load_data_block(
        self,
        block_name: str,
    ) -> list[dict[str, Any]]:
        """Return one logical block from the Jira/MCP snapshot."""
        normalized = str(block_name or "").strip()
        rows = self._jira_source_data.get(normalized, [])
        if not isinstance(rows, list):
            raise TypeError(
                f"Jira data block {normalized!r} returned "
                f"{type(rows).__name__}; expected list."
            )
        return rows

    def _load_jira_source_data(
        self,
        release_id: str,
    ) -> dict[str, list[dict[str, Any]]]:
        """Load all Jira/MCP-backed logical blocks required by the pipeline."""
        if not self.jira_client or not self.jira_project_key:
            raise RuntimeError("MCP Jira client and JIRA_PROJECT_KEY are required.")

        # This method is where essentially all of a run's wall-clock time is
        # actually spent — every later stage reads from data already loaded
        # into memory here, with no further Jira/network calls. Emitting
        # sub-progress under stage_key="orchestrator" keeps that dominant
        # phase from looking like a single opaque spinner.
        self._emit_stage(
            "orchestrator", "running",
            "Resolving Jira custom field mappings…",
            agent_name="Master Orchestrator",
        )
        field_ids = self._resolve_jira_field_ids()
        fields_to_fetch = [
            "summary",
            "description",
            "issuetype",
            "labels",
            "status",
            "parent",
            "priority",
            "key",
            "id",
            "issuelinks",
            "fixVersions",
        ]
        for value in field_ids.values():
            if isinstance(value, (list, tuple, set)):
                fields_to_fetch.extend(str(item) for item in value if item)
            elif value:
                fields_to_fetch.append(str(value))
        unique_fields = list(dict.fromkeys(fields_to_fetch))

        project_clause = f'project = "{self.jira_project_key}"'
        self._emit_stage(
            "orchestrator", "running",
            f"Querying Jira project {self.jira_project_key!r} for all issues…",
            agent_name="Master Orchestrator",
        )
        all_issues = self._fetch_jira_issues(
            f"{project_clause} ORDER BY key ASC",
            unique_fields,
        )
        self._emit_stage(
            "orchestrator", "running",
            f"Fetched {len(all_issues)} Jira issues — categorizing and building release scope…",
            agent_name="Master Orchestrator",
        )

        rows: list[dict[str, Any]] = []
        issue_by_key: dict[str, dict[str, Any]] = {}

        for issue in all_issues:
            row = self._jira_issue_to_row(issue, field_ids)
            rows.append(row)
            key = str(row.get("issue_key") or "").strip()
            if key:
                issue_by_key[key] = row

        # Categorize first so parent traversal can identify parent types.
        for row in rows:
            row["category"] = self._jira_issue_category(row)

        # Multiple passes ensure TC -> Story -> Epic is fully enriched even if
        # Jira key ordering puts a child before its ancestor.
        for _ in range(3):
            for row in rows:
                self._enrich_jira_row_with_hierarchy(
                    row=row,
                    issue_by_key=issue_by_key,
                )

        # Reclassify after enrichment because some rows may only become
        # identifiable through inherited logical IDs.
        for row in rows:
            row["category"] = self._jira_issue_category(row)

        def by_cat(category: str) -> list[dict[str, Any]]:
            return [r for r in rows if r.get("category") == category]

        releases = by_cat("releases")
        modules = by_cat("modules")
        epics_all = by_cat("epics")
        stories_all = by_cat("stories")
        requirements_all = by_cat("requirements")
        test_cases_all = by_cat("test_cases")
        executions = by_cat("executions")
        defects = by_cat("defects")
        flaky_tests = by_cat("flaky_tests")
        policies = by_cat("policies")
        release_rules = by_cat("release_rules")

        rid = str(release_id or "").strip().upper()
        rid_normalized = self._normalize_key(rid)

        def identity_tokens(row: dict[str, Any]) -> set[str]:
            vals = set(self._row_identity_tokens(row))

            # work_item_id/issue_key are generic issue identifiers, not
            # release ids specifically, so they stay plain-normalized.
            for candidate in (
                row.get("work_item_id"),
                row.get("issue_key"),
            ):
                normalized = self._normalize_key(candidate)
                if normalized:
                    vals.add(normalized)

            # Release_ID, labels, and Fix Versions ARE what a tester types a
            # release id against — expand each into every REL-prefix variant
            # (see _release_id_variants) so 'REL-25.4', 'rel-25.4', and the
            # bare '25.4' all resolve the same way, whichever form Jira
            # itself stores.
            for candidate in (
                row.get("Release_ID"),
                row.get("Release ID"),
            ):
                vals.update(self._release_id_variants(candidate))

            labels = row.get("labels") or []

            if isinstance(labels, (list, tuple, set)):
                for label in labels:
                    vals.update(self._release_id_variants(label))
            else:
                vals.update(self._release_id_variants(labels))

            fix_versions = (row.get("Fix_Versions") or row.get("fixVersions") or [])

            if isinstance(fix_versions, (list, tuple, set)):
                version_values = fix_versions
            else:
                version_values = [fix_versions]

            for version in version_values:
                if isinstance(version, dict):
                    version_name = version.get("name") or version.get("value") or ""
                else:
                    version_name = version

                vals.update(self._release_id_variants(version_name))

            return vals

        def release_match(row: dict[str, Any]) -> bool:
            tokens = identity_tokens(row)
            summary = self._normalize_key(row.get("summary"))

            return (
                rid_normalized in tokens
                or rid_normalized in summary
            )

        matching_releases = [row for row in releases if release_match(row)]

        # Fallback #1: a Fix Version matching the requested release id —
        # tolerant of a 'REL'/'REL-' prefix on either side (see
        # _release_id_variants), so a tester typing '25.4' still finds a
        # Fix Version stored as 'REL-25.4' and vice versa. The actual
        # matched Fix Version text (not the tester's raw input) becomes
        # this run's canonical Release_ID, so scope membership below is
        # checked against the identifier Jira issues actually carry.
        if not matching_releases:

            fix_version_matches: list[dict[str, Any]] = []
            matched_release_id: str | None = None

            for row in rows:

                fix_versions = (row.get("Fix_Versions") or row.get("fixVersions") or [])

                if not isinstance(fix_versions, (list, tuple, set)):
                    fix_versions = [fix_versions]

                for version in fix_versions:

                    if isinstance(version, dict):
                        version_name = version.get("name") or version.get("value") or ""
                    else:
                        version_name = version

                    if rid_normalized in self._release_id_variants(version_name):
                        fix_version_matches.append(row)
                        if matched_release_id is None:
                            matched_release_id = str(version_name).strip()
                        break

            if fix_version_matches:

                release_id_value = matched_release_id or rid

                matching_releases = [{
                    "category": "releases",
                    "Release_ID": release_id_value,
                    "Release Name": release_id_value,
                    "summary": release_id_value,
                    "release_source": "jira_fix_version",
                    "source_issue_count": len(fix_version_matches),
                }]

                releases.extend(matching_releases)

        # Fallback #2: some Jira projects tag release membership with a
        # label (e.g. "REL-25.4") instead of a dedicated Release issue or
        # the Fix Versions field — only reached if neither of the above
        # found anything, same pattern as the Fix Version fallback above,
        # with the same REL-prefix tolerance and canonical-id capture.
        if not matching_releases:

            label_matches: list[dict[str, Any]] = []
            matched_release_id = None

            for row in rows:

                labels = row.get("labels") or []

                if not isinstance(labels, (list, tuple, set)):
                    labels = [labels]

                for label in labels:
                    if rid_normalized in self._release_id_variants(label):
                        label_matches.append(row)
                        if matched_release_id is None:
                            matched_release_id = str(label).strip()
                        break

            if label_matches:

                release_id_value = matched_release_id or rid

                matching_releases = [{
                    "category": "releases",
                    "Release_ID": release_id_value,
                    "Release Name": release_id_value,
                    "summary": release_id_value,
                    "release_source": "jira_label",
                    "source_issue_count": len(label_matches),
                }]

                releases.extend(matching_releases)

        if not matching_releases:

            available = set()

            for row in rows:

                candidate = (
                    row.get("Release_ID")
                    or row.get("work_item_id")
                    or self._strip_work_item_prefix(str(row.get("summary") or ""))
                )

                if candidate:
                    available.add(str(candidate).strip())

                fix_versions = (row.get("Fix_Versions") or row.get("fixVersions") or [])

                if not isinstance(fix_versions, (list, tuple, set)):
                    fix_versions = [fix_versions]

                for version in fix_versions:

                    if isinstance(version, dict):
                        name = version.get("name") or version.get("value") or ""
                    else:
                        name = version

                    if name:
                        available.add(str(name).strip())

                labels = row.get("labels") or []

                if not isinstance(labels, (list, tuple, set)):
                    labels = [labels]

                for label in labels:
                    if label:
                        available.add(str(label).strip())

            raise ValueError(
                f"Release {rid!r} was not found "
                "in Jira release data, Fix Versions, or labels. "
                f"Available releases/fixVersions/labels: "
                f"{sorted(available)}"
            )

        # release_match() above deliberately matches loosely (label/Release_ID
        # exact match OR a substring hit against the release issue's own
        # summary) so that an abbreviated or short-form input like "25.4"
        # still finds the intended Release issue, whose summary happens to
        # mention it. But that same loose match is reused below to decide
        # SCOPE MEMBERSHIP for every other issue (Epics/Stories/Tests) — and
        # those are labelled with the release's full canonical identifier
        # (e.g. "REL-25.4"), not the short form. Left as-is, searching for
        # "25.4" would find the right release but then silently scope in
        # zero epics/stories (no exact label match) plus only whichever
        # tests happen to mention "25.4" in their own summary text — a
        # materially incomplete, wrong dataset with no error raised.
        #
        # Fix: once the release is resolved, re-derive rid_normalized from
        # its own canonical Release_ID/work_item_id before using it to scope
        # every other issue, so scope membership is checked against the
        # identifier those issues actually carry.
        canonical_rid = next(
            (
                str(candidate).strip()
                for candidate_row in matching_releases
                for candidate in (
                    candidate_row.get("Release_ID"),
                    candidate_row.get("Release ID"),
                    candidate_row.get("work_item_id"),
                )
                if candidate
            ),
            None,
        )

        if canonical_rid:
            canonical_rid_normalized = self._normalize_key(canonical_rid)
            if canonical_rid_normalized:
                rid_normalized = canonical_rid_normalized

        # Seed scope from every Jira issue that explicitly references this
        # release via label, Release_ID, summary, or Fix Version.
        scoped_keys: set[str] = set()
        for row in rows:
            if release_match(row):
                key = str(row.get("issue_key") or "").strip()
                if key:
                    scoped_keys.add(key)

        # Expand in BOTH directions. This is important for this project because
        # the release label is sometimes on the Epic, while reusable descendants
        # may not carry the label themselves. It also lets a release-labelled
        # child bring its parent Story/Epic into the logical scope.
        changed = True
        while changed:
            changed = False
            for row in rows:
                issue_key = str(row.get("issue_key") or "").strip()
                parent_key = str(row.get("parent_key") or "").strip()

                # Parent -> child
                if issue_key and parent_key and parent_key in scoped_keys and issue_key not in scoped_keys:
                    scoped_keys.add(issue_key)
                    changed = True

                # Child -> parent
                if issue_key in scoped_keys and parent_key and parent_key not in scoped_keys:
                    scoped_keys.add(parent_key)
                    changed = True

        def in_scope(row: dict[str, Any]) -> bool:
            issue_key = str(row.get("issue_key") or "").strip()
            if issue_key in scoped_keys:
                return True
            return bool(identity_tokens(row) & {
                self._normalize_key(rid),
            })

        epics = [r for r in epics_all if in_scope(r)]
        stories = [r for r in stories_all if in_scope(r)]
        requirements = [r for r in requirements_all if in_scope(r)]

        # Resolve dependencies before broadening test-case scope so downstream
        # module tests are available to the Feature Agent.
        dependencies = self._build_module_dependencies(
            modules,
            issue_by_key,
        )

        release_scoped_test_cases = [
            r
            for r in test_cases_all
            if in_scope(r)
        ]

        dependent_module_ids_for_scope = {
            str(dependency.get("Dependent_Module_ID") or "").strip()
            for dependency in dependencies
            if str(dependency.get("Dependent_Module_ID") or "").strip()
        }

        dependency_module_test_cases = [
            r
            for r in test_cases_all
            if str(
                r.get("Module_ID")
                or r.get("Module ID")
                or ""
            ).strip() in dependent_module_ids_for_scope
            and str(
                r.get("Test_Status")
                or r.get("Test Status")
                or r.get("status")
                or "ACTIVE"
            ).strip().upper()
            not in {
                "INACTIVE",
                "DISABLED",
                "RETIRED",
                "DEPRECATED",
            }
        ]

        test_case_rows_by_key: dict[str, dict[str, Any]] = {}
        for row in (
            release_scoped_test_cases
            + dependency_module_test_cases
        ):
            key = str(
                row.get("issue_key")
                or row.get("Test_Case_ID")
                or row.get("Test Case ID")
                or row.get("work_item_id")
                or ""
            ).strip()
            if key:
                test_case_rows_by_key[key] = row

        test_cases = list(test_case_rows_by_key.values())

        # Reconstruct RTM from Test Case fields. Requirements are NOT Jira
        # parents in this project; Requirement_ID on the Test Case is the RTM
        # source of truth.
        rtm: list[dict[str, Any]] = []
        seen_rtm: set[tuple[str, str]] = set()
        for row in test_cases:
            tc = str(
                row.get("Test_Case_ID")
                or row.get("Test Case ID")
                or row.get("work_item_id")
                or ""
            ).strip()
            req = str(
                row.get("Requirement_ID")
                or row.get("Requirement ID")
                or ""
            ).strip()
            if not tc or not req:
                continue

            mapping_type = str(
                row.get("Mapping_Type")
                or row.get("Mapping Type")
                or "PRIMARY"
            ).strip().upper()
            mapping_status = str(
                row.get("Mapping_Status")
                or row.get("Mapping Status")
                or "ACTIVE"
            ).strip().upper()

            signature = (self._normalize_key(req), self._normalize_key(tc))
            if signature in seen_rtm:
                continue
            seen_rtm.add(signature)

            rtm.append({
                "Requirement_ID": req,
                "Test_Case_ID": tc,
                "Mapping_Type": mapping_type,
                "Mapping_Status": mapping_status,
            })

        # Reconstruct release scope for the Feature Agent. Epic/Story/Requirement
        # rows are each represented explicitly, while the same IDs are repeated
        # where useful for downstream joins.
        release_scope: list[dict[str, Any]] = []
        seen_scope: set[tuple[str, str, str]] = set()
        for collection_name, collection in (
            ("epics", epics),
            ("stories", stories),
            ("requirements", requirements),
        ):
            for row in collection:
                epic_id = str(
                    row.get("Epic_ID")
                    or row.get("Epic ID")
                    or row.get("work_item_id")
                    if collection_name == "epics"
                    else ""
                ).strip()
                story_id = str(
                    row.get("User_Story_ID")
                    or row.get("Story_ID")
                    or row.get("User Story ID")
                    or row.get("work_item_id")
                    if collection_name == "stories"
                    else ""
                ).strip()
                requirement_id = str(
                    row.get("Requirement_ID")
                    or row.get("Requirement ID")
                    or row.get("work_item_id")
                    if collection_name == "requirements"
                    else ""
                ).strip()

                # Fill inherited IDs from the normalized hierarchy.
                epic_id = epic_id or str(row.get("Epic_ID") or row.get("Epic ID") or "").strip()
                story_id = story_id or str(row.get("User_Story_ID") or row.get("Story_ID") or "").strip()
                requirement_id = requirement_id or str(row.get("Requirement_ID") or row.get("Requirement ID") or "").strip()

                item_id = requirement_id or story_id or epic_id or str(row.get("work_item_id") or row.get("issue_key") or "").strip()
                signature = (collection_name, self._normalize_key(item_id), rid_normalized)
                if not item_id or signature in seen_scope:
                    continue
                seen_scope.add(signature)

                release_scope.append({
                    "Release_ID": rid,
                    "Epic_ID": epic_id,
                    "User_Story_ID": story_id,
                    "Requirement_ID": requirement_id,
                    "Change_Type": row.get("Change_Type") or row.get("Change_Status") or "MODIFIED",
                    "Scope_Status": row.get("Scope_Status") or row.get("Scope Status") or "IN_SCOPE",
                    "Change_Description": row.get("Change_Description") or row.get("Change Description") or row.get("description") or "",
                    "Module_ID": row.get("Module_ID") or row.get("Module ID") or "",
                })


        normalized_executions: list[dict[str, Any]] = []
        for row in executions:
            normalized_executions.append({
                **row,
                "Execution_ID": row.get("Execution_ID") or row.get("Execution ID") or row.get("work_item_id") or "",
                "Test_Case_ID": row.get("Test_Case_ID") or row.get("Test Case ID") or "",
                "Release_ID": row.get("Release_ID") or row.get("Release ID") or "",
                "Execution_Date": row.get("Execution_Date") or row.get("Execution Date") or "",
                "Status": row.get("Execution_Status") or row.get("Execution Status") or row.get("Status") or row.get("status") or "",
                "Failure_Type": row.get("Failure_Type") or row.get("Failure Type") or "",
                "Is_Flaky": row.get("Is_Flaky") or row.get("Is Flaky") or "NO",
                "Environment": row.get("Environment") or "",
                "Test_Phase": row.get("Test_Phase") or row.get("Test Phase") or "",
            })

        import re as _re

        def _text_tc_id(row: dict[str, Any]) -> str:
            for field_name in ("Test_Case_ID", "Test Case ID", "summary", "Summary", "description", "Description"):
                value = row.get(field_name)
                if value is None:
                    continue
                match = _re.search(r"\bTC-\d+\b", str(value), _re.IGNORECASE)
                if match:
                    return match.group(0).upper()
            return ""

        normalized_defects: list[dict[str, Any]] = []
        for row in defects:
            normalized = dict(row)
            normalized["Test_Case_ID"] = normalized.get("Test_Case_ID") or normalized.get("Test Case ID") or _text_tc_id(normalized)
            if not normalized.get("Confirmed"):
                status_value = str(normalized.get("Status") or normalized.get("status") or "CONFIRMED").strip().upper()
                if status_value not in {"REJECTED", "DUPLICATE", "INVALID", "CANCELLED", "NOT_A_DEFECT"}:
                    normalized["Confirmed"] = "YES"
            normalized_defects.append(normalized)

        normalized_flaky: list[dict[str, Any]] = []
        for row in flaky_tests:
            normalized = dict(row)
            normalized["Test_Case_ID"] = normalized.get("Test_Case_ID") or normalized.get("Test Case ID") or _text_tc_id(normalized)
            normalized_flaky.append(normalized)

        regulatory_tests = [
            r for r in test_cases
            if str(
                r.get("Regulatory_Flag")
                or r.get("Regulatory Flag")
                or r.get("Regulatory_Status")
                or r.get("Regulatory Status")
                or ""
            ).strip().upper() in {"YES", "Y", "TRUE", "1", "ACTIVE", "REGULATORY"}
        ]

        self._emit_stage(
            "orchestrator", "running",
            f"Release scope resolved — {len(test_cases)} test cases in scope.",
            agent_name="Master Orchestrator",
        )

        return {
            "releases": matching_releases,
            "modules": modules,
            "epics": epics,
            "stories": stories,
            "requirements": requirements,
            "rtm": rtm,
            "test_cases": test_cases,
            "release_scope": release_scope,
            "dependencies": dependencies,
            "out_of_scope": [],
            "executions": normalized_executions,
            "defects": normalized_defects,
            "flaky_tests": normalized_flaky,
            "policies": policies,
            "regulatory_tests": regulatory_tests,
            "release_rules": release_rules,
        }

    def _build_module_dependencies(
        self,
        modules: list[dict[str, Any]],
        issue_by_key: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Build downstream Module-to-Module dependencies from Jira issue links.

        Business rule:

            A --blocks--> B

        is considered a downstream dependency only when the relationship is
        *one-way*. If Jira also contains:

            B --blocks--> A

        then the pair is bidirectional/circular and MUST NOT be treated as a
        downstream dependency in either direction.

        Therefore:

            A -> B only       => keep A -> B as downstream
            A -> B and B -> A => exclude both directions
            B -> A only       => keep B -> A as downstream

        The dependent module does not need to be in the release scope. It only
        needs to resolve to a real Jira Module. This allows a changed MOD-104
        to propagate to downstream MOD-109.
        """

        def resolve_module_id(
            issue_key: str,
            row: dict[str, Any] | None = None,
            link_issue: dict[str, Any] | None = None,
        ) -> str:
            """Resolve a Module ID from normalized Jira data, then summary."""
            candidates: list[Any] = []

            if row:
                candidates.extend(
                    [
                        row.get("Module_ID"),
                        row.get("Module ID"),
                        row.get("work_item_id"),
                        row.get("summary"),
                    ]
                )

            if link_issue:
                link_fields = link_issue.get("fields") or {}
                if isinstance(link_fields, dict):
                    candidates.extend(
                        [
                            link_fields.get("Module_ID"),
                            link_fields.get("Module ID"),
                            link_fields.get("summary"),
                        ]
                    )
                candidates.extend(
                    [
                        link_issue.get("summary"),
                        link_issue.get("key"),
                    ]
                )

            candidates.append(issue_key)

            for value in candidates:
                text = str(value or "").strip()
                if not text:
                    continue

                match = re.search(
                    r"\bMOD-\d+\b",
                    text,
                    re.IGNORECASE,
                )
                if match:
                    return match.group(0).upper()

            return ""

        module_keys: dict[str, str] = {}
        for row in modules:
            jira_key = str(row.get("issue_key") or "").strip()
            if not jira_key:
                continue

            module_id = resolve_module_id(
                jira_key,
                row=row,
            )
            if module_id:
                module_keys[jira_key] = module_id

        known_module_ids = set(module_keys.values())

        # First collect ALL directed BLOCKS edges. Do not immediately add them
        # to the downstream result because we must first detect reverse edges.
        directed_edges: dict[tuple[str, str], dict[str, Any]] = {}

        for module in modules:
            current_key = str(
                module.get("issue_key") or ""
            ).strip()
            if not current_key:
                continue

            current_module_id = module_keys.get(
                current_key,
            ) or resolve_module_id(
                current_key,
                row=module,
            )

            if not current_module_id:
                continue

            links = (
                module.get("Issue_Links")
                or module.get("issuelinks")
                or []
            )
            if not isinstance(links, list):
                continue

            for link in links:
                if not isinstance(link, dict):
                    continue

                link_type = link.get("type") or {}
                if not isinstance(link_type, dict):
                    continue

                outward_desc = self._normalize_key(
                    link_type.get("outward") or ""
                )
                inward_desc = self._normalize_key(
                    link_type.get("inward") or ""
                )

                outward_issue = link.get("outwardIssue") or {}
                inward_issue = link.get("inwardIssue") or {}

                outward_key = str(
                    outward_issue.get("key") or ""
                ).strip()
                inward_key = str(
                    inward_issue.get("key") or ""
                ).strip()

                source_key = ""
                dependent_key = ""
                source_issue_payload: dict[str, Any] | None = None
                dependent_issue_payload: dict[str, Any] | None = None

                # A --blocks--> B
                if (
                    outward_key
                    and outward_key != current_key
                    and "BLOCKS" in outward_desc
                ):
                    source_key = current_key
                    dependent_key = outward_key
                    source_issue_payload = issue_by_key.get(
                        current_key,
                        module,
                    )
                    dependent_issue_payload = outward_issue

                # B --blocks--> A, observed while inspecting A.
                elif (
                    inward_key
                    and inward_key != current_key
                    and "BLOCKED_BY" in inward_desc
                ):
                    source_key = inward_key
                    dependent_key = current_key
                    source_issue_payload = inward_issue
                    dependent_issue_payload = issue_by_key.get(
                        current_key,
                        module,
                    )

                if not source_key or not dependent_key:
                    continue

                source_row = issue_by_key.get(source_key)
                dependent_row = issue_by_key.get(dependent_key)

                source_module_id = resolve_module_id(
                    source_key,
                    row=source_row,
                    link_issue=source_issue_payload,
                )
                dependent_module_id = resolve_module_id(
                    dependent_key,
                    row=dependent_row,
                    link_issue=dependent_issue_payload,
                )

                # Final Jira lookup if a dependent row was not present in the
                # normalized project snapshot.
                if not dependent_module_id and self.jira_client:
                    try:
                        hydrated = self.jira_client.get_issue(
                            dependent_key,
                            [
                                "summary",
                                "issuetype",
                            ],
                        )
                    except Exception:
                        hydrated = {}

                    dependent_module_id = resolve_module_id(
                        dependent_key,
                        row=(
                            hydrated.get("fields", {})
                            if isinstance(hydrated, dict)
                            else None
                        ),
                        link_issue=hydrated,
                    )

                if not source_module_id or not dependent_module_id:
                    continue

                # Source must be a known Module. The dependent module may be
                # outside direct release scope but must resolve to MOD-xxxx.
                if source_module_id not in known_module_ids:
                    continue

                # Dependent/downstream modules may be outside direct release
                # scope; they must still participate when Jira resolves them.

                if source_module_id == dependent_module_id:
                    continue

                signature = (
                    source_module_id,
                    dependent_module_id,
                )

                # Preserve the first normalized record for this direction.
                if signature not in directed_edges:
                    directed_edges[signature] = {
                        "Source_Module_ID": source_module_id,
                        "Dependent_Module_ID": dependent_module_id,
                        "Dependency_Type": "BLOCKS",
                        "Description": (
                            f"{source_module_id} blocks "
                            f"{dependent_module_id}"
                        ),
                    }

        # A pair is a valid downstream dependency ONLY when it is one-way.
        # Reciprocal BLOCKS relationships are treated as bidirectional/circular
        # and are excluded in both directions.
        dependencies: list[dict[str, Any]] = []
        for (source_module_id, dependent_module_id), dependency in directed_edges.items():
            reverse_signature = (
                dependent_module_id,
                source_module_id,
            )

            if reverse_signature in directed_edges:
                continue

            dependencies.append(dependency)

        dependencies.sort(
            key=lambda row: (
                str(row.get("Source_Module_ID") or ""),
                str(row.get("Dependent_Module_ID") or ""),
            )
        )

        return dependencies

    def _fetch_jira_issues(
        self,
        jql: str,
        fields: list[str],
    ) -> list[dict[str, Any]]:
        """Fetch Jira issues and surface MCP/Jira errors."""
        if not self.jira_client:
            raise RuntimeError("MCP Jira client is not configured.")

        try:
            issues = self.jira_client.search(jql, fields)
        except Exception as exc:
            raise RuntimeError(
                f"MCP/Jira search failed. JQL={jql!r}; "
                f"Error={type(exc).__name__}: {exc}"
            ) from exc

        if not isinstance(issues, list):
            raise TypeError(
                f"MCP/Jira search returned {type(issues).__name__}; expected list."
            )

        return issues

    def _row_identity_tokens(
        self,
        row: dict[str, Any],
    ) -> set[str]:
        """Build normalized identity/release-scope tokens for a Jira row."""

        token_fields = (
            "issue_key",
            "work_item_id",
            "Epic_ID",
            "User_Story_ID",
            "Requirement_ID",
            "Epic ID",
            "Story_ID",
            "User Story ID",
            "Requirement ID",
            "parent_key",
            "Test_Case_ID",
            "Test Case ID",
        )

        # These fields are the ones a tester actually types a release id
        # against — expand each into every REL-prefix variant (see
        # _release_id_variants) so 'REL-25.4', 'rel-25.4', and the bare
        # '25.4' all resolve to the same tokens, however Jira stores it.
        release_id_fields = (
            "Release_ID",
            "Release ID",
        )

        tokens: set[str] = set()
        for field_name in token_fields:
            value = row.get(field_name)
            if value is None:
                continue
            if isinstance(value, (list, tuple, set)):
                values = value
            else:
                values = (value,)
            for item in values:
                normalized = self._normalize_key(item)
                if normalized:
                    tokens.add(normalized)

        for field_name in release_id_fields:
            value = row.get(field_name)
            if value is None:
                continue
            if isinstance(value, (list, tuple, set)):
                values = value
            else:
                values = (value,)
            for item in values:
                tokens.update(self._release_id_variants(item))

        labels = row.get("labels") or []
        if isinstance(labels, (list, tuple, set)):
            label_values = labels
        else:
            label_values = (labels,)
        for label in label_values:
            tokens.update(self._release_id_variants(label))

        # Fix Versions may also be used as release-scope metadata.
        for version in row.get("Fix_Versions") or row.get("fixVersions") or []:
            if isinstance(version, dict):
                version_name = version.get("name") or version.get("value") or ""
            else:
                version_name = version
            tokens.update(self._release_id_variants(version_name))

        return tokens

    def _row_belongs_to_release(
        self,
        row: dict[str, Any],
        release_scope_tokens: set[str],
    ) -> bool:
        """
        Determine whether a row is part of the current release scope.

        For epics / stories / requirements this is straightforward because the
        rows themselves are loaded from the release-scoped Jira query.
        For test cases we require a relationship to one of the release-scoped
        identifiers so reusable unlabeled tests can still be included.
        """

        if not release_scope_tokens:
            return True

        row_tokens = self._row_identity_tokens(row)
        if row_tokens & release_scope_tokens:
            return True

        parent_key = self._normalize_key(row.get("parent_key"))
        if parent_key and parent_key in release_scope_tokens:
            return True

        return False

    def _resolve_jira_field_ids(
        self,
    ) -> dict[str, str]:
        """
        Resolve Jira custom field IDs dynamically by semantic field name.

        Jira can contain duplicate custom fields with the same display name.
        For example, this project has two "Release Type" fields. In that
        situation, select the candidate that is actually populated on the
        relevant Jira work type instead of relying on dictionary overwrite
        order or hard-coded customfield IDs.
        """
        if self._jira_field_ids is not None:
            return self._jira_field_ids

        field_ids: dict[str, str] = {
            "epic_id": "",
            "story_id": "",
            "module_id": "",
            "change_status": "",
            "requirement_id": "",
            "test_case_id": "",
            "test_status": "",
            "business_priority": "",
            "automation_status": "",
            "execution_minutes": "",
            "regulatory_flag": "",
            "requirement_description": "",
            "test_name": "",
            "story_name": "",
            "epic_name": "",
            "release_id": "",
            "execution_id": "",
            "execution_date": "",
            "execution_status": "",
            "failure_type": "",
            "is_flaky": "",
            "environment": "",
            "test_phase": "",
            "defect_id": "",
            "severity": "",
            "confirmed": "",
            "production_escape": "",
            "detected_date": "",
            "mapping_type": "",
            "mapping_status": "",
            "release_type": "",
            "rule_name": "",
            "rule_value": "",
            "mandatory_reason": "",
            "policy_reference": "",
            "policy_status": "",
            "release_name": "",
            "release_status": "",
            "scope_freeze_date": "",
            "planned_release_date": "",
            "module_name": "",
            "regulatory_score": "",
            "financial_score": "",
            "customer_score": "",
            "sla_score": "",
            "incident_score": "",
            "change_type": "",
            "scope_status": "",
            "change_description": "",
            "flaky_status": "",
            "flaky_total_runs": "",
            "flaky_failures": "",
            "flaky_rate": "",
            "remediation_action": "",
            "minimum_coverage": "",
            "tier_max_exclusion": "",
            "overall_max_exclusion": "",
            "over_cap_approval_role": "",
            "rule_status": "",
            "rule_type": "",
        }

        if not self.jira_client:
            self._jira_field_ids = field_ids
            return field_ids

        try:
            all_fields = self.jira_client.list_fields()
        except Exception:
            all_fields = []

        # Keep every field ID for a semantic name instead of overwriting a
        # duplicate name with the last ID returned by Jira.
        lookup: dict[str, list[str]] = {}
        for field in all_fields:
            field_id = str(
                field.get("id")
                or field.get("key")
                or ""
            ).strip()
            if not field_id:
                continue

            names: list[str] = []
            raw_name = field.get("name")
            if raw_name:
                names.append(str(raw_name))

            clause_names = field.get("clauseNames") or []
            if isinstance(clause_names, list):
                names.extend(
                    str(clause_name)
                    for clause_name in clause_names
                    if clause_name
                )

            for name in names:
                key = self._normalize_key(name)
                if not key:
                    continue
                ids = lookup.setdefault(key, [])
                if field_id not in ids:
                    ids.append(field_id)

        # Work-type probes used only when a semantic name maps to multiple
        # custom fields. These are Jira issue-type names, not custom field IDs.
        probe_types: dict[str, tuple[str, ...]] = {
            "release": ("Release",),
            "module": ("Module",),
            "test_case": ("Test Case", "Test"),
            "requirement": ("Requirement", "Requirment"),
            "execution": ("Test Execution", "Execution"),
            "defect": ("Bug", "Defect"),
            "policy": ("Risk Policy", "Policy"),
            "release_rule": ("Release Rule", "Rule"),
            "flaky": ("Flaky Test", "Flaky Test Record", "Flaky_Test"),
        }

        probe_cache: dict[str, list[dict[str, Any]]] = {}

        def probe_issue_type(type_names: tuple[str, ...]) -> list[dict[str, Any]]:
            cache_key = "|".join(type_names)
            if cache_key in probe_cache:
                return probe_cache[cache_key]

            issues: list[dict[str, Any]] = []
            for type_name in type_names:
                jql = (
                    f'project = "{self.jira_project_key}" '
                    f'AND issuetype = "{type_name}" ORDER BY key ASC'
                )
                try:
                    candidate_issues = self.jira_client.search(
                        jql,
                        ["key", "summary"],
                    )
                except Exception:
                    candidate_issues = []

                if candidate_issues:
                    issues.extend(candidate_issues)

            # Preserve order and remove duplicate Jira keys.
            seen: set[str] = set()
            unique: list[dict[str, Any]] = []
            for issue in issues:
                key = str(issue.get("key") or "").strip()
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                unique.append(issue)

            probe_cache[cache_key] = unique[:20]
            return probe_cache[cache_key]

        def _candidate_values(
            candidate_ids: list[str],
            issue_types: tuple[str, ...] | None,
        ) -> dict[str, int]:
            """Count populated values for candidate fields on probe issues."""
            scores = {candidate_id: 0 for candidate_id in candidate_ids}
            if len(candidate_ids) <= 1 or not issue_types:
                return scores

            probe_issues = probe_issue_type(issue_types)
            if not probe_issues:
                return scores

            # Fetch the candidate fields directly from the probe issues.
            for issue in probe_issues:
                issue_key = str(issue.get("key") or "").strip()
                if not issue_key:
                    continue
                try:
                    hydrated = self.jira_client.get_issue(
                        issue_key,
                        candidate_ids,
                    )
                except Exception:
                    continue

                fields = hydrated.get("fields", {}) if isinstance(hydrated, dict) else {}
                if not isinstance(fields, dict):
                    continue

                for candidate_id in candidate_ids:
                    value = fields.get(candidate_id)
                    if value is None or value == "":
                        continue
                    if isinstance(value, (list, dict)) and not value:
                        continue
                    # Jira option objects are populated if they contain a
                    # value/name/id. Any non-empty scalar is populated too.
                    if isinstance(value, dict) and not any(
                        value.get(k) for k in ("value", "name", "id", "key")
                    ):
                        continue
                    scores[candidate_id] += 1

            return scores

        semantic_probe_group: dict[str, tuple[str, ...] | None] = {
            "release_id": probe_types["release"],
            "release_type": probe_types["release"],
            "module_id": probe_types["module"],
            "test_case_id": probe_types["test_case"],
            "test_status": probe_types["test_case"],
            "automation_status": probe_types["test_case"],
            "execution_minutes": probe_types["test_case"],
            "regulatory_flag": probe_types["test_case"],
            "requirement_id": probe_types["requirement"],
            "requirement_description": probe_types["requirement"],
            "execution_id": probe_types["execution"],
            "execution_date": probe_types["execution"],
            "execution_status": probe_types["execution"],
            "failure_type": probe_types["execution"],
            "is_flaky": probe_types["execution"],
            "environment": probe_types["execution"],
            "test_phase": probe_types["execution"],
            "defect_id": probe_types["defect"],
            "severity": probe_types["defect"],
            "confirmed": probe_types["defect"],
            "production_escape": probe_types["defect"],
            "detected_date": probe_types["defect"],
            "release_type": probe_types["release"],
            "rule_name": probe_types["release_rule"],
            "rule_value": probe_types["release_rule"],
            "mandatory_reason": probe_types["policy"],
            "policy_reference": probe_types["policy"],
            "policy_status": probe_types["policy"],
            "minimum_coverage": probe_types["policy"],
            "tier_max_exclusion": probe_types["policy"],
            "overall_max_exclusion": probe_types["policy"],
            "over_cap_approval_role": probe_types["policy"],
            "rule_status": probe_types["release_rule"],
            "rule_type": probe_types["release_rule"],
            "release_name": probe_types["release"],
            "release_status": probe_types["release"],
            "scope_freeze_date": probe_types["release"],
            "planned_release_date": probe_types["release"],
            "module_name": probe_types["module"],
            "regulatory_score": probe_types["module"],
            "financial_score": probe_types["module"],
            "customer_score": probe_types["module"],
            "sla_score": probe_types["module"],
            "incident_score": probe_types["module"],
            "change_type": None,
            "scope_status": None,
            "change_description": None,
            "flaky_status": probe_types["flaky"],
            "flaky_total_runs": probe_types["flaky"],
            "flaky_failures": probe_types["flaky"],
            "flaky_rate": probe_types["flaky"],
            "remediation_action": probe_types["flaky"],
        }

        def find(field_key: str, *candidates: str) -> str:
            candidate_ids: list[str] = []
            seen_ids: set[str] = set()
            for candidate in candidates:
                ids = lookup.get(self._normalize_key(candidate), [])
                for candidate_id in ids:
                    if candidate_id not in seen_ids:
                        seen_ids.add(candidate_id)
                        candidate_ids.append(candidate_id)

            if not candidate_ids:
                return ""
            if len(candidate_ids) == 1:
                return candidate_ids[0]

            scores = _candidate_values(
                candidate_ids,
                semantic_probe_group.get(field_key),
            )

            # Highest populated score wins. If tied, preserve Jira's returned
            # order instead of selecting a random duplicate.
            best_id = candidate_ids[0]
            best_score = scores.get(best_id, 0)
            for candidate_id in candidate_ids[1:]:
                score = scores.get(candidate_id, 0)
                if score > best_score:
                    best_id = candidate_id
                    best_score = score

            return best_id

        field_ids["requirement_id"] = find(
            "requirement_id",
            "Requirement ID",
            "RequirementId",
            "Requirement_ID",
            "Req ID",
            "Req_ID",
        )
        field_ids["test_case_id"] = find(
            "test_case_id",
            "Test Case ID",
            "TestCase ID",
            "Test_Case_ID",
            "TestCase_ID",
            "TC ID",
            "TC_ID",
        )
        field_ids["test_status"] = find("test_status", "Test Status", "Test_Status", "TestStatus")
        field_ids["business_priority"] = find("business_priority", "Business Priority", "Business_Priority")
        field_ids["automation_status"] = find("automation_status", "Automation Status", "Automation_Status")
        field_ids["execution_minutes"] = find("execution_minutes", "Execution Minutes", "Execution_Minutes", "Duration Minutes", "Duration")
        field_ids["regulatory_flag"] = find("regulatory_flag", "Regulatory Flag", "Regulatory_Flag")
        field_ids["requirement_description"] = find("requirement_description", "Requirement Description", "Requirement_Description", "Description")
        field_ids["test_name"] = find("test_name", "Test Name", "Test_Name")
        field_ids["story_name"] = find("story_name", "Story Name", "User Story Name", "User_Story_Name")
        field_ids["epic_name"] = find("epic_name", "Epic Name", "Epic_Name")
        field_ids["release_id"] = find("release_id", "Release ID", "ReleaseId", "Release_ID")
        field_ids["execution_id"] = find("execution_id", "Execution ID", "ExecutionId", "Execution_ID")
        field_ids["execution_date"] = find("execution_date", "Execution Date", "ExecutionDate", "Execution_Date")
        field_ids["execution_status"] = find("execution_status", "Execution Status", "ExecutionStatus", "Execution_Status")
        field_ids["failure_type"] = find("failure_type", "Failure Type", "FailureType", "Failure_Type")
        field_ids["is_flaky"] = find("is_flaky", "Is Flaky", "IsFlaky", "Is_Flaky")
        field_ids["environment"] = find("environment", "Environment")
        field_ids["test_phase"] = find("test_phase", "Test Phase", "TestPhase", "Test_Phase")
        field_ids["defect_id"] = find("defect_id", "Defect ID", "DefectId", "Defect_ID")
        field_ids["severity"] = find("severity", "Severity")
        field_ids["confirmed"] = find("confirmed", "Confirmed")
        field_ids["production_escape"] = find("production_escape", "Production Escape", "Production_Escape")
        field_ids["detected_date"] = find("detected_date", "Detected Date", "Detected_Date")
        field_ids["mapping_type"] = find("mapping_type", "Mapping Type", "Mapping_Type")
        field_ids["mapping_status"] = find("mapping_status", "Mapping Status", "Mapping_Status")
        field_ids["release_type"] = find("release_type", "Release Type", "Release_Type")
        field_ids["rule_name"] = find("rule_name", "Rule Name", "Rule_Name")
        field_ids["rule_value"] = find("rule_value", "Rule Value", "Rule_Value")
        field_ids["mandatory_reason"] = find("mandatory_reason", "Mandatory Reason", "Mandatory_Reason")
        field_ids["policy_reference"] = find("policy_reference", "Policy Reference", "Policy_Reference")
        field_ids["policy_status"] = find(
            "policy_status",
            "Policy Status",
            "Policy_Status",
            "PolicyStatus",
        )
        field_ids["minimum_coverage"] = find(
            "minimum_coverage",
            "Minimum Coverage",
            "Minimum_Coverage",
            "Min Coverage",
            "Min_Coverage",
        )
        field_ids["tier_max_exclusion"] = find(
            "tier_max_exclusion",
            "Tier Max Exclusion",
            "Tier_Max_Exclusion",
        )
        field_ids["overall_max_exclusion"] = find(
            "overall_max_exclusion",
            "Overall Max Exclusion",
            "Overall_Max_Exclusion",
        )
        field_ids["over_cap_approval_role"] = find(
            "over_cap_approval_role",
            "Over Cap Approval Role",
            "Over_Cap_Approval_Role",
        )
        field_ids["rule_status"] = find(
            "rule_status",
            "Rule Status",
            "Rule_Status",
        )
        field_ids["rule_type"] = find(
            "rule_type",
            "Rule Type",
            "Rule_Type",
        )

        field_ids["release_name"] = find(
            "release_name",
            "Release Name",
            "Release_Name",
        )
        field_ids["release_status"] = find(
            "release_status",
            "Release Status",
            "Release_Status",
        )
        field_ids["scope_freeze_date"] = find(
            "scope_freeze_date",
            "Scope Freeze Date",
            "Scope_Freeze_Date",
        )
        field_ids["planned_release_date"] = find(
            "planned_release_date",
            "Planned Release Date",
            "Planned_Release_Date",
        )

        field_ids["module_name"] = find(
            "module_name",
            "Module Name",
            "Module_Name",
        )
        field_ids["regulatory_score"] = find(
            "regulatory_score",
            "Regulatory Score",
            "Regulatory_Score",
        )
        field_ids["financial_score"] = find(
            "financial_score",
            "Financial Score",
            "Financial_Score",
        )
        field_ids["customer_score"] = find(
            "customer_score",
            "Customer Score",
            "Customer_Score",
        )
        field_ids["sla_score"] = find(
            "sla_score",
            "SLA Score",
            "SLA_Score",
        )
        field_ids["incident_score"] = find(
            "incident_score",
            "Incident Score",
            "Incident_Score",
            # The Jira project's actual custom field for this factor is
            # named "Incident Number" (customfield_10188), not "Incident
            # Score" — without this alias, field resolution silently never
            # matches it and every module's incident factor reads as blank.
            "Incident Number",
            "Incident_Number",
        )

        field_ids["flaky_status"] = find(
            "flaky_status",
            "Flaky Status",
            "Flaky_Status",
        )
        field_ids["flaky_total_runs"] = find(
            "flaky_total_runs",
            "Total Runs",
            "Total_Runs",
        )
        field_ids["flaky_failures"] = find(
            "flaky_failures",
            "Flaky Failures",
            "Flaky_Failures",
        )
        field_ids["flaky_rate"] = find(
            "flaky_rate",
            "Flaky Rate",
            "Flaky_Rate",
        )
        field_ids["remediation_action"] = find(
            "remediation_action",
            "Remediation Action",
            "Remediation_Action",
        )

        # Explicitly resolve the remaining hierarchy fields too. These names
        # can also be duplicated between historical/custom fields.
        field_ids["epic_id"] = find("epic_id", "Epic ID", "EpicId", "Epic_ID")
        field_ids["story_id"] = find("story_id", "Story ID", "StoryId", "Story_ID", "User Story ID", "User_Story_ID")
        field_ids["module_id"] = find("module_id", "Module ID", "ModuleId", "Module_ID")
        field_ids["change_status"] = find("change_status", "Change Status", "ChangeStatus", "Change_Status")

        self._jira_field_ids = field_ids
        return field_ids

    def _jira_issue_to_row(
        self,
        issue: dict[str, Any],
        field_ids: dict[str, str],
    ) -> dict[str, Any]:
        """
        Convert one Jira issue into a normalized row.
        """

        fields = issue.get(
            "fields",
            {},
        )
        if not isinstance(
            fields,
            dict,
        ):
            fields = {}

        issue_key = str(
            issue.get("key") or ""
        ).strip()
        issue_type = str(
            (
                fields.get("issuetype", {}) or {}
            ).get("name")
            or ""
        ).strip()
        summary = str(
            fields.get("summary")
            or ""
        ).strip()
        description = fields.get(
            "description",
            "",
        )
        if description is None:
            description = ""
        status = str(
            (
                fields.get("status", {}) or {}
            ).get("name")
            or ""
        ).strip()
        labels = fields.get(
            "labels",
            [],
        )
        if not isinstance(
            labels,
            list,
        ):
            labels = [labels]
        parent = fields.get(
            "parent",
            {},
        )
        parent_key = str(
            (
                parent or {}
            ).get("key")
            or ""
        ).strip()

        work_item_id = self._extract_work_item_id(
            summary=summary,
            issue_key=issue_key,
        )

        row: dict[str, Any] = {
            "issue_key": issue_key,
            "issue_type": issue_type,
            "summary": summary,
            "description": description,
            "status": status,
            "labels": labels,
            "parent_key": parent_key,
            "work_item_id": work_item_id,
            "Epic_ID": self._field_text(fields, field_ids.get("epic_id")),
            "User_Story_ID": self._field_text(fields, field_ids.get("story_id")),
            "Requirement_ID": self._field_text(fields, field_ids.get("requirement_id")),
            "Test_Case_ID": self._field_text(fields, field_ids.get("test_case_id")),
            "Module_ID": self._field_text(fields, field_ids.get("module_id")),
            "Change_Status": self._field_text(fields, field_ids.get("change_status")),
            "Business_Priority": self._field_text(fields, field_ids.get("business_priority")),
            "Test_Status": self._field_text(fields, field_ids.get("test_status")),
            "Automation_Status": self._field_text(fields, field_ids.get("automation_status")),
            "Execution_Minutes": self._field_text(fields, field_ids.get("execution_minutes")),
            "Regulatory_Flag": self._field_text(fields, field_ids.get("regulatory_flag")),
            "Requirement_Description": self._field_text(fields, field_ids.get("requirement_description")),
            "Test_Name": self._field_text(fields, field_ids.get("test_name")),
            "User_Story_Name": self._field_text(fields, field_ids.get("story_name")),
            "Epic_Name": self._field_text(fields, field_ids.get("epic_name")),
            "Release_ID": self._field_text(fields, field_ids.get("release_id")),
            "Execution_ID": self._field_text(fields, field_ids.get("execution_id")),
            "Execution_Date": self._field_text(fields, field_ids.get("execution_date")),
            "Execution_Status": self._field_text(fields, field_ids.get("execution_status")),
            "Failure_Type": self._field_text(fields, field_ids.get("failure_type")),
            "Is_Flaky": self._field_text(fields, field_ids.get("is_flaky")),
            "Environment": self._field_text(fields, field_ids.get("environment")),
            "Test_Phase": self._field_text(fields, field_ids.get("test_phase")),
            "Defect_ID": self._field_text(fields, field_ids.get("defect_id")),
            "Severity": self._field_text(fields, field_ids.get("severity")),
            "Confirmed": self._field_text(fields, field_ids.get("confirmed")),
            "Production_Escape": self._field_text(fields, field_ids.get("production_escape")),
            "Detected_Date": self._field_text(fields, field_ids.get("detected_date")),
            "Mapping_Type": self._field_text(fields, field_ids.get("mapping_type")),
            "Mapping_Status": self._field_text(fields, field_ids.get("mapping_status")),
            "Release_Type": self._field_text(fields, field_ids.get("release_type")),
            "Rule_Name": self._field_text(fields, field_ids.get("rule_name")),
            "Rule_Value": self._field_text(fields, field_ids.get("rule_value")),
            "Mandatory_Reason": self._field_text(fields, field_ids.get("mandatory_reason")),
            "Policy_Reference": self._field_text(fields, field_ids.get("policy_reference")),
            "Policy_Status": self._field_text(fields, field_ids.get("policy_status")),
            "Release_Name": self._field_text(fields, field_ids.get("release_name")),
            "Release_Status": self._field_text(fields, field_ids.get("release_status")),
            "Scope_Freeze_Date": self._field_text(fields, field_ids.get("scope_freeze_date")),
            "Planned_Release_Date": self._field_text(fields, field_ids.get("planned_release_date")),
            "Module_Name": self._field_text(fields, field_ids.get("module_name")),
            "Regulatory_Score": self._field_text(fields, field_ids.get("regulatory_score")),
            "Financial_Score": self._field_text(fields, field_ids.get("financial_score")),
            "Customer_Score": self._field_text(fields, field_ids.get("customer_score")),
            "SLA_Score": self._field_text(fields, field_ids.get("sla_score")),
            "Incident_Score": self._field_text(fields, field_ids.get("incident_score")),
            "Change_Type": self._field_text(fields, field_ids.get("change_type")),
            "Scope_Status": self._field_text(fields, field_ids.get("scope_status")),
            "Change_Description": self._field_text(fields, field_ids.get("change_description")),
            "Flaky_Status": self._field_text(fields, field_ids.get("flaky_status")),
            "Total_Runs": self._field_text(fields, field_ids.get("flaky_total_runs")),
            "Flaky_Failures": self._field_text(fields, field_ids.get("flaky_failures")),
            "Flaky_Rate": self._field_text(fields, field_ids.get("flaky_rate")),
            "Remediation_Action": self._field_text(fields, field_ids.get("remediation_action")),
            "Minimum_Coverage": self._field_text(fields, field_ids.get("minimum_coverage")),
            "Tier_Max_Exclusion": self._field_text(fields, field_ids.get("tier_max_exclusion")),
            "Overall_Max_Exclusion": self._field_text(fields, field_ids.get("overall_max_exclusion")),
            "Over_Cap_Approval_Role": self._field_text(fields, field_ids.get("over_cap_approval_role")),
            "Rule_Status": self._field_text(fields, field_ids.get("rule_status")),
            "Rule_Type": self._field_text(fields, field_ids.get("rule_type")),
            "Issue_Links": fields.get("issuelinks", []),
            "Fix_Versions": fields.get("fixVersions", []),
        }

        # Fill obvious name fields from the summary when a dedicated field is
        # not available.
        stripped_summary = self._strip_work_item_prefix(
            summary
        )
        row["Epic_Name"] = row["Epic_Name"] or stripped_summary
        row["User_Story_Name"] = row["User_Story_Name"] or stripped_summary
        row["Requirement_Name"] = row.get("Requirement_Name") or stripped_summary
        row["Test_Name"] = row["Test_Name"] or stripped_summary

        # Convenience aliases used by the downstream tools.
        row["Epic ID"] = row["Epic_ID"]
        row["Story_ID"] = row["User_Story_ID"]
        row["User Story ID"] = row["User_Story_ID"]
        row["Requirement ID"] = row["Requirement_ID"]
        row["Test Case ID"] = row["Test_Case_ID"]
        row["Test Case Name"] = row["Test_Name"]
        row["Module ID"] = row["Module_ID"]
        row["Change Status"] = row["Change_Status"]
        row["Business Priority"] = row["Business_Priority"]
        row["Test Status"] = row["Test_Status"]
        row["Automation Status"] = row["Automation_Status"]
        row["Execution Minutes"] = row["Execution_Minutes"]
        row["Regulatory Flag"] = row["Regulatory_Flag"]
        row["Requirement Description"] = row["Requirement_Description"]
        row["Test Name"] = row["Test_Name"]
        row["Story Name"] = row["User_Story_Name"]
        row["Epic Name"] = row["Epic_Name"]
        row["Release ID"] = row.get("Release_ID", "")
        row["Execution ID"] = row.get("Execution_ID", "")
        row["Execution Status"] = row.get("Execution_Status", "")
        row["Failure Type"] = row.get("Failure_Type", "")
        row["Is Flaky"] = row.get("Is_Flaky", "")
        row["Environment"] = row.get("Environment", "")
        row["Test Phase"] = row.get("Test_Phase", "")
        row["Defect ID"] = row.get("Defect_ID", "")
        row["Severity"] = row.get("Severity", "")
        row["Confirmed"] = row.get("Confirmed", "")
        row["Production Escape"] = row.get("Production_Escape", "")
        row["Detected Date"] = row.get("Detected_Date", "")
        row["Mapping Type"] = row.get("Mapping_Type", "")
        row["Mapping Status"] = row.get("Mapping_Status", "")
        row["Release Type"] = row.get("Release_Type", "")
        row["Rule Name"] = row.get("Rule_Name", "")
        row["Rule Value"] = row.get("Rule_Value", "")
        row["Mandatory Reason"] = row.get("Mandatory_Reason", "")
        row["Policy Reference"] = row.get("Policy_Reference", "")
        row["Policy Status"] = row.get("Policy_Status", "")
        row["Release Name"] = row.get("Release_Name", "")
        row["Release Status"] = row.get("Release_Status", "")
        row["Scope Freeze Date"] = row.get("Scope_Freeze_Date", "")
        row["Planned Release Date"] = row.get("Planned_Release_Date", "")
        row["Module Name"] = row.get("Module_Name", "")
        row["Regulatory Score"] = row.get("Regulatory_Score", "")
        row["Financial Score"] = row.get("Financial_Score", "")
        row["Customer Score"] = row.get("Customer_Score", "")
        row["SLA Score"] = row.get("SLA_Score", "")
        row["Incident Score"] = row.get("Incident_Score", "")
        row["Change Type"] = row.get("Change_Type", "")
        row["Scope Status"] = row.get("Scope_Status", "")
        row["Change Description"] = row.get("Change_Description", "")
        row["Flaky Status"] = row.get("Flaky_Status", "")
        row["Total Runs"] = row.get("Total_Runs", "")
        row["Flaky Failures"] = row.get("Flaky_Failures", "")
        row["Flaky Rate"] = row.get("Flaky_Rate", "")
        row["Remediation Action"] = row.get("Remediation_Action", "")
        row["Minimum Coverage"] = row.get("Minimum_Coverage", "")
        row["Tier Max Exclusion"] = row.get("Tier_Max_Exclusion", "")
        row["Overall Max Exclusion"] = row.get("Overall_Max_Exclusion", "")
        row["Over Cap Approval Role"] = row.get("Over_Cap_Approval_Role", "")
        row["Rule Status"] = row.get("Rule_Status", "")
        row["Rule Type"] = row.get("Rule_Type", "")

        if (
            self._normalize_key(issue_type) in {"TEST_CASE", "TEST", "SUBTASK", "SUB_TASK"}
            or str(row.get("work_item_id") or "").upper().startswith("TC-")
        ) and not row["Test_Status"]:
            row["Test_Status"] = "ACTIVE"
            row["Test Status"] = "ACTIVE"

        # Release Type is a Jira custom field. If field metadata discovery is
        # unavailable, still recover a configured release type from the raw
        # field payload without hard-coding a customfield_XXXXX ID.
        if not row["Release_Type"] and self._normalize_key(issue_type) == "RELEASE":
            inferred_release_type = self._infer_release_type_from_fields(fields)
            if inferred_release_type:
                row["Release_Type"] = inferred_release_type
                row["Release Type"] = inferred_release_type

        if not row["Release_ID"] and row.get("work_item_id", "").upper().startswith("REL-"):
            row["Release_ID"] = row["work_item_id"]

        row["category"] = self._jira_issue_category(
            row
        )

        return row

    def _infer_release_type_from_fields(
        self,
        fields: dict[str, Any],
    ) -> str:
        """Infer MAJOR/MINOR/HOTFIX from raw Jira Release fields safely."""
        allowed = {"MAJOR", "MINOR", "HOTFIX"}

        def walk(value: Any) -> str:
            if isinstance(value, dict):
                for key in ("value", "name", "key"):
                    candidate = value.get(key)
                    normalized = self._normalize_key(candidate)
                    if normalized in allowed:
                        return str(candidate).strip().upper()
                for nested in value.values():
                    found = walk(nested)
                    if found:
                        return found
                return ""

            if isinstance(value, (list, tuple, set)):
                for nested in value:
                    found = walk(nested)
                    if found:
                        return found
                return ""

            normalized = self._normalize_key(value)
            return str(value).strip().upper() if normalized in allowed else ""

        for field_id, value in fields.items():
            if not str(field_id).startswith("customfield_"):
                continue
            found = walk(value)
            if found:
                return found

        return ""

    def _enrich_jira_row_with_hierarchy(
        self,
        row: dict[str, Any],
        issue_by_key: dict[str, dict[str, Any]],
    ) -> None:
        """
        Propagate the complete Jira parent hierarchy into one normalized row.

        Project model:
            Epic -> Story -> Test Case (subtask)

        Requirements are not Jira parents in this project. A Test Case carries
        Requirement_ID directly, so that field is preserved as the source of
        truth for RTM. Parent traversal is used only for Epic/Story/Module and
        other hierarchy metadata that can be inherited safely.
        """

        current = row
        visited: set[str] = set()
        depth = 0

        while depth < 10:
            parent_key = str(current.get("parent_key") or "").strip()
            if not parent_key or parent_key in visited:
                break
            visited.add(parent_key)

            parent = issue_by_key.get(parent_key)
            if not parent:
                break

            # Inherit fields only when the child does not already have the
            # value. Direct fields on Test Cases therefore remain authoritative.
            for field_name in (
                "Epic_ID",
                "User_Story_ID",
                "Module_ID",
                "Change_Status",
            ):
                if not row.get(field_name) and parent.get(field_name):
                    row[field_name] = parent.get(field_name)

            # Story parent -> Epic.
            if self._normalize_key(parent.get("issue_type")) == "EPIC":
                row["Epic_ID"] = (
                    row.get("Epic_ID")
                    or parent.get("Epic_ID")
                    or parent.get("work_item_id")
                    or parent_key
                )

            # Test Case / subtask parent -> Story.
            if self._normalize_key(parent.get("issue_type")) in {
                "STORY",
                "TASK",
            } or str(parent.get("work_item_id") or "").upper().startswith("US-"):
                row["User_Story_ID"] = (
                    row.get("User_Story_ID")
                    or parent.get("User_Story_ID")
                    or parent.get("work_item_id")
                    or parent_key
                )
                row["Epic_ID"] = (
                    row.get("Epic_ID")
                    or parent.get("Epic_ID")
                )

            # Continue walking so TC -> Story -> Epic is fully inherited.
            current = parent
            depth += 1

        # Keep direct Requirement_ID untouched. Requirements are a logical
        # relationship from the Test Case, not a Jira parent in this project.
        row["Story_ID"] = row.get("User_Story_ID", "")
        row["User Story ID"] = row.get("User_Story_ID", "")
        row["Requirement ID"] = row.get("Requirement_ID", "")
        row["Epic ID"] = row.get("Epic_ID", "")
        row["Module ID"] = row.get("Module_ID", "")
        row["Change Status"] = row.get("Change_Status", "")

    def _jira_issue_category(
        self,
        row: dict[str, Any],
    ) -> str:
        """Classify Jira issues into the logical blocks used by the agents."""

        work_item_id = str(row.get("work_item_id") or "").strip().upper()
        issue_type = self._normalize_key(row.get("issue_type"))

        if issue_type in {"TEST_EXECUTION", "EXECUTION"} or work_item_id.startswith("EX-"):
            return "executions"
        if issue_type in {"FLAKY_TEST_RECORD", "FLAKY_TEST"} or work_item_id.startswith("FLAKY-"):
            return "flaky_tests"
        if issue_type in {"BUG", "DEFECT"} or work_item_id.startswith("DEF-"):
            return "defects"
        if issue_type == "MODULE" or work_item_id.startswith("MOD-"):
            return "modules"
        if issue_type == "RELEASE" or work_item_id.startswith("REL-"):
            return "releases"
        if issue_type in {"RISK_POLICY", "POLICY"} or work_item_id.startswith("POL-"):
            return "policies"
        if issue_type in {"RELEASE_RULE", "RULE"} or work_item_id.startswith("RULE-"):
            return "release_rules"

        # Test Case issues are subtasks in this project. Check this before the
        # requirement fallback because Test Cases also carry Requirement_ID.
        if (
            work_item_id.startswith("TC-")
            or row.get("Test_Case_ID")
            or row.get("Test_Status")
            or row.get("Automation_Status")
            or issue_type in {"SUBTASK", "SUB_TASK", "TEST", "TEST_CASE"}
        ):
            return "test_cases"

        if issue_type == "EPIC" or work_item_id.startswith("EP-"):
            return "epics"
        if issue_type == "STORY" or work_item_id.startswith("US-"):
            return "stories"

        # Jira work type in this project is literally spelled "Requirment".
        if (
            work_item_id.startswith("REQ-")
            or row.get("Requirement_ID")
            or row.get("Business_Priority")
            or issue_type in {"REQUIREMENT", "REQUIRMENT"}
        ):
            return "requirements"

        if row.get("Requirement_ID"):
            return "requirements"
        if row.get("User_Story_ID"):
            return "stories"
        return "epics"

    def _extract_work_item_id(
        self,
        summary: str,
        issue_key: str,
    ) -> str:
        match = re.search(
            r"\[\s*([A-Za-z]{2,10}-\d+(?:\.\d+)?)\s*\]",
            summary or "",
        )
        if match:
            return match.group(1).strip()
        return issue_key

    def _strip_work_item_prefix(
        self,
        summary: str,
    ) -> str:
        cleaned = re.sub(
            r"^\s*\[[^\]]+\]\s*",
            "",
            summary or "",
        ).strip()
        return cleaned or (summary or "").strip()

    def _field_text(
        self,
        fields_or_value: dict[str, Any] | Any,
        field_id: str | None = None,
    ) -> str:
        """
        Convert Jira field values into normalized text.

        Supports both ``_field_text(fields, field_id)`` and
        ``_field_text(value)``. Jira custom fields may return strings,
        option dictionaries, lists of options, or scalar values.
        """
        value = (
            fields_or_value.get(field_id, "")
            if field_id is not None and isinstance(fields_or_value, dict)
            else fields_or_value
        )
        return self._normalize_jira_field_text(value)

    @staticmethod
    def _normalize_jira_field_text(value: Any) -> str:
        """Normalize a raw Jira field value into stable text."""
        if value is None:
            return ""

        if isinstance(value, str):
            return value.strip()

        if isinstance(value, dict):
            for key in ("value", "name", "displayName", "key"):
                if value.get(key) is not None:
                    return str(value[key]).strip()
            return str(value).strip()

        if isinstance(value, list):
            values: list[str] = []
            for item in value:
                if isinstance(item, dict):
                    extracted: str | None = None
                    for key in ("value", "name", "displayName", "key"):
                        if item.get(key) is not None:
                            extracted = str(item[key]).strip()
                            break
                    if extracted:
                        values.append(extracted)
                elif item is not None:
                    item_text = str(item).strip()
                    if item_text:
                        values.append(item_text)
            return ", ".join(values)

        return str(value).strip()

    def _normalize_key(
        self,
        value: Any,
    ) -> str:
        return (
            str(value or "")
            .strip()
            .upper()
            .replace(" ", "_")
            .replace("-", "_")
        )

    def _release_id_variants(
        self,
        value: Any,
    ) -> set[str]:
        """
        Every normalized form a release identifier might be typed or stored
        as, so a tester can query a release as '25.4', 'REL-25.4',
        'rel-25.4', '24', etc. and reach the same release regardless of
        which form Jira itself stores (a label, Fix Version, or Release
        issue's own identifier). Case is already unified by _normalize_key;
        this additionally unifies the presence/absence of a 'REL' prefix.

        Only strips/adds the prefix immediately before a digit, so real
        words like 'RELEASE' or 'RELIABLE' are never mistaken for a
        prefixed release id.
        """
        normalized = self._normalize_key(value)

        if not normalized:
            return set()

        stripped = re.sub(r"^REL_?(?=\d)", "", normalized)

        if stripped != normalized:
            return {normalized, stripped}

        return {normalized, f"REL_{normalized}"}


    def _run_stage(
        self,
        state: PipelineState,
        agent_name: str,
        function: Callable[
            [],
            A2AResponse,
        ],
        stage_key: str | None = None,
        tool_ref: Callable[..., Any] | None = None,
        tool_args: dict[str, Any] | None = None,
    ) -> A2AResponse:
        """
        Execute one pipeline stage and record its audit status.

        tool_ref/tool_args are purely for app.tracing (optional, additive):
        when given, they name the real business-logic function this stage
        calls and its real keyword arguments, so its docstring/input/output
        can be recorded as one tool_calls/ entry under this agent's trace.
        Neither is ever passed to `function` itself, which is invoked
        exactly as before this parameter existed.
        """

        started_at = datetime.now(
            timezone.utc
        )

        if stage_key:
            self._emit_stage(stage_key, "running", f"Running {agent_name}…", agent_name=agent_name)

        run_trace = getattr(self, "_run_trace", None)
        agent_trace = None
        if run_trace is not None:
            try:
                agent_trace = tracing.start_agent_trace(
                    run_trace, agent_name=agent_name, input_data=tool_args or {}
                )
            except Exception:
                logger.exception("tracing: failed to start agent trace for %s", agent_name)

        try:
            result = function()

            if not isinstance(
                result,
                A2AResponse
            ):
                raise TypeError(
                    f"{agent_name} returned "
                    f"{type(result).__name__}; "
                    "expected A2AResponse."
                )

            state.audit_log.append(
                AgentRun(
                    agent=agent_name,
                    status="COMPLETED",
                    summary={
                        "records": (
                            self._result_size(
                                result.data
                            )
                        )
                    },
                    started_at=started_at,
                    completed_at=datetime.now(
                        timezone.utc
                    ),
                )
            )

            if agent_trace is not None:
                try:
                    if tool_ref is not None:
                        duration_ms = (datetime.now(timezone.utc) - started_at).total_seconds() * 1000
                        tracing.record_tool_call(
                            agent_trace,
                            tool_name=getattr(tool_ref, "__name__", agent_name),
                            docstring=inspect.getdoc(tool_ref),
                            args=tool_args or {},
                            response=result.data,
                            status="SUCCESS",
                            duration_ms=duration_ms,
                        )
                    tracing.finish_agent_trace(agent_trace, output_data=result.data, status="SUCCESS")
                except Exception:
                    logger.exception("tracing: failed to finish agent trace for %s", agent_name)

            if stage_key:
                self._emit_stage(stage_key, "finished", f"{agent_name} complete.", agent_name=agent_name)

            return result

        except Exception as exc:
            state.audit_log.append(
                AgentRun(
                    agent=agent_name,
                    status="FAILED",
                    summary={
                        "error_type": (
                            type(exc).__name__
                        ),
                        "error": str(exc),
                    },
                    started_at=started_at,
                    completed_at=datetime.now(
                        timezone.utc
                    ),
                )
            )

            if agent_trace is not None:
                try:
                    if tool_ref is not None:
                        duration_ms = (datetime.now(timezone.utc) - started_at).total_seconds() * 1000
                        tracing.record_tool_call(
                            agent_trace,
                            tool_name=getattr(tool_ref, "__name__", agent_name),
                            docstring=inspect.getdoc(tool_ref),
                            args=tool_args or {},
                            response=None,
                            status="FAILED",
                            duration_ms=duration_ms,
                            error=str(exc),
                        )
                    tracing.finish_agent_trace(agent_trace, status="FAILED", error=exc)
                except Exception:
                    logger.exception("tracing: failed to finish (failed) agent trace for %s", agent_name)

            if stage_key:
                self._emit_stage(stage_key, "failed", f"{agent_name} failed: {exc}", agent_name=agent_name)

            raise

    @staticmethod
    def _result_size(
        result: dict[str, Any],
    ) -> int:
        """
        Estimate how many records an agent produced.
        """

        candidate_keys = (
            "results",
            "records",
            "test_summaries",
            "test_tags",
            "module_assignments",
            "direct_impacts",
            "changed_requirements",
            "regulatory_tests",
            "release_rules",
        )

        for key in candidate_keys:
            value = result.get(
                key
            )

            if isinstance(
                value,
                (list, dict),
            ):
                return len(value)

        return len(result)

    @staticmethod
    def _require_mapping_key(
        mapping: dict[str, Any],
        key: str,
        context: str,
    ) -> Any:
        """
        Return a required mapping value or raise a clear error.
        """

        value = mapping.get(
            key
        )

        if value is None:
            raise KeyError(
                f"{context} did not provide required "
                f"field {key!r}."
            )

        return value

    def _send_message(
        self,
        sender: str,
        receiver: str,
        message_type: str,
        payload: dict[str, Any],
    ) -> None:
        """
        Send one structured message through the in-memory message bus.
        """

        # A2A: Persist the same serializable envelope used by the specialist
        # boundary so audit history contains explicit sender/receiver/type/data.
        envelope = make_request(
            sender=sender,
            receiver=receiver,
            message_type=message_type,
            release_id=str(payload.get("release_id") or "").strip().upper(),
            data=payload,
        )
        self.message_bus.send(
            sender,
            receiver,
            message_type,
            envelope.model_dump(mode="json"),
        )

        run_trace = getattr(self, "_run_trace", None)
        if run_trace is not None:
            try:
                tracing.record_a2a(
                    run_trace,
                    "A2A_REQUEST",
                    source_agent=sender,
                    destination_agent=receiver,
                    payload=envelope.model_dump(mode="json"),
                    message_type=message_type,
                )
            except Exception:
                logger.exception("tracing: failed to record A2A event for %s -> %s", sender, receiver)

    # A2A: Query routing uses the same Master-owned Jira snapshot and specialist
    # outputs as the pipeline. The specialist never reads Jira directly.
    _AGENT_QUERY_SPECS: dict[str, dict[str, Any]] = {
        "feature": {
            "name": "Feature / Epic Change Impact Agent",
            "module": "app.agents.feature_change_agent.tools",
            "source_blocks": FEATURE_INPUT_BLOCKS,
            "state_attr": "change_impact",
        },
        "change": {
            "name": "Feature / Epic Change Impact Agent",
            "module": "app.agents.feature_change_agent.tools",
            "source_blocks": FEATURE_INPUT_BLOCKS,
            "state_attr": "change_impact",
        },
        "criticality": {
            "name": "Application Criticality Classification Agent",
            "module": "app.agents.criticality_agent.tools",
            "source_blocks": ("modules", "test_cases", "tier_change_log"),
            "state_attr": "criticality",
        },
        "history": {
            "name": "Historical Execution Intelligence Agent",
            "module": "app.agents.historical_agent.tools",
            "source_blocks": HISTORICAL_INPUT_BLOCKS,
            "state_attr": "history",
        },
        "historical": {
            "name": "Historical Execution Intelligence Agent",
            "module": "app.agents.historical_agent.tools",
            "source_blocks": HISTORICAL_INPUT_BLOCKS,
            "state_attr": "history",
        },
        "policy": {
            "name": "Policy / Risk Appetite Calibration Agent",
            "module": "app.agents.policy_agent.tools",
            "source_blocks": POLICY_INPUT_BLOCKS,
            "state_attr": "policy",
        },
        "risk": {
            "name": "Policy / Risk Appetite Calibration Agent",
            "module": "app.agents.policy_agent.tools",
            "source_blocks": POLICY_INPUT_BLOCKS,
            "state_attr": "policy",
        },
        "scoring": {
            "name": "Decision Engine / Risk Scoring Agent",
            "module": "app.agents.scoring_agent.tools",
            "source_blocks": SCORING_INPUT_BLOCKS,
            "state_attr": "scoring",
        },
        "selection": {
            "name": "Decision Engine / Risk Scoring Agent",
            "module": "app.agents.scoring_agent.tools",
            "source_blocks": SCORING_INPUT_BLOCKS,
            "state_attr": "scoring",
        },
        "governance": {
            "name": "Exclusion Risk & Governance Agent",
            "module": "app.agents.governance_agent.tools",
            "source_blocks": (),
            "state_attr": "governance",
        },
        "exclusion": {
            "name": "Exclusion Risk & Governance Agent",
            "module": "app.agents.governance_agent.tools",
            "source_blocks": (),
            "state_attr": "governance",
        },
    }

    def _agent_query_source_data(
        self,
        agent_key: str,
        state: PipelineState,
    ) -> dict[str, list[dict[str, Any]]]:
        """Return only the source blocks needed by one specialist query."""
        spec = self._AGENT_QUERY_SPECS.get(agent_key)
        if not spec:
            raise ValueError(
                f"Unknown agent {agent_key!r}. Supported agents: "
                f"{sorted(self._AGENT_QUERY_SPECS)}"
            )

        # A2A: Post-run specialist queries receive the exact source blocks used
        # by the completed pipeline. Do not reload Jira for a conversational query.
        cached_source = self.get_cached_source_data(state.release_id)
        if not cached_source and agent_key not in {"scoring", "selection", "governance", "exclusion"}:
            raise RuntimeError(
                f"No completed Master source snapshot is available for release "
                f"{state.release_id}. Run the release pipeline after installing the updated Master Orchestrator."
            )

        source_data = {
            block: list(cached_source.get(block, []))
            for block in spec["source_blocks"]
            if block in cached_source
        }

        # A2A: Downstream agents receive earlier specialist outputs as structured
        # data, never as hidden objects or infrastructure references.
        if agent_key in {"scoring", "selection"}:
            source_data = dict(source_data)
            source_data["change_impact"] = [state.change_impact]
            source_data["criticality"] = [state.criticality]
            source_data["history"] = [state.history]
            source_data["policy"] = [state.policy]
            # Keep post-run scoring queries compatible with both the current
            # optional-input Scoring Agent and older runtimes that validate these
            # configuration blocks at the orchestrator boundary.
            policy_payload = state.policy.get("agent_output", state.policy) if isinstance(state.policy, dict) else {}
            configured_weights = policy_payload.get("scoring_weights") or policy_payload.get("weights") or []
            configured_thresholds = policy_payload.get("thresholds") or policy_payload.get("risk_thresholds") or []
            if not configured_weights:
                configured_weights = [{"Factor": factor, "Weight": value} for factor, value in DEFAULT_WEIGHTS.items()]
            if not configured_thresholds:
                configured_thresholds = [{"Classification": cls, "Minimum_Score": value} for cls, value in DEFAULT_THRESHOLDS.items()]
            source_data["scoring_weights"] = configured_weights if isinstance(configured_weights, list) else []
            source_data["thresholds"] = configured_thresholds if isinstance(configured_thresholds, list) else []
        elif agent_key in {"governance", "exclusion"}:
            source_data = {
                "scoring": [state.scoring],
                "policy": [state.policy],
            }

        return source_data

    # A raw chat query is classified here, and only here — the frontend
    # forwards whatever the user typed unchanged; the Master alone decides
    # whether it needs a full pipeline run or a cached-context answer.
    _PIPELINE_RUN_RELEASE_TOKEN_RE = re.compile(r"\b(?:REL-?|R)?\d{1,3}\.\d+\b", re.IGNORECASE)
    _PIPELINE_RUN_TRIGGER_VERB_RE = re.compile(
        r"\b(analy[sz]e|run|start|trigger|kick off|execute)\b", re.IGNORECASE
    )

    @classmethod
    def detect_pipeline_run_request(cls, query: str) -> str | None:
        """Decide whether a raw user query is asking to run the full Risk
        Tier pipeline for a specific release, or is a conversational
        drill-down question instead.

        Returns the extracted release id for a pipeline-run request, or None
        if the query should be answered from cached pipeline state instead.
        A bare token (e.g. "R25.4") counts as a run request on its own; any
        other phrasing needs an explicit trigger verb alongside a release
        token (e.g. "analyze release R25.4").
        """
        trimmed = str(query or "").strip()
        if not trimmed:
            return None

        if len(trimmed) <= 20 and len(trimmed.split()) <= 2:
            bare_match = cls._PIPELINE_RUN_RELEASE_TOKEN_RE.search(trimmed)
            if bare_match:
                return bare_match.group(0).upper()

        if cls._PIPELINE_RUN_TRIGGER_VERB_RE.search(trimmed):
            match = cls._PIPELINE_RUN_RELEASE_TOKEN_RE.search(trimmed)
            if match:
                return match.group(0).upper()

        return None

    @staticmethod
    def _detect_query_agents(question: str) -> list[str]:
        """Infer one or more specialist agents from the user's question.

        ADK should not choose the specialist. The Master owns routing so a
        cross-agent question can consult multiple authoritative pipeline stages.
        """
        text = str(question or "").strip().lower()
        if not text:
            logger.info("QUERY_ROUTING | question=<empty> | routed_to=['scoring'] | reason=empty_question")
            return ["scoring"]

        scores: dict[str, int] = {
            "feature": 0,
            "criticality": 0,
            "history": 0,
            "policy": 0,
            "scoring": 0,
            "governance": 0,
        }

        keyword_groups = {
            "feature": (
                "feature", "change impact", "changed epic", "epic", "user story",
                "story", "requirement", "traceability", "downstream", "directly impacted",
                "new feature", "mapping", "scope",
            ),
            "criticality": (
                "criticality", "critical", "tier 1", "tier-1", "tier 2", "tier-2",
                "tier 3", "tier-3", "tier 4", "tier-4", "module tier", "application tier",
            ),
            "history": (
                "historical", "history", "execution", "executions", "pass rate", "passed",
                "failed", "defect", "defects", "flaky", "recency", "insufficient history",
                "consistent pass", "zero defect", "historical value",
            ),
            "policy": (
                "policy", "risk appetite", "regulatory", "mandatory", "exclusion prohibited",
                "maximum exclusion", "exclusion cap", "approval role", "qa lead", "business owner",
                "release type",
            ),
            "scoring": (
                "score", "scoring", "classification", "must-test", "must test", "recommended",
                "optional", "exclude candidate", "exclude", "composite", "risk band",
                "risk scoring", "selected tests", "selection", "why only", "difference between",
            ),
            "governance": (
                "governance", "approval", "approved exclusion", "pending approval",
                "residual risk", "risk statement", "waiver",
            ),
        }

        for agent_key, keywords in keyword_groups.items():
            for keyword in keywords:
                if keyword in text:
                    scores[agent_key] += 1

        # Questions about totals/selection differences normally require both the
        # upstream impact source and the final scoring result. Historical context
        # is also useful when the wording asks why a population changed.
        if (
            ("how many" in text or "why only" in text or "difference" in text or "why" in text)
            and "test" in text
        ):
            scores["scoring"] += 2
            scores["feature"] += 1

        ordered = sorted(
            (key for key, value in scores.items() if value > 0),
            key=lambda key: (-scores[key], ("feature", "criticality", "history", "policy", "scoring", "governance").index(key)),
        )

        # If no specialist-specific signal exists, answer from scoring because it
        # is the final decision stage and has the compact classification result.
        if ordered:
            logger.info(
                "QUERY_ROUTING | question=%r | routed_to=%s | reason=keyword_match | scores=%s",
                question, ordered, {k: v for k, v in scores.items() if v > 0},
            )
            return ordered

        logger.info(
            "QUERY_ROUTING | question=%r | routed_to=['scoring'] | reason=general_query_no_keyword_match",
            question,
        )
        return ["scoring"]

    def _answer_single_agent_question(
        self,
        normalized_release_id: str,
        agent_key: str,
        question_text: str,
        state: PipelineState,
    ) -> dict[str, Any]:
        """Query one specialist through the Master-owned A2A boundary."""
        if agent_key not in self._AGENT_QUERY_SPECS:
            raise ValueError(
                f"Unknown agent {agent_key!r}. Supported agents: "
                f"{sorted(self._AGENT_QUERY_SPECS)}"
            )

        spec = self._AGENT_QUERY_SPECS[agent_key]
        agent_output = getattr(state, spec["state_attr"]) or {}
        if not isinstance(agent_output, dict):
            agent_output = {"value": agent_output}
        compact_context = self.get_cached_agent_context(
            normalized_release_id,
            agent_key,
            question_text,
        )
        # get_cached_agent_context always attaches the targeted agent's own
        # raw output under "agent_output" (see that method), independent of
        # whatever extra topic-specific summary `question_kind` bolts on —
        # so a single check here covers every agent uniformly instead of
        # each one checking a different, `kind`-coupled key name that only
        # happened to be present for some question phrasings.
        if "agent_output" not in compact_context:
            raise RuntimeError(
                f"{spec['name']} context is missing agent_output."
            )
        source_data = compact_context.get("traceability", {}) if isinstance(compact_context, dict) else {}

        request = make_request(
            sender=self.name,
            receiver=spec["name"],
            message_type="AGENT_QUERY",
            release_id=normalized_release_id,
            data={
                "question": question_text,
                "agent_context": compact_context,
            },
        )

        response: A2AResponse | None = None
        handler_error: Exception | None = None
        try:
            module = importlib.import_module(spec["module"])
            handler = getattr(module, "handle_a2a_request", None)
            if not callable(handler):
                raise RuntimeError(
                    f"{spec['name']} does not expose an A2A handle_a2a_request function."
                )
            candidate = handler(request)
            if not isinstance(candidate, A2AResponse):
                raise TypeError(
                    f"{spec['name']} returned {type(candidate).__name__} for AGENT_QUERY; expected A2AResponse."
                )
            response = candidate
        except Exception as exc:
            handler_error = exc
            response = None

        if self._is_traceability_mapping_question(question_text) and agent_key in {"feature", "change"}:
            trace = compact_context.get("traceability", {}) if isinstance(compact_context, dict) else {}
            markdown = self._format_feature_traceability_mapping(
                state=state,
                source_data=trace,
            )
        else:
            response_data = (
                response.data
                if isinstance(response, A2AResponse)
                else {}
            )
            if not isinstance(response_data, dict):
                response_data = {"answer": str(response_data)}
            markdown = response_data.get("markdown")
            if not isinstance(markdown, str) or self._looks_like_context_dump(markdown):
                markdown = self._format_agent_query_answer(
                    agent_key=agent_key,
                    question=question_text,
                    state=state,
                    agent_output=agent_output,
                    source_data=source_data,
                )

        return {
            "agent_key": agent_key,
            "agent": spec["name"],
            "markdown": markdown,
            "a2a_handler_fallback": bool(handler_error),
        }

    def answer_agent_question(
        self,
        release_id: str,
        question: str,
        agent: str | None = None,
        model_id: str = "gpt-5-mini",
    ) -> dict[str, Any]:
        """Answer a post-run question using Master-owned automatic routing.

        ``agent`` is retained as an optional backward-compatible override for
        internal callers, but ADK-facing callers should omit it. The Master
        automatically detects one or more specialists and merges their evidence.
        """
        normalized_release_id = str(release_id or "").strip().upper()
        question_text = str(question or "").strip()

        logger.info(
            "MASTER_QUERY_STARTED | release=%s | question=%r | explicit_agent=%s",
            normalized_release_id, question_text, agent,
        )

        if not normalized_release_id:
            raise ValueError("release_id cannot be empty.")
        if not question_text:
            raise ValueError("question is required.")

        state = self.get_cached_state(normalized_release_id)
        if state is None:
            logger.warning(
                "MASTER_QUERY_NO_CACHE | release=%s | question=%r",
                normalized_release_id, question_text,
            )
            raise RuntimeError(
                f"No completed pipeline state is available for {normalized_release_id}. "
                "Run execute_risk_tier_pipeline once before asking drill-down questions."
            )

        agent_keys = [str(agent).strip().lower()] if agent else self._detect_query_agents(question_text)
        agent_keys = [key for key in agent_keys if key in self._AGENT_QUERY_SPECS]
        if not agent_keys:
            agent_keys = ["scoring"]

        # De-duplicate aliased routing keys while preserving order.
        seen: set[str] = set()
        deduplicated_agent_keys: list[str] = []
        for key in agent_keys:
            if key in seen:
                continue
            seen.add(key)
            deduplicated_agent_keys.append(key)
        agent_keys = deduplicated_agent_keys

        results = [
            self._answer_single_agent_question(
                normalized_release_id=normalized_release_id,
                agent_key=key,
                question_text=question_text,
                state=state,
            )
            for key in agent_keys
        ]

        if len(results) == 1:
            markdown = results[0]["markdown"]
        else:
            lines = [
                f"## Risk Tier Master Answer — {normalized_release_id}",
                "",
                f"**Question:** {question_text}",
                "",
                "The Master Orchestrator consulted the following specialist agents:",
                "",
            ]
            for result in results:
                lines.extend([
                    f"- {result['agent']}",
                ])
            lines.append("")
            for result in results:
                lines.extend([
                    "---",
                    "",
                    f"### {result['agent']}",
                    "",
                    str(result["markdown"]),
                    "",
                ])
            markdown = "\n".join(lines).strip()

        logger.info(
            "MASTER_QUERY_COMPLETED | release=%s | question=%r | agents_consulted=%s | a2a_handler_fallback=%s",
            normalized_release_id, question_text, agent_keys,
            any(result["a2a_handler_fallback"] for result in results),
        )

        return {
            "status": "success",
            "release_id": normalized_release_id,
            "agents_consulted": [self._AGENT_QUERY_SPECS[key]["name"] for key in agent_keys],
            "message_type": "AGENT_QUERY",
            "markdown": markdown,
            "a2a_handler_fallback": any(result["a2a_handler_fallback"] for result in results),
        }

    @staticmethod
    def _looks_like_context_dump(markdown: str) -> bool:
        """Detect the old generic JSON context-dump response."""
        lowered = markdown.lower()
        return (
            "## specialist context" in lowered
            or "```json" in lowered and "agent_output" in lowered
            or '"question":' in lowered and '"context":' in lowered
        )

    @staticmethod
    def _is_traceability_mapping_question(question: str) -> bool:
        lowered = str(question or "").lower()
        return (
            ("epic" in lowered and "story" in lowered and "requirement" in lowered and "test" in lowered)
            or "epic -> story" in lowered
            or "epic → story" in lowered
            or ("traceability" in lowered and "mapping" in lowered)
        )

    @staticmethod
    def _first_text(row: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                text = str(value).strip()
                if text:
                    return text
        return ""

    def _format_feature_traceability_mapping(
        self,
        state: PipelineState,
        source_data: dict[str, list[dict[str, Any]]],
    ) -> str:
        """Render authoritative Epic -> Story -> Requirement -> Tests data.

        A2A: This formatter consumes the same structured blocks the Master sent
        to the Feature Agent. It does not infer relationships from scoring.
        """
        epics = source_data.get("epics", [])
        stories = source_data.get("stories", [])
        requirements = source_data.get("requirements", [])
        rtm = source_data.get("rtm", [])

        tests_by_requirement: dict[str, list[str]] = {}
        for mapping in rtm:
            req_id = self._first_text(mapping, "Requirement_ID", "Requirement ID")
            tc_id = self._first_text(mapping, "Test_Case_ID", "Test Case ID")
            if req_id and tc_id:
                tests_by_requirement.setdefault(req_id, []).append(tc_id)

        requirements_by_story: dict[str, list[dict[str, Any]]] = {}
        for requirement in requirements:
            story_id = self._first_text(
                requirement,
                "User_Story_ID",
                "Story_ID",
                "User Story ID",
            )
            if story_id:
                requirements_by_story.setdefault(story_id, []).append(requirement)

        epic_by_issue_key: dict[str, str] = {}
        for epic in epics:
            epic_key = self._first_text(epic, "issue_key", "work_item_id", "Epic_ID", "Epic ID")
            epic_id = self._first_text(epic, "Epic_ID", "Epic ID", "work_item_id", "issue_key")
            if epic_key and epic_id:
                epic_by_issue_key[epic_key] = epic_id

        stories_by_epic: dict[str, list[dict[str, Any]]] = {}
        for story in stories:
            epic_id = self._first_text(
                story,
                "Epic_ID",
                "Epic ID",
            )
            if not epic_id:
                parent_key = self._first_text(story, "parent_key")
                epic_id = epic_by_issue_key.get(parent_key, "")
            if epic_id:
                stories_by_epic.setdefault(epic_id, []).append(story)

        lines = [
            f"## Epic → Story → Requirement → Tests — {state.release_id}",
            "",
            "Source: completed Master Orchestrator release snapshot.",
            "",
        ]

        if not epics:
            lines.append("No in-scope Epic records were supplied by the Master Orchestrator.")
            return "\n".join(lines)

        for epic in epics:
            epic_id = self._first_text(
                epic,
                "Epic_ID",
                "Epic ID",
                "work_item_id",
                "issue_key",
            )
            epic_name = self._first_text(
                epic,
                "Epic_Name",
                "Epic Name",
                "summary",
            )
            lines.append(
                f"### `{epic_id}`"
                + (f" — {epic_name}" if epic_name and epic_name != epic_id else "")
            )

            epic_stories = stories_by_epic.get(epic_id, [])
            if not epic_stories:
                lines.append("- No mapped stories found in the release snapshot.")
                lines.append("")
                continue

            for story in epic_stories:
                story_id = self._first_text(
                    story,
                    "User_Story_ID",
                    "Story_ID",
                    "User Story ID",
                    "work_item_id",
                    "issue_key",
                )
                story_name = self._first_text(
                    story,
                    "User_Story_Name",
                    "Story Name",
                    "summary",
                )
                lines.append(
                    f"- **Story `{story_id}`**"
                    + (f" — {story_name}" if story_name and story_name != story_id else "")
                )

                story_requirements = requirements_by_story.get(story_id, [])
                if not story_requirements:
                    lines.append("  - No mapped requirements found in the release snapshot.")
                    continue

                for requirement in story_requirements:
                    req_id = self._first_text(
                        requirement,
                        "Requirement_ID",
                        "Requirement ID",
                        "work_item_id",
                        "issue_key",
                    )
                    req_name = self._first_text(
                        requirement,
                        "Requirement_Name",
                        "Requirement Name",
                        "summary",
                        "Requirement_Description",
                    )
                    lines.append(
                        f"  - **Requirement `{req_id}`**"
                        + (f" — {req_name}" if req_name and req_name != req_id else "")
                    )
                    test_ids = sorted(set(tests_by_requirement.get(req_id, [])))
                    if test_ids:
                        lines.append(
                            "    - Tests: " + ", ".join(f"`{tc}`" for tc in test_ids)
                        )
                    else:
                        lines.append("    - Tests: **TRACEABILITY GAP**")

            lines.append("")

        return "\n".join(lines).strip()

    @staticmethod
    def _unwrap_agent_output(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        nested = value.get("agent_output")
        return nested if isinstance(nested, dict) else value

    @staticmethod
    def _normalize_test_id(value: Any) -> str:
        return str(value or "").strip().upper()

    def _format_population_reconciliation(
        self,
        state: PipelineState,
        question: str,
    ) -> str:
        """Explain direct-impact vs scoring population using exact cached IDs."""
        change = self._unwrap_agent_output(state.change_impact)
        scoring = self._unwrap_agent_output(state.scoring)
        direct_ids = {
            self._normalize_test_id(value)
            for value in change.get("direct_test_ids", [])
            if self._normalize_test_id(value)
        }
        results = scoring.get("results", [])
        classified_ids = {
            self._normalize_test_id(row.get("test_case_id"))
            for row in results
            if isinstance(row, dict) and self._normalize_test_id(row.get("test_case_id"))
        }
        missing = sorted(direct_ids - classified_ids)
        extra = sorted(classified_ids - direct_ids)

        lines = [
            f"### Direct Impact vs Final Classification — {state.release_id}",
            f"- Directly impacted test cases: **{len(direct_ids)}**",
            f"- Test cases present in final scoring results: **{len(classified_ids)}**",
            f"- Direct-impact tests missing from scoring: **{len(missing)}**",
            f"- Classified tests not in direct-impact set: **{len(extra)}**",
        ]

        if missing:
            lines.extend(["", "**Direct-impact IDs missing from scoring:**"])
            source_rows = {}
            for row in self.get_cached_source_data(state.release_id).get("test_cases", []):
                if isinstance(row, dict):
                    key = self._normalize_test_id(
                        row.get("Test_Case_ID")
                        or row.get("Test Case ID")
                        or row.get("work_item_id")
                        or row.get("issue_key")
                    )
                    if key:
                        source_rows[key] = row
            for test_id in missing:
                row = source_rows.get(test_id)
                if not row:
                    lines.append(f"- `{test_id}` — no matching test-case row exists in the persisted Master source snapshot.")
                    continue
                status = str(
                    row.get("Test_Status")
                    or row.get("Test Status")
                    or row.get("status")
                    or ""
                ).strip()
                lines.append(
                    f"- `{test_id}` — source snapshot status=`{status or 'not populated'}`; it was not present in final scoring results."
                )
        if extra:
            lines.extend(["", "**Scoring tests outside the direct-impact set:**"])
            lines.append("- " + ", ".join(f"`{item}`" for item in extra))

        lines.extend(["", "This reconciliation uses the exact IDs emitted by the Change Impact and Scoring stages; it does not infer a count from prose."])
        return "\n".join(lines)

    def _format_optional_score_answer(
        self,
        state: PipelineState,
        question: str,
    ) -> str:
        scoring = self._unwrap_agent_output(state.scoring)
        results = [
            row for row in scoring.get("results", [])
            if isinstance(row, dict) and str(row.get("classification") or "").strip().upper() == "OPTIONAL"
        ]
        scores = [
            float(row["composite_score"])
            for row in results
            if row.get("composite_score") not in (None, "")
        ]
        lines = [
            f"### Optional Test Composite Scores — {state.release_id}",
            f"- Optional test count: **{len(results)}**",
        ]
        if scores:
            ordered = sorted(scores)
            avg = sum(scores) / len(scores)
            median = ordered[len(ordered) // 2] if len(ordered) % 2 else (ordered[len(ordered)//2 - 1] + ordered[len(ordered)//2]) / 2
            lines.extend([
                f"- Minimum composite score: **{min(scores):.2f}**",
                f"- Maximum composite score: **{max(scores):.2f}**",
                f"- Average composite score: **{avg:.2f}**",
                f"- Median composite score: **{median:.2f}**",
                "",
                "| Test Case | Composite Score |",
                "|---|---:|",
            ])
            for row in sorted(results, key=lambda item: self._normalize_test_id(item.get("test_case_id"))):
                score = row.get("composite_score")
                lines.append(f"| `{row.get('test_case_id')}` | {float(score):.2f} |")
        else:
            lines.append("- No numeric composite scores were stored for the Optional classification rows.")
        return "\n".join(lines)

    def _format_protection_flag_answer(
        self,
        state: PipelineState,
        question: str,
        agent_output: dict[str, Any],
    ) -> str:
        """Answer "which tests were prevented from being downgraded, and by which flag?".

        A row qualifies when its final classification differs from what the
        raw composite score alone would have produced
        (``classification_overridden``, set by the Scoring Agent itself —
        see app/agents/scoring_agent/tools.py) and it actually carries at
        least one protection flag — i.e. a hard protection rule changed the
        outcome, not just a scoring-band boundary. Optionally scoped to one
        tier if the question names one (e.g. "Tier-1").
        """
        question_lower = question.lower()
        rows = self._flatten_result_rows(agent_output)

        tier_filter: int | None = None
        tier_match = re.search(r"\btier[\s-]*([1-4])\b", question_lower)
        if tier_match:
            tier_filter = int(tier_match.group(1))

        protected_rows = [
            row for row in rows
            if row.get("classification_overridden")
            and row.get("protection_flags")
            and (tier_filter is None or str(row.get("tier")) == str(tier_filter))
        ]

        scope_label = f"Tier-{tier_filter} " if tier_filter else ""
        lines = [
            f"### {scope_label}Tests Protected From Downgrade — {state.release_id}",
            f"**Question:** {question}",
            "",
        ]

        if not protected_rows:
            lines.append(
                f"No {scope_label}tests were found where a protection flag changed the "
                "final classification away from the raw composite score."
            )
            return "\n".join(lines)

        lines.append(f"- Count: **{len(protected_rows)}**")
        lines.append("")
        lines.append("| Test Case | Final Classification | Would-Have-Been | Triggering Protection Flag(s) |")
        lines.append("|---|---|---|---|")
        for row in sorted(protected_rows, key=lambda r: self._normalize_test_id(r.get("test_case_id"))):
            flags = ", ".join(f"`{flag}`" for flag in row.get("protection_flags", []))
            lines.append(
                f"| `{row.get('test_case_id')}` | **{row.get('classification')}** | "
                f"`{row.get('base_classification')}` | {flags} |"
            )
        return "\n".join(lines)

    def _format_agent_query_answer(
        self,
        agent_key: str,
        question: str,
        state: PipelineState,
        agent_output: dict[str, Any],
        source_data: dict[str, list[dict[str, Any]]],
    ) -> str:
        """Render compact, question-oriented evidence for ADK."""
        lines = [
            f"## {self._AGENT_QUERY_SPECS[agent_key]['name']} — {state.release_id}",
            "",
            f"**Question:** {question}",
            "",
        ]

        question_lower = question.lower()
        result_rows = self._flatten_result_rows(agent_output)

        # Common test-specific lookup for "why", classification, protection and
        # similar questions. The CSV-backed result is already in pipeline state.
        requested_test_ids = set(
            match.upper()
            for match in re.findall(r"\bTC-\d+\b", question, re.IGNORECASE)
        )

        if agent_key in {"scoring", "selection"} and "optional" in question_lower and ("composite" in question_lower or "score" in question_lower):
            return self._format_optional_score_answer(state, question)

        if agent_key in {"scoring", "selection"} and (
            ("prevented" in question_lower or "protect" in question_lower)
            and ("downgrad" in question_lower or "protection flag" in question_lower or "triggering" in question_lower)
        ):
            return self._format_protection_flag_answer(state, question, agent_output)

        if agent_key in {"scoring", "selection"} and ("directly impacted" in question_lower or "direct impact" in question_lower) and ("classified" in question_lower or "classification" in question_lower or "only" in question_lower or "difference" in question_lower):
            return self._format_population_reconciliation(state, question)

        if agent_key in {"scoring", "selection"} and requested_test_ids:
            matches = [
                row for row in result_rows
                if str(row.get("test_case_id") or "").upper() in requested_test_ids
            ]
            if matches:
                lines.append("### Test-level result")
                for row in matches[:10]:
                    lines.append(
                        f"- `{row.get('test_case_id')}`: "
                        f"**{row.get('classification', 'UNKNOWN')}**; "
                        f"tier=`{row.get('tier', 'N/A')}`; "
                        f"score=`{row.get('composite_score', 'N/A')}`"
                    )
                    reasons = row.get("reasons") or []
                    if isinstance(reasons, str):
                        reasons = [reasons]
                    for reason in list(reasons)[:8]:
                        lines.append(f"  - {reason}")
                return "\n".join(lines)

        # Feature / Change Impact evidence.
        if agent_key in {"feature", "change"}:
            summary = agent_output.get("summary", {}) if isinstance(agent_output, dict) else {}
            lines.extend([
                "### Change Impact",
                f"- In-scope epics: {summary.get('in_scope_epics', 0)}",
                f"- Changed user stories: {summary.get('changed_user_stories', 0)}",
                f"- Changed requirements: {summary.get('changed_requirements', 0)}",
                f"- Directly impacted tests: {summary.get('direct_test_cases', 0)}",
                f"- Downstream dependencies: {summary.get('downstream_dependencies', 0)}",
                f"- Downstream module test cases: {summary.get('downstream_module_test_cases', 0)}",
                f"- Additional downstream tests: {len(set(map(str, agent_output.get('downstream_test_ids', []))))}",
                f"- New-feature tests: {summary.get('new_feature_tests', 0)}",
                f"- Traceability gaps: {summary.get('traceability_gaps', 0)}",
            ])
            changed_epics = agent_output.get("changed_epics", [])

            if changed_epics:
                lines.append("")
                lines.append("### Changed Epics")

                for epic in changed_epics:

                    epic_id = (
                        epic.get("Epic_ID")
                        or epic.get("Epic ID")
                        or epic.get("work_item_id")
                        or epic.get("issue_key")
                        or "Unknown"
                    )

                    epic_name = (
                        epic.get("Epic_Name")
                        or epic.get("Epic Name")
                        or epic.get("summary")
                        or ""
                    )

                    if epic_name:
                        lines.append(f"- {epic_id} : {epic_name}")
                    else:
                        lines.append(f"- {epic_id}")

            if requested_test_ids:
                for test_id in sorted(requested_test_ids):
                    if test_id in set(map(str.upper, agent_output.get("direct_test_ids", []))):
                        lines.append(f"- `{test_id}` is in the direct-impact set.")
                    elif test_id in set(map(str.upper, agent_output.get("downstream_test_ids", []))):
                        lines.append(f"- `{test_id}` is in the additional downstream-impact set.")
                    else:
                        lines.append(f"- `{test_id}` is not present in the Feature Agent impact lists.")
            if "br-chg" in question_lower or "business rule" in question_lower or "validate" in question_lower:
                lines.extend([
                    "",
                    "### Business-rule evidence",
                    "- BR-CHG-01: evidence comes from release-scope Epic/Story linkage and out-of-scope handling.",
                    "- BR-CHG-02: evidence comes from changed Requirement IDs and RTM Requirement-to-Test mappings.",
                    "- BR-CHG-03: evidence comes from normalized one-way downstream dependencies and downstream test IDs.",
                    "- BR-CHG-04: evidence requires the requirement-level impact map; summary counts alone are not treated as proof.",
                    "- BR-CHG-05: evidence comes from new-requirement/new-epic protection and first-release coverage actions.",
                ])
                lines.append(f"- Source blocks supplied to the Feature Agent: {', '.join(sorted(source_data))}.")
            return "\n".join(lines)

        # Criticality evidence.
        if agent_key == "criticality":
            summary = agent_output.get("summary", {}) if isinstance(agent_output, dict) else {}
            lines.extend([
                "### Criticality",
                f"- Tier 1 modules: {summary.get('tier_1_modules', 0)}",
                f"- Tier 2 modules: {summary.get('tier_2_modules', 0)}",
                f"- Tier 3 modules: {summary.get('tier_3_modules', 0)}",
                f"- Tier 4 modules: {summary.get('tier_4_modules', 0)}",
                f"- Test tags produced: {len(agent_output.get('test_tags', {})) if isinstance(agent_output.get('test_tags'), dict) else 0}",
            ])
            assignments = agent_output.get("module_assignments", {})
            if isinstance(assignments, dict):
                for module_id, assignment in list(sorted(assignments.items()))[:20]:
                    if isinstance(assignment, dict):
                        lines.append(
                            f"- `{module_id}` -> `{assignment.get('final_tier', assignment.get('tier', 'N/A'))}`"
                        )
                    else:
                        lines.append(f"- `{module_id}` -> `{assignment}`")
            if "br-crit" in question_lower or "business rule" in question_lower or "validate" in question_lower:
                lines.extend([
                    "",
                    "### Business-rule checks",
                    "- BR-CRIT-01: weighted module factors determine Tier 1-4.",
                    "- BR-CRIT-02: each test inherits its mapped module tier; no independent lower test tier is allowed.",
                    "- BR-CRIT-03: Tier 1 requires 100% coverage; Tier 2 requires at least 70%; Tier 3/4 remain risk-based.",
                    "- BR-CRIT-04: qualifying production incidents require escalation; de-escalation requires approved governance evidence.",
                ])
                lines.append(f"- Source blocks supplied: {', '.join(sorted(source_data))}.")
            return "\n".join(lines)

        # Historical evidence.
        if agent_key in {"history", "historical"}:
            summary = agent_output.get("summary", {}) if isinstance(agent_output, dict) else {}
            lines.extend([
                "### Historical Execution",
                f"- Test cases analysed: {summary.get('total_test_cases', summary.get('test_cases_analysed', 0))}",
                f"- Executions: {summary.get('total_execution_records', summary.get('historical_executions', 0))}",
                f"- Passed: {summary.get('passed_executions', 0)}",
                f"- Failed: {summary.get('failed_executions', 0)}",
                f"- Confirmed defects: {summary.get('confirmed_defects', 0)}",
                f"- Defect-protected tests: {summary.get('defect_protected_tests', 0)}",
                f"- Flaky tests: {summary.get('flaky_test_count', summary.get('flaky_tests', 0))}",
                f"- Insufficient-history tests: {summary.get('tests_with_insufficient_history', 0)}",
                f"- Consistent-pass/zero-defect eligible tests: {summary.get('consistent_pass_zero_defect_eligible_tests', 0)}",
            ])
            for key, label in (
                ("defect_protected_test_ids", "Defect-protected tests"),
                ("flaky_test_ids", "Flaky tests"),
                ("insufficient_history_test_ids", "Insufficient-history tests"),
                ("consistent_pass_zero_defect_candidate_ids", "Consistent-pass candidates"),
            ):
                values = agent_output.get(key, [])
                if isinstance(values, (list, tuple, set)) and values:
                    lines.append(f"- {label}: {', '.join(map(str, sorted(values))) }")
            if "br-hist" in question_lower or "business rule" in question_lower or "validate" in question_lower:
                lines.extend([
                    "",
                    "### Business-rule checks",
                    "- Recent confirmed-defect protection is retained and must not be removed by score alone.",
                    "- Flakiness is remediation-only and does not reduce Historical Value Score.",
                    "- Insufficient history is an inclusion safeguard, not a reason for exclusion.",
                    "- Consistent-pass/zero-defect eligibility is limited to the configured Tier 3/4 conditions.",
                    "- Recency decay is applied before Historical Value Score contribution.",
                ])
            return "\n".join(lines)

        # Policy evidence.
        if agent_key in {"policy", "risk"}:
            summary = agent_output.get("summary", {}) if isinstance(agent_output, dict) else {}
            lines.extend([
                "### Risk Appetite / Policy",
                f"- Release type: {summary.get('release_type', agent_output.get('release_type', 'UNKNOWN'))}",
                f"- Regulatory tests: {summary.get('regulatory_test_count', 0)}",
                f"- Mandatory tests: {summary.get('mandatory_test_count', 0)}",
                f"- Exclusion-prohibited tests: {summary.get('exclusion_prohibited_test_count', 0)}",
                f"- Maximum overall exclusion: {summary.get('overall_max_exclusion_percent', agent_output.get('overall_max_exclusion', 0))}",
                f"- Approval required: {summary.get('require_approval_for_exclusion', summary.get('approval_required', True))}",
            ])
            if "br-risk" in question_lower or "business rule" in question_lower or "validate" in question_lower:
                lines.extend([
                    "",
                    "### Business-rule checks",
                    "- Regulatory/compliance tests are non-negotiable Must-Test.",
                    "- Release-type posture controls the applicable risk thresholds.",
                    "- Overall exclusion cannot exceed the configured cap without required leadership approval.",
                    "- Tier-specific exclusion tolerances are published with the policy result.",
                ])
            return "\n".join(lines)

        # Governance evidence.
        if agent_key in {"governance", "exclusion"}:
            summary = agent_output.get("summary", {}) if isinstance(agent_output, dict) else {}
            lines.extend([
                "### Governance",
                f"- Exclusion candidates: {summary.get('exclusion_candidates', 0)}",
                f"- Approved exclusions: {summary.get('approved_exclusions', 0)}",
                f"- Pending approvals: {summary.get('pending_approvals', 0)}",
                f"- Exclusion rate: {summary.get('exclusion_rate_percent', summary.get('exclusion_rate', 0))}",
                f"- Maximum allowed exclusion: {summary.get('maximum_allowed_exclusion_percent', summary.get('maximum_allowed_exclusion_rate', 0))}",
                f"- Cap exceeded: {summary.get('over_cap', summary.get('exclusion_cap_exceeded', False))}",
            ])
            if "br-gov" in question_lower or "business rule" in question_lower or "validate" in question_lower:
                lines.extend([
                    "",
                    "### Business-rule checks",
                    "- Each exclusion candidate requires an auditable risk statement.",
                    "- Medium residual-risk exclusions require QA Lead approval.",
                    "- High residual-risk exclusions require QA Lead and Business Owner approval.",
                    "- The aggregate exclusion set must remain within the approved risk-appetite cap.",
                ])
            return "\n".join(lines)

        lines.append("### Available answer")
        lines.append("The specialist A2A query completed and the answer above is grounded in the current Master Orchestrator state.")
        return "\n".join(lines)

    @staticmethod
    def _flatten_result_rows(agent_output: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(agent_output, dict):
            return []
        for key in ("results", "classification_results", "test_results"):
            value = agent_output.get(key)
            if isinstance(value, list) and all(isinstance(item, dict) for item in value):
                return value
        nested = agent_output.get("agent_output")
        if isinstance(nested, dict):
            return RiskTierMasterOrchestrator._flatten_result_rows(nested)
        return []

    def execute(
        self,
        release_id: str,
        on_stage: Callable[[str, str, str, str | None, dict[str, Any] | None], None] | None = None,
        trace_parent_run_id: str | None = None,
    ) -> PipelineState:
        """
        Thin tracing wrapper around _execute_inner (the real pipeline body,
        unchanged below). Kept separate so app.tracing has exactly one
        entry/exit point for the whole run — opened here before the real
        work starts, closed here whether it succeeds or raises — without
        having to wrap _execute_inner's ~700-line body in a try/finally.

        trace_parent_run_id is optional context for app.tracing only (e.g.
        the ADK invocation_id when this run was triggered from the AG-UI
        chat path via app/agents/pipeline_stream_agent.py) — it has no
        effect on pipeline behavior. When given, this run's own
        run_summary.json also folds in that ADK turn's real token usage
        (see tracing.peek_run_totals): the 6 specialist stages below are
        deterministic Python and never call an LLM, but the Master
        Orchestrator's own reasoning turn that decided to run this
        pipeline (stage_pipeline_run + transfer_to_agent) really did
        consume real tokens, and this is how that cost becomes visible
        from the pipeline's own run summary instead of only in a
        separately-keyed, harder-to-find trace tree.
        """
        normalized_release_id = str(release_id or "").strip().upper()
        run_trace = tracing.start_run(
            release_id=normalized_release_id or "UNKNOWN",
            kind="pipeline",
            trace_parent_run_id=trace_parent_run_id,
        )
        self._run_trace = run_trace

        orchestration = None
        if trace_parent_run_id:
            try:
                orchestration = tracing.peek_run_totals(trace_parent_run_id)
            except Exception:
                logger.exception(
                    "tracing: failed to peek orchestration totals for %s", trace_parent_run_id
                )
            if orchestration is not None:
                orchestration = {**orchestration, "run_id": trace_parent_run_id}

        try:
            state = self._execute_inner(release_id, on_stage=on_stage)
        except Exception as exc:
            try:
                tracing.finish_run(run_trace, status="FAILED", error=exc, orchestration=orchestration)
            except Exception:
                logger.exception("tracing: failed to finish run %s", run_trace.run_id)
            raise
        else:
            try:
                run_trace.set_final_response(state.summary())
            except Exception:
                logger.exception("tracing: failed to set final_response for run %s", run_trace.run_id)
            try:
                tracing.finish_run(run_trace, status="SUCCESS", orchestration=orchestration)
            except Exception:
                logger.exception("tracing: failed to finish run %s", run_trace.run_id)
            return state

    def _execute_inner(
        self,
        release_id: str,
        on_stage: Callable[[str, str, str, str | None, dict[str, Any] | None], None] | None = None,
    ) -> PipelineState:

        """
        Execute the complete Risk Tier pipeline for one release.

        ``on_stage(stage_key, status, text, agent_name)`` is an optional
        real-time progress callback used by the AG-UI streaming agent
        (app/agents/pipeline_stream_agent.py). ``stage_key`` is one of
        "orchestrator", "agent1".."agent6", "ledger" (a stable routing id);
        ``status`` is one of "running", "finished", "failed"; ``agent_name``
        is the human-readable name to display (e.g. "Feature / Epic Change
        Impact Agent") and may be sent multiple times per stage_key with
        different ``text`` — the Jira-loading phase in particular emits
        several "running" sub-progress updates under stage_key="orchestrator"
        before it finishes, since that single step is where essentially all
        of a run's wall-clock time is actually spent (every later stage reads
        from data already loaded into memory here — no further Jira/network
        calls happen after this point). Every existing caller that omits
        on_stage (CLI, plain REST /analyze) is unaffected.
        """

        print('Execute_function started..........................')

        self._on_stage = on_stage
        _ORCHESTRATOR_NAME = "Master Orchestrator"

        normalized_release_id = str(
            release_id or ""
        ).strip().upper()

        if not normalized_release_id:
            raise ValueError(
                "release_id cannot be empty."
            )

        self._emit_stage("orchestrator", "running", "Freezing release scope, loading Jira data…", agent_name=_ORCHESTRATOR_NAME)

        # Traces the orchestrator's own Jira-loading/cache-resolution phase
        # as a first-class agent (same start_agent_trace/finish_agent_trace
        # pattern already used for "Report Generator"), so
        # logs/<release>/<date>/<run_id>/Master_Orchestrator/ exists as its
        # own folder rather than only showing up as _emit_stage narration.
        run_trace = getattr(self, "_run_trace", None)
        master_trace = None
        if run_trace is not None:
            try:
                master_trace = tracing.start_agent_trace(
                    run_trace, agent_name=_ORCHESTRATOR_NAME,
                    input_data={"release_id": normalized_release_id},
                )
            except Exception:
                logger.exception("tracing: failed to start Master Orchestrator agent trace")

        def _finish_master_trace(status: str, error: Exception | str | None = None) -> None:
            if master_trace is None:
                return
            try:
                tracing.finish_agent_trace(
                    master_trace,
                    output_data={"blocks": sorted(self._jira_source_data.keys())} if status == "SUCCESS" else None,
                    status=status,
                    error=error,
                )
            except Exception:
                logger.exception("tracing: failed to finish Master Orchestrator agent trace")

        try:
            self._prepare_jira_source_data(
                normalized_release_id
            )
        except ReleaseDataUnavailableError as exc:
            self._emit_stage("orchestrator", "failed", str(exc), agent_name=_ORCHESTRATOR_NAME)
            _finish_master_trace("FAILED", exc)
            raise
        except Exception as exc:
            self._emit_stage("orchestrator", "failed", f"Failed to load Jira data: {exc}", agent_name=_ORCHESTRATOR_NAME)
            _finish_master_trace("FAILED", exc)
            raise

        self._emit_stage("orchestrator", "finished", "Release scope frozen.", agent_name=_ORCHESTRATOR_NAME)
        _finish_master_trace("SUCCESS")

        # Start every execution with an empty message bus and a fresh
        # per-agent input/output trace (see _log_a2a_payload / _write_agent_io_trace).
        self.message_bus = InMemoryMessageBus()
        self._agent_io_trace = []

        state = PipelineState(
            release_id=normalized_release_id
        )
        print('state : ', state)

        # =====================================================
        # Agents 1-4: Feature / Criticality / Historical / Policy
        # =====================================================
        # These four stages are mutually independent: each needs only the
        # already-loaded Jira source data (self._jira_source_data), never
        # another stage's output. Release/Release_Type — Policy's one input
        # that used to be read back out of Feature's own echoed response —
        # is resolved directly from that source data here instead, so Policy
        # no longer has a data dependency on Feature. They still run one
        # after another in plain Python, in order 1-4; Scoring (Agent 5)
        # waits for all four to finish before it runs, which is unchanged.
        release_rows = self._jira_source_data.get("releases", [])
        state.release = release_rows[0] if release_rows else {}

        release_type_value = (
            state.release.get(
                "Release_Type"
            )
            or state.release.get(
                "Release Type"
            )
            or state.release.get(
                "release_type"
            )
        )

        if not release_type_value:
            release_issue_key = state.release.get("issue_key") or "none (no matching Release issue)"
            release_source = state.release.get("release_source") or "direct Jira Release/label match"
            release_known_keys = sorted(state.release.keys())
            fallback_release_type = get_settings().default_release_type or "UNSPECIFIED"

            # No Release_Type is readable — most often because this release
            # only exists as a label/Fix Version on other issues, not a
            # dedicated 'Release'-typed Jira issue. Rather than block the
            # whole run, fall back to a configured sentinel (never a
            # guessed real type like 'MAJOR') and record that fact loudly —
            # in the log, the audit trail, and on state.release itself — so
            # nobody mistakes this for a real Jira value later. Type-
            # specific policy rows simply won't apply to this run; policies
            # scoped 'ALL'/'ANY'/empty still do (see _row_applies_to_release_type).
            logger.warning(
                "Release %r was found in Jira, but Release_Type could not be "
                "read (issue_key=%r, resolved via=%r, fields present=%s). "
                "Falling back to RISK_TIER_DEFAULT_RELEASE_TYPE=%r — any "
                "policy scoped to a specific release type will NOT apply to "
                "this run. Create a real Jira issue of the 'Release' issue "
                "type with Release_Type populated to get a real value instead.",
                normalized_release_id, release_issue_key, release_source,
                release_known_keys, fallback_release_type,
            )
            state.audit_log.append(
                AgentRun(
                    agent=_ORCHESTRATOR_NAME,
                    status="WARNING",
                    summary={
                        "release_id": normalized_release_id,
                        "issue": "release_type_unavailable",
                        "resolved_via": release_source,
                        "fallback_release_type": fallback_release_type,
                        "message": (
                            "Release_Type unavailable; falling back to "
                            f"{fallback_release_type!r}. Type-specific "
                            "policies will not apply to this run."
                        ),
                    },
                    started_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                )
            )
            release_type_value = fallback_release_type
            state.release["Release_Type"] = fallback_release_type
            state.release["release_type_is_fallback"] = True

        release_type = str(
            release_type_value
        ).strip().upper()

        feature_source_data = self._load_source_data(FEATURE_INPUT_BLOCKS)
        # The Feature Agent requires a "release_test_cases" block (the
        # release-scoped test subset, distinct from the full "test_cases"
        # population) that isn't fetched from Jira separately — derive it
        # here from data already loaded (release_scope + rtm + test_cases).
        feature_source_data["release_test_cases"] = derive_release_test_cases(
            feature_source_data, normalized_release_id
        )
        print('feature_source_data: ', feature_source_data)
        criticality_source_data = self._load_source_data(CRITICALITY_INPUT_BLOCKS)
        print('criticality_source_data: ', criticality_source_data)
        historical_source_data = self._load_source_data(HISTORICAL_INPUT_BLOCKS)
        print('historical_source_data: ', historical_source_data)
        policy_source_data = self._load_source_data(POLICY_INPUT_BLOCKS)
        print('policy_source_data: ', policy_source_data)

        # A2A: Master -> Feature / Criticality / Historical / Policy Agents.
        feature_request = make_request(
            sender="Risk Tier Master Orchestrator",
            receiver="Feature / Epic Change Impact Agent",
            message_type="FEATURE_CHANGE_REQUEST",
            release_id=normalized_release_id,
            data={"source_data": feature_source_data},
        )
        print('feature_request: ', feature_request)
        criticality_request = make_request(
            sender="Risk Tier Master Orchestrator",
            receiver="Application Criticality Classification Agent",
            message_type="CRITICALITY_REQUEST",
            release_id=normalized_release_id,
            data={"source_data": criticality_source_data},
        )
        print('criticality_request: ', criticality_request)
        history_request = make_request(
            sender="Risk Tier Master Orchestrator",
            receiver="Historical Execution Intelligence Agent",
            message_type="HISTORICAL_REQUEST",
            release_id=normalized_release_id,
            data={"source_data": historical_source_data},
        )
        print('history_request: ', history_request)
        policy_request = make_request(
            sender="Risk Tier Master Orchestrator",
            receiver="Policy / Risk Appetite Calibration Agent",
            message_type="POLICY_REQUEST",
            release_id=normalized_release_id,
            data={"source_data": policy_source_data, "release_type": release_type},
        )

        self._log_a2a_payload(
            "INPUT",
            "Feature / Epic Change Impact Agent",
            feature_request,
        )
        feature_response = self._run_stage(
            state=state,
            agent_name="Feature / Epic Change Impact Agent",
            function=lambda: __import__(
                "app.agents.feature_change_agent.tools", fromlist=["handle_a2a_request"]
            ).handle_a2a_request(feature_request),
            stage_key="agent1",
            tool_ref=analyze_release_scope,
            tool_args={"release_id": normalized_release_id, "source_data": feature_source_data},
        )
        self._log_a2a_payload(
            "OUTPUT",
            "Feature / Epic Change Impact Agent",
            feature_response,
        )
        self._log_a2a_payload(
            "INPUT",
            "Application Criticality Classification Agent",
            criticality_request,
        )
        criticality_response = self._run_stage(
            state=state,
            agent_name="Application Criticality Classification Agent",
            function=lambda: __import__(
                "app.agents.criticality_agent.tools", fromlist=["handle_a2a_request"]
            ).handle_a2a_request(criticality_request),
            stage_key="agent2",
            tool_ref=classify_application_criticality,
            tool_args={"source_data": criticality_source_data},
        )
        self._log_a2a_payload(
            "OUTPUT",
            "Application Criticality Classification Agent",
            criticality_response,
        )
        self._log_a2a_payload(
            "INPUT",
            "Historical Execution Intelligence Agent",
            history_request,
        )
        history_response = self._run_stage(
            state=state,
            agent_name="Historical Execution Intelligence Agent",
            function=lambda: __import__(
                "app.agents.historical_agent.tools", fromlist=["handle_a2a_request"]
            ).handle_a2a_request(history_request),
            stage_key="agent3",
            tool_ref=analyze_historical_execution,
            tool_args={"source_data": historical_source_data, "release_id": normalized_release_id},
        )
        print('history_response : ',history_response )
        self._log_a2a_payload(
            "OUTPUT",
            "Historical Execution Intelligence Agent",
            history_response,
        )
        self._log_a2a_payload(
            "INPUT",
            "Policy / Risk Appetite Calibration Agent",
            policy_request,
        )
        policy_response = self._run_stage(
            state=state,
            agent_name="Policy / Risk Appetite Calibration Agent",
            function=lambda: __import__(
                "app.agents.policy_agent.tools", fromlist=["handle_a2a_request"]
            ).handle_a2a_request(policy_request),
            stage_key="agent4",
            tool_ref=calibrate_risk_policy,
            tool_args={"source_data": policy_source_data, "release_type": release_type},
        )
        print('policy_response: ',policy_response)
        self._log_a2a_payload(
            "OUTPUT",
            "Policy / Risk Appetite Calibration Agent",
            policy_response,
        )


        state.change_impact = feature_response.data
        state.criticality = criticality_response.data
        state.history = history_response.data
        state.policy = policy_response.data

        policy_payload = state.policy.get(
            "agent_output",
            state.policy,
        )

        self._send_message(
            sender=(
                "Feature / Epic Change Impact Agent"
            ),
            receiver=(
                "Decision Engine / Risk Scoring Agent"
            ),
            message_type="CHANGE_IMPACT_READY",
            payload={
                "release_id": (
                    normalized_release_id
                ),
                "direct_test_ids": (
                    state.change_impact.get(
                        "direct_test_ids",
                        [],
                    )
                ),
                "downstream_test_ids": (
                    state.change_impact.get(
                        "downstream_test_ids",
                        [],
                    )
                ),
                "new_feature_test_ids": (
                    state.change_impact.get(
                        "new_feature_test_ids",
                        [],
                    )
                ),
                "changed_requirement_ids": (
                    state.change_impact.get(
                        "changed_requirement_ids",
                        [],
                    )
                ),
                "traceability_gaps": (
                    state.change_impact.get(
                        "traceability_gaps",
                        [],
                    )
                ),
            },
        )
        self._send_message(
            sender=(
                "Application Criticality "
                "Classification Agent"
            ),
            receiver=(
                "Decision Engine / Risk Scoring Agent"
            ),
            message_type="CRITICALITY_READY",
            payload={
                "release_id": (
                    normalized_release_id
                ),
                "test_tags": (
                    state.criticality.get(
                        "test_tags",
                        {},
                    )
                ),
                "module_assignments": (
                    state.criticality.get(
                        "module_assignments",
                        {},
                    )
                ),
            },
        )
        self._send_message(
            sender=(
                "Historical Execution "
                "Intelligence Agent"
            ),
            receiver=(
                "Decision Engine / Risk Scoring Agent"
            ),
            message_type="HISTORY_READY",
            payload={
                "release_id": (
                    normalized_release_id
                ),
                "test_summaries": (
                    state.history.get(
                        "test_summaries",
                        {},
                    )
                ),
                "historical_summary": (
                    state.history.get(
                        "summary",
                        {},
                    )
                ),
            },
        )
        self._send_message(
            sender=(
                "Policy / Risk Appetite "
                "Calibration Agent"
            ),
            receiver=(
                "Decision Engine / Risk Scoring Agent"
            ),
            message_type="POLICY_READY",
            payload={
                "release_id": (
                    normalized_release_id
                ),
                "release_type": (
                    policy_payload.get(
                        "release_type",
                        release_type,
                    )
                ),
                "overall_max_exclusion": (
                    policy_payload.get(
                        "overall_max_exclusion",
                        state.policy.get(
                            "overall_max_exclusion",
                            0,
                        ),
                    )
                ),
                "regulatory_test_ids": (
                    policy_payload.get(
                        "regulatory_test_ids",
                        sorted(
                            state.policy.get(
                                "regulatory_tests",
                                {},
                            ).keys()
                        ),
                    )
                ),
                "mandatory_test_ids": (
                    policy_payload.get(
                        "mandatory_test_ids",
                        state.policy.get(
                            "mandatory_test_ids",
                            [],
                        ),
                    )
                ),
            },
        )

        # =====================================================
        # Agent 5: Decision Engine / Risk Scoring
        # =====================================================
        # The Scoring Agent historically expected scoring_weights and
        # thresholds to be present in source_data. The current Scoring Agent
        # can use internal defaults, but the Master Orchestrator explicitly
        # supplies a complete configuration here so both contracts work and
        # the pipeline cannot fail merely because the configuration blocks
        # were omitted from Jira-backed source data.
        scoring_source_data = (
            self._load_source_data(
                SCORING_INPUT_BLOCKS
            )
        )

        configured_weights = (
            policy_payload.get("scoring_weights")
            or policy_payload.get("weights")
            or policy_payload.get("risk_score_weights")
            or []
        )
        configured_thresholds = (
            policy_payload.get("thresholds")
            or policy_payload.get("risk_thresholds")
            or []
        )

        if isinstance(configured_weights, dict):
            configured_weights = [
                {"Factor": factor, "Weight": value}
                for factor, value in configured_weights.items()
            ]
        elif not isinstance(configured_weights, list):
            configured_weights = []

        if isinstance(configured_thresholds, dict):
            configured_thresholds = [
                {"Classification": classification, "Minimum_Score": value}
                for classification, value in configured_thresholds.items()
            ]
        elif not isinstance(configured_thresholds, list):
            configured_thresholds = []

        # Use documented defaults when the Policy Agent does not provide an
        # explicit scoring configuration. Convert the dictionaries to row
        # format because the Scoring Agent supports list-of-row inputs.
        if not configured_weights:
            configured_weights = [
                {"Factor": factor, "Weight": value}
                for factor, value in DEFAULT_WEIGHTS.items()
            ]
        if not configured_thresholds:
            configured_thresholds = [
                {"Classification": classification, "Minimum_Score": value}
                for classification, value in DEFAULT_THRESHOLDS.items()
            ]

        scoring_source_data["scoring_weights"] = configured_weights
        scoring_source_data["thresholds"] = configured_thresholds

        # A2A: Master -> Scoring Agent with all required upstream outputs.
        scoring_request = make_request(
            sender="Risk Tier Master Orchestrator",
            receiver="Decision Engine / Risk Scoring Agent",
            message_type="SCORING_REQUEST",
            release_id=normalized_release_id,
            data={
                "source_data": scoring_source_data,
                "change_impact": state.change_impact,
                "criticality": state.criticality,
                "history": state.history,
                "policy": state.policy,
            },
        )
        self._log_a2a_payload(
            "INPUT",
            "Decision Engine / Risk Scoring Agent",
            scoring_request,
        )
        scoring_response = self._run_stage(
            state=state,
            agent_name="Decision Engine / Risk Scoring Agent",
            function=lambda: __import__(
                "app.agents.scoring_agent.tools", fromlist=["handle_a2a_request"]
            ).handle_a2a_request(scoring_request),
            stage_key="agent5",
            tool_ref=calculate_test_selection,
            tool_args=scoring_request.data,
        )
        print('scoring_response: ', scoring_response)
        self._log_a2a_payload(
            "OUTPUT",
            "Decision Engine / Risk Scoring Agent",
            scoring_response,
        )
        state.scoring = scoring_response.data

        scoring_payload = state.scoring.get(
            "agent_output",
            state.scoring,
        )

        scoring_results = scoring_payload.get(
            "results",
            state.scoring.get(
                "results",
                [],
            ),
        )

        if not isinstance(
            scoring_results,
            list,
        ):
            raise TypeError(
                "Scoring Agent results must be a list."
            )

        # Persist an exact population reconciliation in PipelineState so the
        # final report and post-run conversational queries can explain any
        # Change Impact -> Scoring population difference without rerunning Jira.
        change_payload_for_reconciliation = self._unwrap_agent_output(state.change_impact)
        direct_ids_for_reconciliation = {
            self._normalize_test_id(value)
            for value in change_payload_for_reconciliation.get("direct_test_ids", [])
            if self._normalize_test_id(value)
        }
        scored_ids_for_reconciliation = {
            self._normalize_test_id(row.get("test_case_id"))
            for row in scoring_results
            if isinstance(row, dict) and self._normalize_test_id(row.get("test_case_id"))
        }
        state.scoring["population_reconciliation"] = {
            "direct_test_count": len(direct_ids_for_reconciliation),
            "scored_test_count": len(scored_ids_for_reconciliation),
            "missing_from_scoring": sorted(direct_ids_for_reconciliation - scored_ids_for_reconciliation),
            "outside_direct_impact": sorted(scored_ids_for_reconciliation - direct_ids_for_reconciliation),
        }

        # Governance reviews only final EXCLUDE classifications.
        candidate_test_ids = [
            row.get(
                "test_case_id"
            )
            for row in scoring_results
            if (
                row.get(
                    "classification"
                )
                == "EXCLUDE"
                and row.get(
                    "test_case_id"
                )
            )
        ]

        self._send_message(
            sender=(
                "Decision Engine / Risk Scoring Agent"
            ),
            receiver=(
                "Exclusion Risk & Governance Agent"
            ),
            message_type="SCORING_COMPLETE",
            payload={
                "release_id": (
                    normalized_release_id
                ),
                "summary": (
                    scoring_payload.get(
                        "summary",
                        state.scoring.get(
                            "summary",
                            {},
                        ),
                    )
                ),
                "candidate_test_ids": (
                    candidate_test_ids
                ),
            },
        )

        # =====================================================
        # Agent 6: Exclusion Risk & Governance
        # =====================================================
        # A2A: Master -> Governance Agent.
        governance_request = make_request(
            sender="Risk Tier Master Orchestrator",
            receiver="Exclusion Risk & Governance Agent",
            message_type="GOVERNANCE_REQUEST",
            release_id=normalized_release_id,
            data={"scoring": state.scoring, "policy": state.policy},
        )
        policy_data = state.policy
        self._log_a2a_payload(
            "INPUT",
            "Exclusion Risk & Governance Agent",
            governance_request,
        )
        governance_response = self._run_stage(
            state=state,
            agent_name="Exclusion Risk & Governance Agent",
            function=lambda: __import__(
                "app.agents.governance_agent.tools", fromlist=["handle_a2a_request"]
            ).handle_a2a_request(governance_request),
            stage_key="agent6",
            tool_ref=evaluate_exclusion_governance,
            tool_args=governance_request.data,
        )
        print('governance_response: ', governance_response)
        self._log_a2a_payload(
            "OUTPUT",
            "Exclusion Risk & Governance Agent",
            governance_response,
        )
        state.governance = governance_response.data

        self._send_message(
            sender=(
                "Exclusion Risk & Governance Agent"
            ),
            receiver=(
                "Risk Tier Master Orchestrator"
            ),
            message_type="GOVERNANCE_COMPLETE",
            payload={
                "release_id": (
                    normalized_release_id
                ),
                "summary": (
                    state.governance.get(
                        "summary",
                        {},
                    )
                ),
            },
        )

        # Store all A2A-style messages in pipeline state.
        state.messages = list(
            self.message_bus.messages
        )

        # =====================================================
        # Report generation
        # =====================================================
        report_started_at = datetime.now(
            timezone.utc
        )

        _LEDGER_NAME = "Immutable Audit Ledger"
        self._emit_stage("ledger", "running", "Writing decisions to the audit ledger…", agent_name=_LEDGER_NAME)

        run_trace = getattr(self, "_run_trace", None)
        report_agent_trace = None
        if run_trace is not None:
            try:
                report_agent_trace = tracing.start_agent_trace(
                    run_trace, agent_name="Report Generator", input_data={}
                )
            except Exception:
                logger.exception("tracing: failed to start agent trace for Report Generator")

        try:
            state.report_files = (
                self.report_generator.generate(
                    state
                )
            )

            state.audit_log.append(
                AgentRun(
                    agent="Report Generator",
                    status="COMPLETED",
                    summary=(
                        state.report_files
                    ),
                    started_at=(
                        report_started_at
                    ),
                    completed_at=datetime.now(
                        timezone.utc
                    ),
                )
            )

            if report_agent_trace is not None:
                try:
                    tracing.finish_agent_trace(report_agent_trace, output_data=state.report_files, status="SUCCESS")
                except Exception:
                    logger.exception("tracing: failed to finish agent trace for Report Generator")

        except Exception as exc:
            state.audit_log.append(
                AgentRun(
                    agent="Report Generator",
                    status="FAILED",
                    summary={
                        "error_type": (
                            type(exc).__name__
                        ),
                        "error": str(exc),
                    },
                    started_at=(
                        report_started_at
                    ),
                    completed_at=datetime.now(
                        timezone.utc
                    ),
                )
            )

            if report_agent_trace is not None:
                try:
                    tracing.finish_agent_trace(report_agent_trace, status="FAILED", error=exc)
                except Exception:
                    logger.exception("tracing: failed to finish (failed) agent trace for Report Generator")

            self._emit_stage("ledger", "failed", f"Audit ledger write failed: {exc}", agent_name=_LEDGER_NAME)

            raise

        # Cache only fully completed pipelines for post-run ADK queries.
        # A2A: subsequent specialist questions consume this exact snapshot.
        self._cache_completed_pipeline(
            state=state,
            source_data=self._jira_source_data,
        )

        # Persist the exact input/output exchanged with every agent this run,
        # so the pipeline's data flow can be inspected without re-running it
        # or digging through log output.
        trace_path = self._write_agent_io_trace(normalized_release_id)
        if trace_path is not None:
            state.report_files = {**(state.report_files or {}), "agent_io_trace": str(trace_path)}

        self._emit_stage("ledger", "finished", "Audit ledger updated.", agent_name=_LEDGER_NAME)

        return state

    

def execute_risk_tier_pipeline(
    jira_link: str,
    release_id: str | None = None,
) -> dict[str, Any]:
    """
    ADK-facing entry point for the complete Risk Tier pipeline.

    The detailed pipeline state remains inside Python/report files. Only a
    compact summary is returned to the ADK model so the tool response does not
    exceed the model message-size limit.
    """
    settings = get_settings()

    normalized_jira_link = str(jira_link or "").strip()
    if not normalized_jira_link:
        return {
            "status": "needs_input",
            "message": "Please provide the Jira link.",
        }

    link_ctx = parse_jira_link(normalized_jira_link)
    normalized_release_id = str(
        release_id
        or (link_ctx.release_label if link_ctx else "")
        or settings.default_release
        or ""
    ).strip().upper()

    if not normalized_release_id:
        return {
            "status": "needs_input",
            "message": "Please provide the release ID.",
        }

    try:
        state = (
            RiskTierMasterOrchestrator
            .from_settings(
                settings=settings,
                jira_link=normalized_jira_link,
            )
            .execute(normalized_release_id)
        )

        scoring = state.scoring or {}
        policy = state.policy or {}
        history = state.history or {}
        criticality = state.criticality or {}
        change_impact = state.change_impact or {}
        governance = state.governance or {}

        return {
            "status": "success",
            "release_id": state.release_id,
            "summary": state.summary(),
            "change_impact_summary": change_impact.get(
                "summary", {}
            ),
            "criticality_summary": criticality.get(
                "summary", {}
            ),
            "historical_summary": history.get(
                "summary", {}
            ),
            "policy_summary": policy.get(
                "summary", {}
            ),
            "classification_summary": scoring.get(
                "summary", {}
            ),
            "governance_summary": governance.get(
                "summary", {}
            ),
            "report_files": state.report_files or {},
        }

    except ReleaseDataUnavailableError as exc:
        return {
            "status": "not_found",
            "release_id": normalized_release_id,
            "message": str(exc),
        }
    except Exception as exc:
        return {
            "status": "error",
            "release_id": normalized_release_id,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }


def stage_pipeline_run(
    release_id: str | None,
    jira_link: str = "",
    *,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """
    ADK-facing entry point that stages a full pipeline run without executing it.

    Validates and defaults release_id/jira_link exactly like
    execute_risk_tier_pipeline, but instead of running the pipeline
    synchronously it writes them into the ADK session state and returns
    immediately. The Master Orchestrator should transfer to the
    "risk_tier_pipeline" agent right after this call succeeds — that agent
    reads release_id/jira_link from session state (see
    app/agents/pipeline_stream_agent.py) and streams live per-agent progress,
    which a blocking tool call cannot do.
    """
    settings = get_settings()

    normalized_jira_link = str(jira_link or "").strip()

    link_ctx = parse_jira_link(normalized_jira_link) if normalized_jira_link else None
    normalized_release_id = str(
        release_id
        or (link_ctx.release_label if link_ctx else "")
        or settings.default_release
        or ""
    ).strip().upper()

    if not normalized_release_id:
        return {
            "status": "needs_input",
            "message": "Please provide the release ID.",
        }

    tool_context.state["release_id"] = normalized_release_id
    tool_context.state["jira_link"] = normalized_jira_link or None

    return {
        "status": "staged",
        "release_id": normalized_release_id,
        "message": (
            f"Release context staged for {normalized_release_id}. "
            "Transfer to the risk_tier_pipeline agent now to run it with live progress."
        ),
    }