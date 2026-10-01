
# from __future__ import annotations

# from app.observability.logger import (
#     log_event,
#     trace_error,
# )
# from app.observability.audit import audit_event

# from datetime import date, datetime
# from typing import Any, Iterable

# from app.models import A2ARequest, A2AResponse
# from app.services.a2a import make_response, validate_message


# REQUIRED_INPUTS = (
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

# def _rows(
#     source_data: dict[str, list[dict[str, Any]]],
#     input_name: str,
# ) -> list[dict[str, Any]]:
#     """Return data rows supplied by the Master Orchestrator."""
#     if input_name not in source_data:
#         raise KeyError(
#             f"Master Orchestrator did not provide required input "
#             f"{input_name!r}."
#         )

#     rows = source_data[input_name]

#     if not isinstance(rows, list):
#         raise TypeError(
#             f"Input {input_name!r} must be provided as a list of rows."
#         )

#     return rows


# def _test_case_id(row: dict[str, Any]) -> str:
#     return str(
#         _value(
#             row,
#             "Test_Case_ID",
#             "TestCase_ID",
#             "Test Case ID",
#             "Test_ID",
#             "TC_ID",
#         )
#         or ""
#     ).strip()


# def _module_id(row: dict[str, Any]) -> str:
#     return str(
#         _value(
#             row,
#             "Module_ID",
#             "ModuleId",
#             "Module ID",
#             "Module",
#         )
#         or ""
#     ).strip()


# def _story_id(row: dict[str, Any]) -> str:
#     return str(
#         _value(
#             row,
#             "User_Story_ID",
#             "UserStory_ID",
#             "Story_ID",
#             "User Story ID",
#             "User_Story",
#         )
#         or ""
#     ).strip()


# def _requirement_id(row: dict[str, Any]) -> str:
#     return str(
#         _value(
#             row,
#             "Requirement_ID",
#             "RequirementId",
#             "Requirement ID",
#             "Req_ID",
#             "Req ID",
#         )
#         or ""
#     ).strip()


# def _epic_id(row: dict[str, Any]) -> str:
#     return str(
#         _value(
#             row,
#             "Epic_ID",
#             "EpicId",
#             "Epic ID",
#             "Epic",
#         )
#         or row.get("work_item_id")
#         or row.get("issue_key")
#         or ""
#     ).strip()


# def _is_active_test_case(row: dict[str, Any]) -> bool:
#     return _normalized(
#         _value(
#             row,
#             "Test_Status",
#             "Test Status",
#             "Status",
#         )
#         or "ACTIVE"
#     ) not in {
#         "INACTIVE",
#         "DISABLED",
#         "RETIRED",
#         "DEPRECATED",
#     }


# def _feature_test_epic_ids(
#     test_case: dict[str, Any],
#     story_by_id: dict[str, dict[str, Any]],
# ) -> set[str]:
#     """Resolve Epic IDs associated with a test through explicit fields or its parent story."""
#     epic_ids: set[str] = set()

#     explicit_epic = _epic_id(test_case)
#     if explicit_epic:
#         epic_ids.add(explicit_epic)

#     story_id = _story_id(test_case)
#     story = story_by_id.get(story_id)
#     if story:
#         story_epic = _epic_id(story)
#         if story_epic:
#             epic_ids.add(story_epic)

#     return epic_ids


# def analyze_release_scope(
#     release_id: str,
#     source_data: dict[str, list[dict[str, Any]]],
# ) -> dict[str, Any]:
#     """
#     Analyze one release using in-memory data supplied only by the Master Orchestrator.

#     Input data blocks:
#     - releases
#     - epics
#     - stories
#     - requirements
#     - rtm
#     - test_cases
#     - release_scope
#     - dependencies
#     - out_of_scope

#     Generated outputs:
#     - Changed epics
#     - Changed user stories
#     - Changed requirements
#     - Directly impacted tests
#     - Downstream impacted tests
#     - New-feature protection tests
#     - Traceability gaps
#     - Markdown dashboard

#     This function does not read:
#     - generated change-impact output
#     - generated traceability-gap output
#     """

#     normalized_release_id = str(release_id).strip()

#     if not normalized_release_id:
#         raise ValueError("release_id cannot be empty")

#     log_event(
#         "FEATURE_ANALYSIS_STARTED",
#         agent="Feature / Epic Change Impact Agent",
#         stage="FEATURE",
#         status="STARTED",
#         release_id=normalized_release_id,
#     )

#     # ---------------------------------------------------------
#     # Load source data blocks once
#     # ---------------------------------------------------------
#     releases = _rows(source_data, "releases")
#     release_scope_rows = _rows(source_data, "release_scope")
#     epic_rows = _rows(source_data, "epics")
#     story_rows = _rows(source_data, "stories")
#     requirement_rows = _rows(source_data, "requirements")
#     rtm_rows = _rows(source_data, "rtm")
#     test_case_rows = _rows(source_data, "test_cases")
#     dependency_rows = _rows(source_data, "dependencies")
#     out_of_scope_rows = _rows(source_data, "out_of_scope")

#     log_event(
#         "FEATURE_INPUTS_LOADED",
#         agent="Feature / Epic Change Impact Agent",
#         stage="FEATURE",
#         status="SUCCESS",
#         releases=len(releases),
#         epics=len(epic_rows),
#         stories=len(story_rows),
#         requirements=len(requirement_rows),
#         test_cases=len(test_case_rows),
#     )

#     # ---------------------------------------------------------
#     # 1. Find the release
#     # ---------------------------------------------------------
#     def _release_matches(row: dict[str, Any]) -> bool:
#         candidates = [
#             _value(row, "Release_ID", "ReleaseId", "Release ID", "Release"),
#             row.get("work_item_id"),
#             row.get("issue_key"),
#             row.get("summary"),
#         ]
#         target = _normalized(normalized_release_id)
#         for candidate in candidates:
#             if candidate is None:
#                 continue
#             candidate_norm = _normalized(candidate)
#             if candidate_norm == target or target in candidate_norm:
#                 return True
#         return False

#     release = next((row for row in releases if _release_matches(row)), None)

#     if release is None:
#         available_releases = sorted(
#             {
#                 str(
#                     _value(
#                         row,
#                         "Release_ID",
#                         "ReleaseId",
#                         "Release ID",
#                         "Release",
#                     )
#                     or row.get("work_item_id")
#                     or row.get("issue_key")
#                     or row.get("summary")
#                     or ""
#                 ).strip()
#                 for row in releases
#                 if (
#                     _value(row, "Release_ID", "ReleaseId", "Release ID", "Release")
#                     or row.get("work_item_id")
#                     or row.get("issue_key")
#                     or row.get("summary")
#                 )
#             }
#         )

#         raise ValueError(
#             f"Release {normalized_release_id!r} was not found in releases data. "
#             f"Available releases: {available_releases}. "
#             "Expected the orchestrator to provide Release_ID, issue_key, or a "
#             "summary containing the release identifier."
#         )

#     release_type = _display(
#         _value(
#             release,
#             "Release_Type",
#             "Release Type",
#         )
#         or ""
#     )

#     # ---------------------------------------------------------
#     # 2. Determine in-scope epics
#     # ---------------------------------------------------------
#     scope = [
#         row
#         for row in release_scope_rows
#         if _same(
#             _value(
#                 row,
#                 "Release_ID",
#                 "ReleaseId",
#                 "Release ID",
#                 "Release",
#             ),
#             normalized_release_id,
#         )
#         and _normalized(
#             _value(
#                 row,
#                 "Scope_Status",
#                 "Scope Status",
#                 "Status",
#             )
#         )
#         == "IN_SCOPE"
#     ]

#     epic_ids = {
#         str(epic_id).strip()
#         for row in scope
#         if (
#             epic_id := _value(
#                 row,
#                 "Epic_ID",
#                 "EpicId",
#                 "Epic ID",
#                 "Epic",
#             )
#         )
#     }

#     # Prefer granular scope when release_scope provides it.
#     scoped_story_ids = {
#         str(story_id).strip()
#         for row in scope
#         if (
#             story_id := _value(
#                 row,
#                 "User_Story_ID",
#                 "UserStory_ID",
#                 "Story_ID",
#                 "User Story ID",
#                 "Story",
#             )
#         )
#     }

#     scoped_requirement_ids = {
#         str(requirement_id).strip()
#         for row in scope
#         if (
#             requirement_id := _value(
#                 row,
#                 "Requirement_ID",
#                 "RequirementId",
#                 "Requirement ID",
#                 "Req_ID",
#                 "Req ID",
#             )
#         )
#     }

#     def _row_epic_id(row: dict[str, Any]) -> str:
#         """Resolve an Epic ID from explicit logical fields or Jira identity."""
#         return str(
#             _value(
#                 row,
#                 "Epic_ID",
#                 "EpicId",
#                 "Epic ID",
#                 "Epic",
#             )
#             or row.get("work_item_id")
#             or row.get("issue_key")
#             or ""
#         ).strip()

#     def _is_changed_entity(row: dict[str, Any]) -> bool:
#         """Return True only for entities that actually changed in the release."""
#         status = _normalized(
#             _value(
#                 row,
#                 "Change_Status",
#                 "Change Status",
#                 "Change_Type",
#                 "Change Type",
#                 "Status",
#             )
#         )

#         # Empty change status is treated as unknown rather than changed.
#         # This prevents an unchanged downstream-only requirement from being
#         # pulled into the direct-change population merely because it is in
#         # the broader release hierarchy.
#         return status in {
#             "NEW",
#             "ADDED",
#             "CHANGED",
#             "MODIFIED",
#             "UPDATED",
#             "NEW_FEATURE",
#         }

#     # The Jira project stores release scope on the Epic via labels / scope fields,
#     # while the logical release_scope rows may be incomplete after normalization.
#     # Derive Epic IDs from the authoritative Epic rows as a fallback.
#     normalized_release_token = _normalized(normalized_release_id)
#     if not epic_ids:
#         for row in epic_rows:
#             labels = row.get("labels") or []
#             if not isinstance(labels, (list, tuple, set)):
#                 labels = [labels]
#             normalized_labels = {_normalized(label) for label in labels}
#             scope_status = _normalized(_value(row, "Scope_Status", "Scope Status", "Status"))
#             change_status = _normalized(_value(row, "Change_Status", "Change Status", "Change_Type"))
#             summary_token = _normalized(row.get("summary"))
#             if (
#                 normalized_release_token in normalized_labels
#                 or normalized_release_token in summary_token
#                 or scope_status == "IN_SCOPE" and change_status in {"MODIFIED", "NEW", "ADDED", "CHANGED"}
#             ):
#                 epic_id = _row_epic_id(row)
#                 if epic_id:
#                     epic_ids.add(epic_id)

#     changed_epics = [
#         row
#         for row in epic_rows
#         if _row_epic_id(row) in epic_ids
#     ]

#     log_event(
#         "BR_CHG_01_APPLIED",
#         agent="Feature / Epic Change Impact Agent",
#         rule_id="BR-CHG-01",
#         changed_epics=len(changed_epics),
#     )

#     # If scope rows contain no Epic_ID but the Epic is explicitly labelled for
#     # this release, include every such Epic. This mirrors the Jira setup where
#     # REL-25.4 is attached to the Epic.
#     if not changed_epics:
#         for row in epic_rows:
#             labels = row.get("labels") or []
#             if not isinstance(labels, (list, tuple, set)):
#                 labels = [labels]
#             if normalized_release_token in {_normalized(v) for v in labels}:
#                 changed_epics.append(row)

#     # ---------------------------------------------------------
#     # 3. Determine changed user stories
#     # ---------------------------------------------------------
#     changed_stories: list[dict[str, Any]] = []

#     for row in story_rows:
#         story_id = str(
#             _value(
#                 row,
#                 "User_Story_ID",
#                 "UserStory_ID",
#                 "Story_ID",
#                 "User Story ID",
#                 "User_Story",
#             )
#             or ""
#         ).strip()

#         story_epic_id = str(
#             _value(
#                 row,
#                 "Epic_ID",
#                 "EpicId",
#                 "Epic ID",
#                 "Parent_Epic_ID",
#             )
#             or ""
#         ).strip()

#         if scoped_story_ids:
#             is_changed_story = (
#                 story_id in scoped_story_ids
#             )
#         elif scoped_requirement_ids:
#             # Requirement-level scope is more granular.
#             # Stories will be derived after matching requirements.
#             is_changed_story = False
#         else:
#             is_changed_story = (
#                 story_epic_id in epic_ids
#             )

#         if story_id and is_changed_story:
#             changed_stories.append(row)

#     changed_story_ids = {
#         str(story_id).strip()
#         for row in changed_stories
#         if (
#             story_id := _value(
#                 row,
#                 "User_Story_ID",
#                 "UserStory_ID",
#                 "Story_ID",
#                 "User Story ID",
#                 "User_Story",
#             )
#         )
#     }

#     # ---------------------------------------------------------
#     # 4. Determine changed requirements
#     # ---------------------------------------------------------
#     changed_requirements: list[dict[str, Any]] = []

#     for row in requirement_rows:
#         requirement_id = str(
#             _value(
#                 row,
#                 "Requirement_ID",
#                 "RequirementId",
#                 "Requirement ID",
#                 "Req_ID",
#                 "Req ID",
#             )
#             or ""
#         ).strip()

#         requirement_epic_id = str(
#             _value(
#                 row,
#                 "Epic_ID",
#                 "EpicId",
#                 "Epic ID",
#                 "Parent_Epic_ID",
#             )
#             or ""
#         ).strip()

#         requirement_story_id = str(
#             _value(
#                 row,
#                 "User_Story_ID",
#                 "UserStory_ID",
#                 "Story_ID",
#                 "User Story ID",
#             )
#             or ""
#         ).strip()

#         if scoped_requirement_ids:
#             # Requirement-level scope is authoritative, but an explicitly
#             # UNCHANGED requirement is not a changed requirement. This is
#             # important for downstream-only fixtures: the downstream Story /
#             # Requirement may exist in Jira without independently driving
#             # direct test selection.
#             is_changed_requirement = (
#                 requirement_id in scoped_requirement_ids
#                 and _is_changed_entity(row)
#             )
#         elif scoped_story_ids:
#             # Story-level scope selects requirements linked to those stories.
#             # Only requirements that actually changed are direct-change
#             # requirements; unchanged requirements remain usable for RTM but
#             # do not create direct impact by themselves.
#             is_changed_requirement = (
#                 requirement_story_id in scoped_story_ids
#                 and _is_changed_entity(row)
#             )
#         else:
#             # Epic-level scope: requirements in this input bundle are linked to
#             # epics through Story_ID, so use the selected changed story IDs.
#             is_changed_requirement = (
#                 requirement_story_id in changed_story_ids
#                 and _is_changed_entity(row)
#             )

#         if requirement_id and is_changed_requirement:
#             changed_requirements.append(row)

#     changed_requirement_ids = {
#         str(requirement_id).strip()
#         for row in changed_requirements
#         if (
#             requirement_id := _value(
#                 row,
#                 "Requirement_ID",
#                 "RequirementId",
#                 "Requirement ID",
#                 "Req_ID",
#                 "Req ID",
#             )
#         )
#     }

#     # If scope is requirement-level, derive the related stories
#     # for reporting without broadening the direct test scope.
#     if scoped_requirement_ids:
#         derived_story_ids = {
#             str(
#                 _value(
#                     row,
#                     "User_Story_ID",
#                     "UserStory_ID",
#                     "Story_ID",
#                     "User Story ID",
#                 )
#                 or ""
#             ).strip()
#             for row in changed_requirements
#             if _value(
#                 row,
#                 "User_Story_ID",
#                 "UserStory_ID",
#                 "Story_ID",
#                 "User Story ID",
#             )
#         }

#         changed_stories = [
#             row
#             for row in story_rows
#             if str(
#                 _value(
#                     row,
#                     "User_Story_ID",
#                     "UserStory_ID",
#                     "Story_ID",
#                     "User Story ID",
#                     "User_Story",
#                 )
#                 or ""
#             ).strip()
#             in derived_story_ids
#         ]

#         changed_story_ids = {
#             str(story_id).strip()
#             for row in changed_stories
#             if (
#                 story_id := _value(
#                     row,
#                     "User_Story_ID",
#                     "UserStory_ID",
#                     "Story_ID",
#                     "User Story ID",
#                     "User_Story",
#                 )
#             )
#         }

#     # ---------------------------------------------------------
#     # 5. Generate direct impacts from RTM
#     # ---------------------------------------------------------
#     # Primary source is RTM. In this Jira project, however, the Test Case
#     # itself also carries Requirement_ID, so derive a second set directly
#     # from active test cases and use the union. This keeps the logical RTM
#     # model intact without requiring a dedicated RTM Jira issue type.
#     direct_impacts = [
#         row
#         for row in rtm_rows
#         if _normalized(
#             _value(
#                 row,
#                 "Mapping_Status",
#                 "Mapping Status",
#                 "Status",
#             )
#             or "ACTIVE"
#         )
#         in {"ACTIVE", "APPROVED", "VALID", "ENABLED", "CURRENT"}
#         and str(
#             _value(
#                 row,
#                 "Requirement_ID",
#                 "RequirementId",
#                 "Requirement ID",
#                 "Req_ID",
#                 "Req ID",
#             )
#             or ""
#         ).strip()
#         in changed_requirement_ids
#     ]

#     direct_test_ids_from_rtm = {
#         str(test_case_id).strip()
#         for row in direct_impacts
#         if (
#             test_case_id := _value(
#                 row,
#                 "Test_Case_ID",
#                 "TestCase_ID",
#                 "Test Case ID",
#                 "Test_ID",
#                 "TC_ID",
#             )
#         )
#     }

#     direct_test_ids_from_test_cases = {
#         str(test_case_id).strip()
#         for row in test_case_rows
#         if (
#             test_case_id := _value(
#                 row,
#                 "Test_Case_ID",
#                 "TestCase_ID",
#                 "Test Case ID",
#                 "Test_ID",
#                 "TC_ID",
#             )
#         )
#         and str(
#             _value(
#                 row,
#                 "Requirement_ID",
#                 "RequirementId",
#                 "Requirement ID",
#                 "Req_ID",
#                 "Req ID",
#             )
#             or ""
#         ).strip() in changed_requirement_ids
#         and _normalized(
#             _value(
#                 row,
#                 "Test_Status",
#                 "Test Status",
#                 "Status",
#             )
#             or "ACTIVE"
#         ) not in {"INACTIVE", "DISABLED", "RETIRED", "DEPRECATED"}
#     }

#     direct_test_ids = sorted(
#         direct_test_ids_from_rtm
#         | direct_test_ids_from_test_cases
#     )

#     log_event(
#         "BR_CHG_02_APPLIED",
#         agent="Feature / Epic Change Impact Agent",
#         rule_id="BR-CHG-02",
#         changed_requirements=len(changed_requirement_ids),
#         direct_tests=len(direct_test_ids),
#     )

#     # ---------------------------------------------------------
#     # 6. Generate traceability gaps
#     # ---------------------------------------------------------
#     traced_requirement_ids = {
#         str(requirement_id).strip()
#         for row in rtm_rows
#         if (
#             requirement_id := _value(
#                 row,
#                 "Requirement_ID",
#                 "RequirementId",
#                 "Requirement ID",
#                 "Req_ID",
#                 "Req ID",
#             )
#         )
#         and _value(
#             row,
#             "Test_Case_ID",
#             "TestCase_ID",
#             "Test Case ID",
#             "Test_ID",
#             "TC_ID",
#         )
#     }

#     # A Test Case's own Requirement_ID is also a valid traceability source
#     # for this Jira model.
#     traced_requirement_ids.update(
#         str(requirement_id).strip()
#         for row in test_case_rows
#         if (
#             requirement_id := _value(
#                 row,
#                 "Requirement_ID",
#                 "RequirementId",
#                 "Requirement ID",
#                 "Req_ID",
#                 "Req ID",
#             )
#         )
#         and _value(
#             row,
#             "Test_Case_ID",
#             "TestCase_ID",
#             "Test Case ID",
#             "Test_ID",
#             "TC_ID",
#         )
#     )

#     traceability_gaps = [
#         {
#             "Release_ID": normalized_release_id,
#             "Requirement_ID": requirement_id,
#             "Gap_Type": "NO_TEST_CASE_MAPPING",
#             "Description": (
#                 f"Requirement {requirement_id} has "
#                 "no test-case mapping in rtm data"
#             ),
#         }
#         for requirement_id
#         in sorted(changed_requirement_ids)
#         if requirement_id
#         not in traced_requirement_ids
#     ]

#     log_event(
#         "TRACEABILITY_ANALYSIS_COMPLETED",
#         agent="Feature / Epic Change Impact Agent",
#         stage="FEATURE",
#         traceability_gaps=len(traceability_gaps),
#     )

#     # ---------------------------------------------------------
#     # 7. Determine changed modules
#     # ---------------------------------------------------------
#     changed_module_ids = {
#         str(module_id).strip()
#         for row in changed_requirements
#         if (
#             module_id := _value(
#                 row,
#                 "Module_ID",
#                 "ModuleId",
#                 "Module ID",
#                 "Module",
#             )
#         )
#     }

#     # If Module_ID is absent on a requirement, resolve it from its
#     # already-selected parent story without widening the release scope.
#     changed_requirement_story_ids = {
#         str(
#             _value(
#                 row,
#                 "User_Story_ID",
#                 "UserStory_ID",
#                 "Story_ID",
#                 "User Story ID",
#             )
#             or ""
#         ).strip()
#         for row in changed_requirements
#     }

#     for story in story_rows:
#         story_id = str(
#             _value(
#                 story,
#                 "User_Story_ID",
#                 "UserStory_ID",
#                 "Story_ID",
#                 "User Story ID",
#                 "User_Story",
#             )
#             or ""
#         ).strip()

#         if story_id not in changed_requirement_story_ids:
#             continue

#         module_id = str(
#             _value(
#                 story,
#                 "Module_ID",
#                 "ModuleId",
#                 "Module ID",
#                 "Module",
#             )
#             or ""
#         ).strip()

#         if module_id:
#             changed_module_ids.add(module_id)

#     # ---------------------------------------------------------
#     # 8. Determine downstream dependencies
#     # ---------------------------------------------------------
#     dependencies = [
#         row
#         for row in dependency_rows
#         if str(
#             _value(
#                 row,
#                 "Source_Module_ID",
#                 "Source Module ID",
#                 "Source_Module",
#                 "Source",
#             )
#             or ""
#         ).strip()
#         in changed_module_ids
#     ]

#     dependent_module_ids = {
#         str(module_id).strip()
#         for row in dependencies
#         if (
#             module_id := _value(
#                 row,
#                 "Dependent_Module_ID",
#                 "Dependent Module ID",
#                 "Target_Module_ID",
#                 "Target Module ID",
#                 "Dependent",
#                 "Target",
#             )
#         )
#     }

 

#     test_case_lookup = {
#         _test_case_id(row): row
#         for row in test_case_rows
#         if _test_case_id(row)
#     }

#     # BR-CHG-03 requires two distinct concepts:
#     # 1) all active tests on declared downstream modules, and
#     # 2) the additional downstream tests that are not already direct.
#     downstream_module_tests = [
#         row
#         for row in test_case_rows
#         if _is_active_test_case(row)
#         and _module_id(row) in dependent_module_ids
#     ]

#     downstream_module_test_ids = sorted(
#         {
#             _test_case_id(row)
#             for row in downstream_module_tests
#             if _test_case_id(row)
#         }
#     )

#     downstream_tests = [
#         row
#         for row in downstream_module_tests
#         if _test_case_id(row) not in direct_test_ids
#     ]

#     downstream_test_ids = sorted(
#         {
#             _test_case_id(row)
#             for row in downstream_tests
#             if _test_case_id(row)
#         }
#     )

#     log_event(
#         "BR_CHG_03_APPLIED",
#         agent="Feature / Epic Change Impact Agent",
#         rule_id="BR-CHG-03",
#         changed_modules=len(changed_module_ids),
#         dependent_modules=len(dependent_module_ids),
#         downstream_tests=len(downstream_test_ids),
#     )

#     # Canonical status required by the Feature Agent contract. Keep the old
#     # alias below for backward compatibility with existing consumers.
#     impact_analysis_status = "COMPLETE"
#     impact_analysis_message = ""

#     if changed_module_ids and not dependencies:
#         impact_analysis_status = "INCOMPLETE_IMPACT_ANALYSIS"
#         impact_analysis_message = (
#             "Changed modules were identified, but no declared module "
#             "dependency records were available. Downstream impact could "
#             "not be established."
#         )
#     elif dependencies and not dependent_module_ids:
#         impact_analysis_status = "INCOMPLETE_IMPACT_ANALYSIS"
#         impact_analysis_message = (
#             "Module dependency records were found, but no dependent "
#             "module IDs could be resolved."
#         )
#     elif dependent_module_ids and not downstream_module_test_ids:
#         # Dependency propagation succeeded; there simply are no active tests
#         # on the declared downstream modules. This is not an incomplete run.
#         impact_analysis_status = "COMPLETE"
#         impact_analysis_message = (
#             "Dependent modules were resolved, but no active test cases "
#             "were found on those modules."
#         )
#     elif downstream_module_test_ids and not downstream_test_ids:
#         # All downstream-module tests are already direct. Per the agent
#         # instructions, an empty downstream_test_ids must not be reported as
#         # proof that propagation was skipped.
#         impact_analysis_status = "COMPLETE"
#         impact_analysis_message = (
#             "All active tests on the declared downstream modules are already "
#             "included in the direct-impact set."
#         )

#     # ---------------------------------------------------------
#     # 9. Determine new-feature / new-epic protection
#     # ---------------------------------------------------------
#     new_epic_ids = {
#         _epic_id(row)
#         for row in changed_epics
#         if _normalized(
#             _value(
#                 row,
#                 "Change_Status",
#                 "Change Status",
#                 "Change_Type",
#                 "Change Type",
#                 "Status",
#             )
#         )
#         in {
#             "NEW",
#             "NEW_FEATURE",
#             "ADDED",
#         }
#         and _epic_id(row)
#     }

#     story_by_id = {
#         _story_id(row): row
#         for row in story_rows
#         if _story_id(row)
#     }

#     # Tests under a NEW Epic are protected at first release. Resolve the
#     # Epic through explicit test fields or the test's parent Story.
#     new_epic_test_ids = sorted(
#         {
#             _test_case_id(row)
#             for row in test_case_rows
#             if _is_active_test_case(row)
#             and (
#                 _feature_test_epic_ids(row, story_by_id)
#                 & new_epic_ids
#             )
#             and _test_case_id(row)
#         }
#     )

#     # The requirement document requires a full-coverage creation/execution
#     # action when a NEW Epic has no prior test coverage. We cannot invent a
#     # missing test count; we can only report the absence of mapped test cases
#     # from the supplied Jira/RTM data.
#     new_epics_without_prior_tests = sorted(
#         epic_id
#         for epic_id in new_epic_ids
#         if not any(
#             epic_id in _feature_test_epic_ids(
#                 row,
#                 story_by_id,
#             )
#             for row in test_case_rows
#             if _is_active_test_case(row)
#         )
#     )

#     new_epic_full_coverage_actions = [
#         {
#             "Epic_ID": epic_id,
#             "Action": "FULL_TEST_CASE_CREATION_AND_EXECUTION",
#             "Must_Test_All_New_Tests": True,
#             "Exclusion_Protected": True,
#         }
#         for epic_id in new_epics_without_prior_tests
#     ]

#     # Preserve support for existing Jira fixtures where NEW status is stored
#     # at Requirement level or an explicit test field is used. These are
#     # protection signals, but BR-CHG-05 is driven by the NEW Epic first.
#     new_requirement_ids = {
#         _requirement_id(row)
#         for row in changed_requirements
#         if _normalized(
#             _value(
#                 row,
#                 "Change_Status",
#                 "Change Status",
#                 "Requirement_Status",
#                 "Requirement Status",
#             )
#         )
#         in {
#             "NEW",
#             "NEW_FEATURE",
#             "ADDED",
#         }
#         and _requirement_id(row)
#     }

#     rtm_new_feature_test_ids = {
#         _test_case_id(row)
#         for row in direct_impacts
#         if _requirement_id(row) in new_requirement_ids
#         and _test_case_id(row)
#     }

#     direct_new_feature_test_ids = {
#         _test_case_id(row)
#         for row in test_case_rows
#         if _test_case_id(row)
#         and _requirement_id(row) in new_requirement_ids
#     }

#     explicit_new_feature_test_ids = {
#         test_case_id
#         for test_case_id in direct_test_ids
#         if _is_new_feature_test(
#             test_case_lookup.get(
#                 test_case_id,
#                 {},
#             )
#         )
#     }

#     new_feature_test_ids = sorted(
#         set(new_epic_test_ids)
#         | rtm_new_feature_test_ids
#         | direct_new_feature_test_ids
#         | explicit_new_feature_test_ids
#     )

#     log_event(
#         "BR_CHG_05_APPLIED",
#         agent="Feature / Epic Change Impact Agent",
#         rule_id="BR-CHG-05",
#         new_epics=len(new_epic_ids),
#         protected_tests=len(new_feature_test_ids),
#     )

#     new_feature_tests = [
#         test_case_lookup[test_case_id]
#         for test_case_id in new_feature_test_ids
#         if test_case_id in test_case_lookup
#     ]

#     # ---------------------------------------------------------
#     # 10. Determine out-of-scope changes
#     # ---------------------------------------------------------
#     out_of_scope_changes = [
#         row
#         for row in out_of_scope_rows
#         if _same(
#             _value(
#                 row,
#                 "Release_ID",
#                 "ReleaseId",
#                 "Release ID",
#                 "Release",
#             ),
#             normalized_release_id,
#         )
#     ]

#     direct_tests = [
#         test_case_lookup[test_case_id]
#         for test_case_id in direct_test_ids
#         if test_case_id in test_case_lookup
#     ]

#     # ---------------------------------------------------------
#     # 11. Build Change Impact Map
#     # ---------------------------------------------------------
#     # Build the full Epic -> Story -> Requirement -> Test Case chain from
#     # relationships already present in the supplied rows/RTM. No missing
#     # relationship is inferred.
#     rtm_tests_by_requirement: dict[str, set[str]] = {}
#     for row in rtm_rows:
#         if _normalized(
#             _value(
#                 row,
#                 "Mapping_Status",
#                 "Mapping Status",
#                 "Status",
#             )
#             or "ACTIVE"
#         ) not in {
#             "ACTIVE",
#             "APPROVED",
#             "VALID",
#             "ENABLED",
#             "CURRENT",
#         }:
#             continue
#         requirement_id = _requirement_id(row)
#         test_id = _test_case_id(row)
#         if requirement_id and test_id:
#             rtm_tests_by_requirement.setdefault(
#                 requirement_id,
#                 set(),
#             ).add(test_id)

#     test_ids_by_requirement: dict[str, set[str]] = {}
#     for row in test_case_rows:
#         requirement_id = _requirement_id(row)
#         test_id = _test_case_id(row)
#         if requirement_id and test_id and _is_active_test_case(row):
#             test_ids_by_requirement.setdefault(
#                 requirement_id,
#                 set(),
#             ).add(test_id)

#     tests_by_requirement = {
#         requirement_id: sorted(
#             rtm_tests_by_requirement.get(requirement_id, set())
#             | test_ids_by_requirement.get(requirement_id, set())
#         )
#         for requirement_id in changed_requirement_ids
#     }

#     stories_by_id: dict[str, dict[str, Any]] = {
#         _story_id(row): row
#         for row in story_rows
#         if _story_id(row)
#     }

#     impact_map_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}

#     for requirement in changed_requirements:
#         requirement_id = _requirement_id(requirement)
#         if not requirement_id:
#             continue

#         story_id = _story_id(requirement)
#         story = stories_by_id.get(story_id, {})
#         epic_id = _epic_id(story) or _epic_id(requirement)
#         if not epic_id:
#             continue

#         key = (epic_id, story_id, requirement_id)
#         impact_map_by_key[key] = {
#             "Epic_ID": epic_id,
#             "User_Story_ID": story_id,
#             "Requirement_ID": requirement_id,
#             "Test_Case_IDs": [
#                 test_id
#                 for test_id in tests_by_requirement.get(
#                     requirement_id,
#                     [],
#                 )
#             ],
#         }

#     change_impact_map = list(impact_map_by_key.values())

#     # ---------------------------------------------------------
#     # 12. Build structured result
#     # ---------------------------------------------------------
#     result: dict[str, Any] = {
#         "release_id": normalized_release_id,
#         "release": release,
#         "scope": scope,
#         "scoped_epic_ids": sorted(epic_ids),
#         "scoped_story_ids": sorted(
#             scoped_story_ids
#         ),
#         "scoped_requirement_ids": sorted(
#             scoped_requirement_ids
#         ),
#         "changed_epics": changed_epics,
#         "changed_stories": changed_stories,
#         "changed_story_ids": sorted(
#             changed_story_ids
#         ),
#         "changed_requirements": changed_requirements,
#         "changed_requirement_ids": sorted(
#             changed_requirement_ids
#         ),
#         "new_requirement_ids": sorted(
#             new_requirement_ids
#         ),
#         "new_epic_ids": sorted(new_epic_ids),
#         "new_epics_without_prior_tests": new_epics_without_prior_tests,
#         "new_epic_full_coverage_actions": new_epic_full_coverage_actions,
#         "change_impact_map": change_impact_map,
#         "direct_impacts": direct_impacts,
#         "direct_test_ids": direct_test_ids,
#         "direct_tests": direct_tests,
#         "changed_module_ids": sorted(
#             changed_module_ids
#         ),
#         "downstream_dependencies": dependencies,
#         "dependent_module_ids": sorted(
#             dependent_module_ids
#         ),
#         "downstream_module_test_ids": downstream_module_test_ids,
#         "downstream_test_ids": downstream_test_ids,
#         "downstream_tests": downstream_tests,
#         "impact_analysis_status": impact_analysis_status,
#         "impact_analysis_message": impact_analysis_message,
#         "downstream_analysis_status": impact_analysis_status,
#         "downstream_analysis_message": impact_analysis_message,
#         "new_feature_test_ids": (
#             new_feature_test_ids
#         ),
#         "new_feature_tests": new_feature_tests,
#         "traceability_gaps": traceability_gaps,
#         "out_of_scope_changes": (
#             out_of_scope_changes
#         ),
#         "summary": {
#             "in_scope_epics": len(
#                 changed_epics
#             ),
#             "changed_user_stories": len(
#                 changed_stories
#             ),
#             "changed_requirements": len(
#                 changed_requirements
#             ),
#             "new_requirements": len(
#                 new_requirement_ids
#             ),
#             "direct_test_cases": len(
#                 direct_test_ids
#             ),
#             "downstream_dependencies": len(
#                 dependencies
#             ),
#             "downstream_module_test_cases": len(
#                 downstream_module_test_ids
#             ),
#             "downstream_test_cases": len(
#                 downstream_test_ids
#             ),
#             "impact_analysis_status": impact_analysis_status,
#             "downstream_analysis_status": impact_analysis_status,
#             "new_feature_tests": len(
#                 new_feature_test_ids
#             ),
#             "traceability_gaps": len(
#                 traceability_gaps
#             ),
#             "out_of_scope_changes": len(
#                 out_of_scope_changes
#             ),
#         },

#         # Compact structured output intended for the next agent.
#         "agent_output": {
#             "business_rules": {
#                 "BR-CHG-01": "Only feature/epic/story-linked changes drive selection; unlinked refactors/config changes stay out of scope.",
#                 "BR-CHG-02": "Every impacted feature/epic must resolve through RTM to requirements and test cases.",
#                 "BR-CHG-03": "Declared downstream dependencies propagate impact to downstream modules/tests.",
#                 "BR-CHG-04": "Partial feature changes are scoped to the changed sub-flow requirement, not the entire epic.",
#                 "BR-CHG-05": "New features/epics without prior tests require full first-release test creation/execution and cannot be excluded.",
#             },
#             "release_id": normalized_release_id,
#             "release_type": release_type,
#             "scoped_epic_ids": sorted(epic_ids),
#             "scoped_story_ids": sorted(
#                 scoped_story_ids
#             ),
#             "scoped_requirement_ids": sorted(
#                 scoped_requirement_ids
#             ),
#             "changed_story_ids": sorted(
#                 changed_story_ids
#             ),
#             "changed_module_ids": sorted(
#                 changed_module_ids
#             ),
#             "changed_requirement_ids": sorted(
#                 changed_requirement_ids
#             ),
#             "new_requirement_ids": sorted(
#                 new_requirement_ids
#             ),
#             "new_epic_ids": sorted(new_epic_ids),
#             "new_epics_without_prior_tests": new_epics_without_prior_tests,
#             "new_epic_full_coverage_actions": new_epic_full_coverage_actions,
#             "change_impact_map": change_impact_map,
#             "direct_test_ids": direct_test_ids,
#             "downstream_dependencies": dependencies,
#             "dependent_module_ids": sorted(dependent_module_ids),
#             "downstream_module_test_ids": downstream_module_test_ids,
#             "downstream_test_ids": downstream_test_ids,
#             "impact_analysis_status": impact_analysis_status,
#             "impact_analysis_message": impact_analysis_message,
#             "new_feature_test_ids": new_feature_test_ids,
#             "traceability_gaps": traceability_gaps,
#             "traceability_gap_count": len(traceability_gaps),
#             "out_of_scope_changes": out_of_scope_changes,
#         },
#     }

#     # Safety check for accidental scope broadening.
#     all_test_ids = {
#         str(test_case_id).strip()
#         for row in test_case_rows
#         if (
#             test_case_id := _value(
#                 row,
#                 "Test_Case_ID",
#                 "TestCase_ID",
#                 "Test Case ID",
#                 "Test_ID",
#                 "TC_ID",
#             )
#         )
#     }

#     all_requirement_ids = {
#         str(requirement_id).strip()
#         for row in requirement_rows
#         if (
#             requirement_id := _value(
#                 row,
#                 "Requirement_ID",
#                 "RequirementId",
#                 "Requirement ID",
#                 "Req_ID",
#                 "Req ID",
#             )
#         )
#     }

#     if (
#         all_test_ids
#         and set(direct_test_ids) == all_test_ids
#         and (
#             scoped_story_ids
#             or scoped_requirement_ids
#         )
#         and len(changed_requirement_ids)
#         < len(all_requirement_ids)
#     ):
#         raise ValueError(
#             "Every test case was mapped as directly impacted even though "
#             "the release uses granular story or requirement scope. "
#             "Check release_scope and rtm mappings."
#         )

#     # User-facing Markdown output for ADK.
#     result["markdown"] = (
#         format_feature_change_cards(result)
#     )

#     return result

    
# def format_feature_change_cards(
#     result: dict[str, Any],
# ) -> str:
#     """
#     Convert structured Feature Agent output into Markdown cards.

#     The dictionary remains available for agent-to-agent communication.
#     The Markdown is intended for the ADK user-facing response.
#     """

#     release = result.get("release", {})
#     changed_epics = result.get(
#         "changed_epics",
#         [],
#     )
#     changed_stories = result.get(
#         "changed_stories",
#         [],
#     )
#     changed_requirements = result.get(
#         "changed_requirements",
#         [],
#     )
#     direct_tests = result.get(
#         "direct_tests",
#         [],
#     )
#     dependencies = result.get(
#         "downstream_dependencies",
#         [],
#     )
#     downstream_tests = result.get(
#         "downstream_tests",
#         [],
#     )
#     impact_analysis_status = result.get(
#         "impact_analysis_status",
#         result.get("downstream_analysis_status", "COMPLETE"),
#     )
#     impact_analysis_message = result.get(
#         "impact_analysis_message",
#         result.get("downstream_analysis_message", ""),
#     )
#     new_feature_tests = result.get(
#         "new_feature_tests",
#         [],
#     )
#     traceability_gaps = result.get(
#         "traceability_gaps",
#         [],
#     )
#     out_of_scope = result.get(
#         "out_of_scope_changes",
#         [],
#     )
#     summary = result.get("summary", {})
    
#     log_event(
#         "CHANGE_IMPACT_ANALYZED",
#         agent="Feature / Epic Change Impact Agent",
#         stage="FEATURE",
#         status="SUCCESS",
#         changed_epics=summary.get(
#             "changed_epics",
#             0,
#         ),
#         changed_stories=summary.get(
#             "changed_stories",
#             0,
#         ),
#         changed_requirements=summary.get(
#             "changed_requirements",
#             0,
#         ),
#         directly_impacted=summary.get(
#             "directly_impacted_tests",
#             0,
#         ),
#         downstream_impacted=summary.get(
#             "downstream_impacted_tests",
#             0,
#         ),
#         new_feature_tests=summary.get(
#             "new_feature_tests",
#             0,
#         ),
#     )

#     audit_event(
#         "CHANGE_IMPACT_COMPLETED",
#         agent="Feature / Epic Change Impact Agent",
#         message=(
#             f"Change impact identified "
#             f"{summary.get('directly_impacted_tests', 0)} "
#             f"directly impacted tests."
#         ),
#         details={
#             "changed_epics": summary.get(
#                 "changed_epics",
#                 0,
#             ),
#             "changed_stories": summary.get(
#                 "changed_stories",
#                 0,
#             ),
#             "changed_requirements": summary.get(
#                 "changed_requirements",
#                 0,
#             ),
#         },
#     )



#     lines: list[str] = [
#         "# Feature / Epic Change Impact",
#         "",
#         "## Release Information",
#         "",
#         "> ### "
#         f"`{_display(_value(release, 'Release_ID', 'Release ID'))}`",
#         ">",
#         "> **Release name:** "
#         f"{_display(_value(release, 'Release_Name', 'Release Name'))}",
#         ">",
#         "> **Release type:** "
#         f"`{_display(_value(release, 'Release_Type', 'Release Type'))}`",
#         ">",
#         "> **Planned date:** "
#         f"{_display_date(_value(release, 'Planned_Release_Date', 'Planned Release Date'))}",
#         ">",
#         "> **Status:** "
#         f"`{_display(_value(release, 'Status'))}`",
#         "",
#         "---",
#         "",
#         "## In-Scope Epics",
#         "",
#     ]

#     if changed_epics:
#         for epic in changed_epics:
#             epic_id = _display(
#                 _value(
#                     epic,
#                     "Epic_ID",
#                     "Epic ID",
#                 )
#             )
#             epic_name = _display(
#                 _value(
#                     epic,
#                     "Epic_Name",
#                     "Epic Name",
#                     "Name",
#                 )
#             )
#             module_id = _display(
#                 _value(
#                     epic,
#                     "Module_ID",
#                     "Module ID",
#                 )
#             )
#             change_status = _display(
#                 _value(
#                     epic,
#                     "Change_Status",
#                     "Change Status",
#                     "Change_Type",
#                 )
#             )

#             lines.extend(
#                 [
#                     f"> ### `{epic_id}` — {epic_name}",
#                     ">",
#                     f"> **Module:** `{module_id}`",
#                     ">",
#                     f"> **Change:** `{change_status}`",
#                     "",
#                 ]
#             )
#     else:
#         lines.extend(
#             [
#                 "> No in-scope epics found.",
#                 "",
#             ]
#         )

#     lines.extend(
#         [
#             "---",
#             "",
#             "## Changed User Stories",
#             "",
#         ]
#     )

#     _append_entity_cards(
#         lines=lines,
#         records=changed_stories,
#         id_fields=(
#             "User_Story_ID",
#             "Story_ID",
#             "User Story ID",
#         ),
#         name_fields=(
#             "User_Story_Name",
#             "Story_Name",
#             "Title",
#             "Description",
#         ),
#         empty_message=(
#             "No changed user stories found."
#         ),
#     )

#     lines.extend(
#         [
#             "---",
#             "",
#             "## Changed Requirements",
#             "",
#         ]
#     )

#     _append_entity_cards(
#         lines=lines,
#         records=changed_requirements,
#         id_fields=(
#             "Requirement_ID",
#             "Req_ID",
#             "Requirement ID",
#         ),
#         name_fields=(
#             "Requirement_Name",
#             "Requirement_Text",
#             "Description",
#             "Title",
#         ),
#         empty_message=(
#             "No changed requirements found."
#         ),
#     )

#     lines.extend(
#         [
#             "---",
#             "",
#             "## Directly Impacted Test Cases",
#             "",
#         ]
#     )

#     _append_test_cards(
#         lines=lines,
#         records=direct_tests,
#         empty_message=(
#             "No directly impacted test cases found."
#         ),
#     )

#     lines.extend(
#         [
#             "---",
#             "",
#             "## Downstream Dependencies",
#             "",
#         ]
#     )

#     if dependencies:
#         for dependency in dependencies:
#             source = _display(
#                 _value(
#                     dependency,
#                     "Source_Module_ID",
#                     "Source Module ID",
#                 )
#             )
#             target = _display(
#                 _value(
#                     dependency,
#                     "Dependent_Module_ID",
#                     "Dependent Module ID",
#                     "Target_Module_ID",
#                 )
#             )
#             dependency_type = _display(
#                 _value(
#                     dependency,
#                     "Dependency_Type",
#                     "Dependency Type",
#                     "Type",
#                 )
#             )
#             description = _display(
#                 _value(
#                     dependency,
#                     "Description",
#                 )
#             )

#             lines.extend(
#                 [
#                     f"> ### `{source}` → `{target}`",
#                     ">",
#                     f"> **Type:** `{dependency_type}`",
#                     ">",
#                     f"> **Description:** {description}",
#                     "",
#                 ]
#             )
#     else:
#         if impact_analysis_status == "INCOMPLETE_IMPACT_ANALYSIS":
#             lines.extend(
#                 [
#                     "> **Incomplete Impact Analysis**",
#                     ">",
#                     f"> {impact_analysis_message}",
#                     "",
#                 ]
#             )
#         else:
#             lines.extend(
#                 [
#                     "> No downstream dependencies found.",
#                     "",
#                 ]
#             )

#     lines.extend(
#         [
#             "---",
#             "",
#             "## Downstream Test Cases",
#             "",
#         ]
#     )

#     _append_test_cards(
#         lines=lines,
#         records=downstream_tests,
#         empty_message=(
#             "No downstream test cases found."
#         ),
#     )

#     lines.extend(
#         [
#             "---",
#             "",
#             "## New-Feature Protection Tests",
#             "",
#         ]
#     )

#     _append_test_cards(
#         lines=lines,
#         records=new_feature_tests,
#         empty_message=(
#             "No new-feature protection tests found."
#         ),
#     )

#     lines.extend(
#         [
#             "---",
#             "",
#             "## Traceability Gaps",
#             "",
#         ]
#     )

#     if traceability_gaps:
#         for gap in traceability_gaps:
#             lines.extend(
#                 [
#                     "> ### "
#                     f"`{_display(gap.get('Requirement_ID'))}`",
#                     ">",
#                     "> **Gap:** "
#                     f"`{_display(gap.get('Gap_Type'))}`",
#                     ">",
#                     "> **Description:** "
#                     f"{_display(gap.get('Description'))}",
#                     "",
#                 ]
#             )
#     else:
#         lines.extend(
#             [
#                 "> No traceability gaps detected.",
#                 "",
#             ]
#         )

#     lines.extend(
#         [
#             "---",
#             "",
#             "## Out-of-Scope Changes",
#             "",
#         ]
#     )

#     if out_of_scope:
#         for row in out_of_scope:
#             identifier = _display(
#                 _value(
#                     row,
#                     "Epic_ID",
#                     "Requirement_ID",
#                     "Change_ID",
#                     "Item_ID",
#                 )
#             )
#             reason = _display(
#                 _value(
#                     row,
#                     "Reason",
#                     "Description",
#                     "Change_Description",
#                 )
#             )

#             lines.extend(
#                 [
#                     f"> ### `{identifier}`",
#                     ">",
#                     f"> **Reason:** {reason}",
#                     "",
#                 ]
#             )
#     else:
#         lines.extend(
#             [
#                 "> No out-of-scope changes found.",
#                 "",
#             ]
#         )

#     lines.extend(
#         [
#             "---",
#             "",
#             "## Summary",
#             "",
#             "| Metric | Count |",
#             "|---|---:|",
#             "| In-scope epics | "
#             f"{summary.get('in_scope_epics', 0)} |",
#             "| Changed user stories | "
#             f"{summary.get('changed_user_stories', 0)} |",
#             "| Changed requirements | "
#             f"{summary.get('changed_requirements', 0)} |",
#             "| New requirements | "
#             f"{summary.get('new_requirements', 0)} |",
#             "| Direct test cases | "
#             f"{summary.get('direct_test_cases', 0)} |",
#             "| Downstream dependencies | "
#             f"{summary.get('downstream_dependencies', 0)} |",
#             "| Downstream test cases | "
#             f"{summary.get('downstream_test_cases', 0)} |",
#             "| New-feature tests | "
#             f"{summary.get('new_feature_tests', 0)} |",
#             "| Traceability gaps | "
#             f"{summary.get('traceability_gaps', 0)} |",
#             "| Out-of-scope changes | "
#             f"{summary.get('out_of_scope_changes', 0)} |",
#         ]
#     )

#     return "\n".join(lines)


# def _append_entity_cards(
#     lines: list[str],
#     records: list[dict[str, Any]],
#     id_fields: Iterable[str],
#     name_fields: Iterable[str],
#     empty_message: str,
# ) -> None:
#     """Append generic entity cards to Markdown output."""

#     if not records:
#         lines.extend(
#             [
#                 f"> {empty_message}",
#                 "",
#             ]
#         )
#         return

#     for record in records:
#         identifier = _display(
#             _value(record, *id_fields)
#         )
#         name = _display(
#             _value(record, *name_fields)
#         )
#         module_id = _display(
#             _value(
#                 record,
#                 "Module_ID",
#                 "Module ID",
#             )
#         )

#         lines.extend(
#             [
#                 f"> ### `{identifier}`",
#                 ">",
#                 f"> **Name:** {name}",
#                 ">",
#                 f"> **Module:** `{module_id}`",
#                 "",
#             ]
#         )


# def _append_test_cards(
#     lines: list[str],
#     records: list[dict[str, Any]],
#     empty_message: str,
# ) -> None:
#     """Append test-case cards to Markdown output."""

#     if not records:
#         lines.extend(
#             [
#                 f"> {empty_message}",
#                 "",
#             ]
#         )
#         return

#     for record in records:
#         test_case_id = _display(
#             _value(
#                 record,
#                 "Test_Case_ID",
#                 "TestCase_ID",
#                 "Test Case ID",
#                 "Test_ID",
#                 "TC_ID",
#             )
#         )
#         test_name = _display(
#             _value(
#                 record,
#                 "Test_Name",
#                 "Test_Case_Name",
#                 "Test Name",
#                 "Name",
#                 "Description",
#             )
#         )
#         module_id = _display(
#             _value(
#                 record,
#                 "Module_ID",
#                 "Module ID",
#             )
#         )

#         lines.extend(
#             [
#                 f"> ### `{test_case_id}`",
#                 ">",
#                 f"> **Test:** {test_name}",
#                 ">",
#                 f"> **Module:** `{module_id}`",
#                 "",
#             ]
#         )


# def _is_new_feature_test(
#     test_case: dict[str, Any],
# ) -> bool:
#     """
#     Return True when a test case is explicitly marked as
#     new-feature protection.
#     """

#     possible_fields = (
#         "New_Feature_Protection",
#         "Is_New_Feature",
#         "New_Feature_Flag",
#         "New Feature Protection",
#         "New Feature Flag",
#     )

#     value = _value(
#         test_case,
#         *possible_fields,
#     )

#     return _normalized(value) in {
#         "YES",
#         "Y",
#         "TRUE",
#         "1",
#         "ACTIVE",
#     }


# def _value(
#     row: dict[str, Any],
#     *possible_names: str,
# ) -> Any:
#     """
#     Return a value using normalized header matching.

#     Supports variations such as:
#     - Epic_ID
#     - Epic ID
#     - epic-id
#     - EpicId
#     """

#     if not row:
#         return None

#     normalized_row = {
#         _normalize_header(key): value
#         for key, value in row.items()
#     }

#     for name in possible_names:
#         normalized_name = _normalize_header(name)

#         if normalized_name in normalized_row:
#             return normalized_row[
#                 normalized_name
#             ]

#     return None


# def _normalize_header(value: Any) -> str:
#     """Normalize a field/header name for comparison."""

#     return (
#         str(value)
#         .strip()
#         .lower()
#         .replace("_", "")
#         .replace("-", "")
#         .replace(" ", "")
#     )


# def _normalized(value: Any) -> str:
#     """Normalize a cell value for status comparison."""

#     return (
#         str(value or "")
#         .strip()
#         .upper()
#         .replace("-", "_")
#         .replace(" ", "_")
#     )


# def _same(
#     first: Any,
#     second: Any,
# ) -> bool:
#     """Case-insensitive string comparison."""

#     return (
#         str(first or "").strip().upper()
#         == str(second or "").strip().upper()
#     )


# def _display(value: Any) -> str:
#     """Return a readable display value."""

#     if value is None or value == "":
#         return "Not available"

#     return str(value)


# def _display_date(value: Any) -> str:
#     """Format dates for Markdown output."""

#     if isinstance(value, datetime):
#         return value.strftime("%Y-%m-%d")

#     if isinstance(value, date):
#         return value.isoformat()

#     return _display(value)

# def analyze_jira_release_scope(
#     release_id: str,
#     jira_url: str | None = None,
#     orchestrator_context: dict[str, Any] | None = None,
# ) -> dict[str, Any]:
#     """Deprecated compatibility entry point.

#     A2A: Direct Jira access was intentionally removed from the specialist.
#     The Master Orchestrator must provide ``orchestrator_context`` containing
#     the normalized source_data block. The jira_url argument is ignored for
#     compatibility and never used to open a connection.
#     """
#     if not isinstance(orchestrator_context, dict):
#         raise RuntimeError(
#             "Feature Agent no longer reads Jira directly. Supply orchestrator_context "
#             "from the Master Orchestrator/A2A request."
#         )
#     return analyze_release_scope(
#         str(release_id or "").strip(),
#         orchestrator_context.get("source_data", orchestrator_context),
#     )

# # A2A: Specialist boundary. The Master Orchestrator calls this handler with a
# # serializable A2A envelope. The specialist never owns Jira/Excel connectivity.
# def handle_a2a_request(request: A2ARequest) -> A2AResponse:

#     try:
#         data = validate_message(
#             request,
#             receiver='Feature / Epic Change Impact Agent',
#             message_types={'FEATURE_CHANGE_REQUEST', "AGENT_QUERY"},
#         )
#         release_id = request.release_id

#     # A2A: All stage inputs arrive in request["data"], prepared by the orchestrator.
#         if request.message_type == "AGENT_QUERY":
#             return make_response(
#                 request,
#                 sender='Feature / Epic Change Impact Agent',
#                 data=answer_agent_question(
#                 question=str(data.get("question") or ""),
#                 context=data.get("agent_context", data),
#             ),
#         )

#         result = analyze_release_scope(release_id=release_id, source_data=data.get("source_data", {}))

#         return make_response(request, sender='Feature / Epic Change Impact Agent', data=result)
#     except Exception as exc:

#         trace_error(
#             "FEATURE_AGENT_FAILED",
#             agent="Feature / Epic Change Impact Agent",
#             error=exc,
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
#     "FEATURE_AGENT_QUERY",
#         agent="Feature / Epic Change Impact Agent",
#         stage="FEATURE",
#         status="SUCCESS",
#         question=question,
#     )
#     return {
#         "status": "success",
#         "agent": 'Feature / Epic Change Impact Agent',
#         "question": question,
#         "context": context,
#         "markdown": _agent_question_markdown(question, context),
#     }


# def _agent_question_markdown(question: str, context: dict[str, Any]) -> str:
#     import json
#     output = context.get("agent_output", context)
#     return "\n".join([
#         f"# {'Feature / Epic Change Impact Agent'}",
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


###################################################################################################################################################################3
#Updated code

#Feature_change_tool.py
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Iterable

from app.models import A2ARequest, A2AResponse
from app.services.a2a import make_response, validate_message
from app.logging_config import get_logger
from app.observability.logger import (
    log_event,
    trace_error,
)
from app.observability.audit import audit_event

logger = get_logger(__name__)

REQUIRED_INPUTS = (
    "releases",
    "epics",
    "stories",
    "requirements",
    "rtm",
    "release_test_cases",
    "test_cases",
    "release_scope",
    "dependencies",
    "out_of_scope",
)


# ============================================================
# Generic helpers
# ============================================================

def _rows(
    source_data: dict[str, list[dict[str, Any]]],
    input_name: str,
) -> list[dict[str, Any]]:
    """Return one required input block from Master Orchestrator."""

    if input_name not in source_data:
        raise KeyError(
            f"Master Orchestrator did not provide required input "
            f"{input_name!r}."
        )

    rows = source_data[input_name]

    if not isinstance(rows, list):
        raise TypeError(
            f"Input {input_name!r} must be provided as a list of rows."
        )

    return rows


def _normalize_header(value: Any) -> str:
    """Normalize a field/header name for tolerant matching."""

    return (
        str(value)
        .strip()
        .lower()
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
    )


def _value(
    row: dict[str, Any],
    *possible_names: str,
) -> Any:
    """
    Return a value using normalized header matching.

    Examples:
        Epic_ID
        Epic ID
        epic-id
        EpicId
    """

    if not row:
        return None

    normalized_row = {
        _normalize_header(key): value
        for key, value in row.items()
    }

    for name in possible_names:
        normalized_name = _normalize_header(name)

        if normalized_name in normalized_row:
            return normalized_row[normalized_name]

    return None


def _normalized(value: Any) -> str:
    """Normalize status/value comparisons."""

    return (
        str(value or "")
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )


def _same(
    first: Any,
    second: Any,
) -> bool:
    """Case-insensitive string comparison."""

    return (
        str(first or "").strip().upper()
        == str(second or "").strip().upper()
    )


def _display(value: Any) -> str:
    """Return a readable display value."""

    if value is None or value == "":
        return "Not available"

    return str(value)


def _display_date(value: Any) -> str:
    """Format date-like values for Markdown."""

    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")

    if isinstance(value, date):
        return value.isoformat()

    return _display(value)


# ============================================================
# ID helpers
# ============================================================

def _test_case_id(row: dict[str, Any]) -> str:
    return str(
        _value(
            row,
            "Test_Case_ID",
            "TestCase_ID",
            "Test Case ID",
            "Test_ID",
            "TC_ID",
        )
        or ""
    ).strip()


def _module_id(row: dict[str, Any]) -> str:
    return str(
        _value(
            row,
            "Module_ID",
            "ModuleId",
            "Module ID",
            "Module",
        )
        or ""
    ).strip()


def _story_id(row: dict[str, Any]) -> str:
    return str(
        _value(
            row,
            "User_Story_ID",
            "UserStory_ID",
            "Story_ID",
            "User Story ID",
            "User_Story",
            "Story",
        )
        or ""
    ).strip()


def _requirement_id(row: dict[str, Any]) -> str:
    return str(
        _value(
            row,
            "Requirement_ID",
            "RequirementId",
            "Requirement ID",
            "Req_ID",
            "Req ID",
        )
        or ""
    ).strip()


def _epic_id(row: dict[str, Any]) -> str:
    return str(
        _value(
            row,
            "Epic_ID",
            "EpicId",
            "Epic ID",
            "Epic",
        )
        or row.get("work_item_id")
        or row.get("issue_key")
        or ""
    ).strip()


def _is_active_test_case(
    row: dict[str, Any],
) -> bool:
    status = _normalized(
        _value(
            row,
            "Test_Status",
            "Test Status",
            "Status",
        )
        or "ACTIVE"
    )

    return status not in {
        "INACTIVE",
        "DISABLED",
        "RETIRED",
        "DEPRECATED",
    }


# ============================================================
# Feature/new-Epic helpers
# ============================================================

def _feature_test_epic_ids(
    test_case: dict[str, Any],
    story_by_id: dict[str, dict[str, Any]],
) -> set[str]:
    """
    Resolve Epic IDs associated with a test.

    Preference:
      1. Explicit Epic field on Test Case
      2. Parent Story -> Epic
    """

    epic_ids: set[str] = set()

    explicit_epic = _epic_id(test_case)

    if explicit_epic:
        epic_ids.add(explicit_epic)

    story_id = _story_id(test_case)

    if story_id:
        story = story_by_id.get(story_id)

        if story:
            story_epic = _epic_id(story)

            if story_epic:
                epic_ids.add(story_epic)

    return epic_ids


def _is_new_feature_test(
    test_case: dict[str, Any],
) -> bool:
    possible_fields = (
        "New_Feature_Protection",
        "Is_New_Feature",
        "New_Feature_Flag",
        "New Feature Protection",
        "New Feature Flag",
    )

    value = _value(
        test_case,
        *possible_fields,
    )

    return _normalized(value) in {
        "YES",
        "Y",
        "TRUE",
        "1",
        "ACTIVE",
    }


# ============================================================
# Release-scoped test case derivation
# ============================================================

def derive_release_test_cases(
    source_data: dict[str, list[dict[str, Any]]],
    release_id: str,
) -> list[dict[str, Any]]:
    """
    Derive the 'release_test_cases' input block (the release-scoped test
    subset analyze_release_scope requires) from already-loaded Jira data,
    for callers (the Master Orchestrator) that would otherwise need a
    separate fetch for it.

    Mirrors the same release_scope -> rtm -> test_cases join
    analyze_release_scope already performs internally for direct-impact
    calculation (see its "Direct RTM impacts" section), except scoped to
    every in-scope requirement for this release rather than only the ones
    that changed.
    """

    normalized_release_id = str(release_id or "").strip()

    release_scope_rows = source_data.get("release_scope", []) or []
    rtm_rows = source_data.get("rtm", []) or []
    all_test_case_rows = source_data.get("test_cases", []) or []

    scope = [
        row
        for row in release_scope_rows
        if (
            _same(
                _value(row, "Release_ID", "ReleaseId", "Release ID", "Release"),
                normalized_release_id,
            )
            and _normalized(
                _value(row, "Scope_Status", "Scope Status", "Status")
            )
            == "IN_SCOPE"
        )
    ]

    scoped_requirement_ids = {
        str(requirement_id).strip()
        for row in scope
        if (
            requirement_id := _value(
                row,
                "Requirement_ID",
                "RequirementId",
                "Requirement ID",
                "Req_ID",
                "Req ID",
            )
        )
    }

    rtm_test_ids = {
        str(
            _value(row, "Test_Case_ID", "TestCase_ID", "Test Case ID", "Test_ID", "TC_ID")
        ).strip()
        for row in rtm_rows
        if (
            _normalized(
                _value(row, "Mapping_Status", "Mapping Status", "Status") or "ACTIVE"
            )
            in {"ACTIVE", "APPROVED", "VALID", "ENABLED", "CURRENT"}
            and _requirement_id(row) in scoped_requirement_ids
            and _value(row, "Test_Case_ID", "TestCase_ID", "Test Case ID", "Test_ID", "TC_ID")
        )
    }

    direct_test_ids = {
        _test_case_id(row)
        for row in all_test_case_rows
        if (
            _test_case_id(row)
            and _requirement_id(row) in scoped_requirement_ids
            and _is_active_test_case(row)
        )
    }

    release_test_ids = rtm_test_ids | direct_test_ids

    return [
        row
        for row in all_test_case_rows
        if _test_case_id(row) in release_test_ids
    ]


# ============================================================
# Main Feature Agent
# ============================================================

def analyze_release_scope(
    release_id: str,
    source_data: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """
    Analyze one release using only data supplied by the
    Master Orchestrator.

    Required source blocks:
        releases
        epics
        stories
        requirements
        rtm
        release_test_cases
        test_cases
        release_scope
        dependencies
        out_of_scope

    Produces:
        changed epics
        changed stories
        changed requirements
        direct test cases
        downstream dependencies
        downstream test cases
        new-feature protection tests
        traceability gaps
        out-of-scope changes
        structured summary
        Markdown output
    """

    try:

        normalized_release_id = str(
            release_id or ""
        ).strip()

        if not normalized_release_id:
            raise ValueError(
                "release_id cannot be empty"
            )
        log_event(
            "FEATURE_ANALYSIS_STARTED",
            agent="Feature / Epic Change Impact Agent",
            stage="FEATURE",
            status="STARTED",
            release_id=normalized_release_id,
        )
        logger.info(
            "Feature Agent analysis started.",
            extra={
                "release_id": normalized_release_id,
            },
        )
        #raise ValueError("Testing Feature Agent Exception")

        # --------------------------------------------------------
        # 1. Load all required blocks
        # --------------------------------------------------------

        releases = _rows(
            source_data,
            "releases",
        )

        release_scope_rows = _rows(
            source_data,
            "release_scope",
        )

        epic_rows = _rows(
            source_data,
            "epics",
        )

        story_rows = _rows(
            source_data,
            "stories",
        )

        requirement_rows = _rows(
            source_data,
            "requirements",
        )

        rtm_rows = _rows(
            source_data,
            "rtm",
        )

        # 50 release-scoped tests: used for direct impact calculation.
        release_test_rows = _rows(
            source_data,
            "release_test_cases",
        )

        # All active tests: used for downstream discovery.
        all_test_case_rows = _rows(
            source_data,
            "test_cases",
        )

        # One lookup containing the complete test population.
        test_case_lookup = {
            _test_case_id(row): row
            for row in all_test_case_rows
            if _test_case_id(row)
        }

        dependency_rows = _rows(
            source_data,
            "dependencies",
        )

        out_of_scope_rows = _rows(
            source_data,
            "out_of_scope",
        )
        log_event(
            "FEATURE_INPUTS_LOADED",
            agent="Feature / Epic Change Impact Agent",
            stage="FEATURE",
            status="SUCCESS",
            releases=len(releases),
            epics=len(epic_rows),
            stories=len(story_rows),
            requirements=len(requirement_rows),
            test_cases=len(all_test_case_rows),
        )
        logger.info(
            "Feature Agent input data loaded.",
            extra={
                "release_id": normalized_release_id,
                "releases": len(releases),
                "epics": len(epic_rows),
                "stories": len(story_rows),
                "requirements": len(requirement_rows),
                "rtm": len(rtm_rows),
                "release_test_cases": len(release_test_rows),
                "test_cases": len(all_test_case_rows),
                "dependencies": len(dependency_rows),
                "out_of_scope": len(out_of_scope_rows),
            },
        )

        # --------------------------------------------------------
        # 2. Find the release
        # --------------------------------------------------------

        def _release_matches(
            row: dict[str, Any],
        ) -> bool:

            candidates = [
                _value(
                    row,
                    "Release_ID",
                    "ReleaseId",
                    "Release ID",
                    "Release",
                ),
                row.get("work_item_id"),
                row.get("issue_key"),
                row.get("summary"),
            ]

            target = _normalized(
                normalized_release_id
            )

            for candidate in candidates:

                if candidate is None:
                    continue

                candidate_norm = _normalized(
                    candidate
                )

                if (
                    candidate_norm == target
                    or target in candidate_norm
                ):
                    return True

            return False

        release = next(
            (
                row
                for row in releases
                if _release_matches(row)
            ),
            None,
        )

        if release is None:

            available_releases = sorted(
                {
                    str(
                        _value(
                            row,
                            "Release_ID",
                            "ReleaseId",
                            "Release ID",
                            "Release",
                        )
                        or row.get("work_item_id")
                        or row.get("issue_key")
                        or row.get("summary")
                        or ""
                    ).strip()
                    for row in releases
                    if (
                        _value(
                            row,
                            "Release_ID",
                            "ReleaseId",
                            "Release ID",
                            "Release",
                        )
                        or row.get("work_item_id")
                        or row.get("issue_key")
                        or row.get("summary")
                    )
                }
            )
            logger.error(
                "Requested release was not found.",
                extra={
                    "release_id": normalized_release_id,
                    "available_releases": available_releases,
                },
            )

            raise ValueError(
                f"Release {normalized_release_id!r} was not found "
                f"in releases data. "
                f"Available releases: {available_releases}."
            )

        release_type = _display(
            _value(
                release,
                "Release_Type",
                "Release Type",
            )
            or ""
        )

        # --------------------------------------------------------
        # 3. Determine release scope
        # --------------------------------------------------------

        scope = [
            row
            for row in release_scope_rows
            if (
                _same(
                    _value(
                        row,
                        "Release_ID",
                        "ReleaseId",
                        "Release ID",
                        "Release",
                    ),
                    normalized_release_id,
                )
                and _normalized(
                    _value(
                        row,
                        "Scope_Status",
                        "Scope Status",
                        "Status",
                    )
                )
                == "IN_SCOPE"
            )
        ]

        epic_ids = {
            str(epic_id).strip()
            for row in scope
            if (
                epic_id := _value(
                    row,
                    "Epic_ID",
                    "EpicId",
                    "Epic ID",
                    "Epic",
                )
            )
        }

        scoped_story_ids = {
            str(story_id).strip()
            for row in scope
            if (
                story_id := _value(
                    row,
                    "User_Story_ID",
                    "UserStory_ID",
                    "Story_ID",
                    "User Story ID",
                    "Story",
                )
            )
        }

        scoped_requirement_ids = {
            str(requirement_id).strip()
            for row in scope
            if (
                requirement_id := _value(
                    row,
                    "Requirement_ID",
                    "RequirementId",
                    "Requirement ID",
                    "Req_ID",
                    "Req ID",
                )
            )
        }

        def _row_epic_id(
            row: dict[str, Any],
        ) -> str:
            return str(
                _value(
                    row,
                    "Epic_ID",
                    "EpicId",
                    "Epic ID",
                    "Epic",
                )
                or row.get("work_item_id")
                or row.get("issue_key")
                or ""
            ).strip()

        def _is_changed_entity(
            row: dict[str, Any],
        ) -> bool:

            status = _normalized(
                _value(
                    row,
                    "Change_Status",
                    "Change Status",
                    "Change_Type",
                    "Change Type",
                    "Status",
                )
            )

            return status in {
                "NEW",
                "ADDED",
                "CHANGED",
                "MODIFIED",
                "UPDATED",
                "NEW_FEATURE",
            }

        # --------------------------------------------------------
        # 4. Resolve changed Epics
        # --------------------------------------------------------

        normalized_release_token = _normalized(
            normalized_release_id
        )

        if not epic_ids:

            for row in epic_rows:

                labels = row.get("labels") or []

                if not isinstance(
                    labels,
                    (list, tuple, set),
                ):
                    labels = [labels]

                normalized_labels = {
                    _normalized(label)
                    for label in labels
                }

                scope_status = _normalized(
                    _value(
                        row,
                        "Scope_Status",
                        "Scope Status",
                        "Status",
                    )
                )

                change_status = _normalized(
                    _value(
                        row,
                        "Change_Status",
                        "Change Status",
                        "Change_Type",
                    )
                )

                summary_token = _normalized(
                    row.get("summary")
                )

                if (
                    normalized_release_token
                    in normalized_labels
                    or normalized_release_token
                    in summary_token
                    or (
                        scope_status == "IN_SCOPE"
                        and change_status
                        in {
                            "MODIFIED",
                            "NEW",
                            "ADDED",
                            "CHANGED",
                        }
                    )
                ):
                    resolved_epic_id = _row_epic_id(row)

                    if resolved_epic_id:
                        epic_ids.add(
                            resolved_epic_id
                        )

        changed_epics = [
            row
            for row in epic_rows
            if _row_epic_id(row) in epic_ids
        ]
        log_event(
            "BR_CHG_01_APPLIED",
            agent="Feature / Epic Change Impact Agent",
            rule_id="BR-CHG-01",
            changed_epics=len(changed_epics),
        )

        # Explicit label fallback.
        if not changed_epics:

            for row in epic_rows:

                labels = row.get("labels") or []

                if not isinstance(
                    labels,
                    (list, tuple, set),
                ):
                    labels = [labels]

                if normalized_release_token in {
                    _normalized(value)
                    for value in labels
                }:
                    changed_epics.append(row)

        # --------------------------------------------------------
        # 5. Resolve changed User Stories
        # --------------------------------------------------------

        changed_stories: list[
            dict[str, Any]
        ] = []

        for row in story_rows:

            story_id = _story_id(row)

            story_epic_id = str(
                _value(
                    row,
                    "Epic_ID",
                    "EpicId",
                    "Epic ID",
                    "Parent_Epic_ID",
                )
                or ""
            ).strip()

            if scoped_story_ids:

                is_changed_story = (
                    story_id
                    in scoped_story_ids
                )

            elif scoped_requirement_ids:

                # Requirement-level scope is resolved below.
                is_changed_story = False

            else:

                is_changed_story = (
                    story_epic_id
                    in epic_ids
                )

            if (
                story_id
                and is_changed_story
            ):
                changed_stories.append(row)

        changed_story_ids = {
            _story_id(row)
            for row in changed_stories
            if _story_id(row)
        }

        # --------------------------------------------------------
        # 6. Resolve changed Requirements
        # --------------------------------------------------------

        changed_requirements: list[
            dict[str, Any]
        ] = []

        for row in requirement_rows:

            requirement_id = _requirement_id(row)

            requirement_story_id = _story_id(row)

            if scoped_requirement_ids:

                is_changed_requirement = (
                    requirement_id
                    in scoped_requirement_ids
                    and _is_changed_entity(row)
                )

            elif scoped_story_ids:

                is_changed_requirement = (
                    requirement_story_id
                    in scoped_story_ids
                    and _is_changed_entity(row)
                )

            else:

                is_changed_requirement = (
                    requirement_story_id
                    in changed_story_ids
                    and _is_changed_entity(row)
                )

            if (
                requirement_id
                and is_changed_requirement
            ):
                changed_requirements.append(row)

        changed_requirement_ids = {
            _requirement_id(row)
            for row in changed_requirements
            if _requirement_id(row)
        }

        # Requirement-level scope may imply stories for reporting.
        if scoped_requirement_ids:

            derived_story_ids = {
                _story_id(row)
                for row in changed_requirements
                if _story_id(row)
            }

            changed_stories = [
                row
                for row in story_rows
                if _story_id(row)
                in derived_story_ids
            ]

            changed_story_ids = {
                _story_id(row)
                for row in changed_stories
                if _story_id(row)
            }

        # --------------------------------------------------------
        # 7. Direct RTM impacts
        # --------------------------------------------------------

        direct_impacts = [
            row
            for row in rtm_rows
            if (
                _normalized(
                    _value(
                        row,
                        "Mapping_Status",
                        "Mapping Status",
                        "Status",
                    )
                    or "ACTIVE"
                )
                in {
                    "ACTIVE",
                    "APPROVED",
                    "VALID",
                    "ENABLED",
                    "CURRENT",
                }
                and _value(
                    row,
                    "Requirement_ID",
                    "RequirementId",
                    "Requirement ID",
                    "Req_ID",
                    "Req ID",
                )
                and str(
                    _value(
                        row,
                        "Requirement_ID",
                        "RequirementId",
                        "Requirement ID",
                        "Req_ID",
                        "Req ID",
                    )
                ).strip()
                in changed_requirement_ids
            )
        ]

        direct_test_ids_from_rtm = {
            str(
                _value(
                    row,
                    "Test_Case_ID",
                    "TestCase_ID",
                    "Test Case ID",
                    "Test_ID",
                    "TC_ID",
                )
            ).strip()
            for row in direct_impacts
            if _value(
                row,
                "Test_Case_ID",
                "TestCase_ID",
                "Test Case ID",
                "Test_ID",
                "TC_ID",
            )
        }

        direct_test_ids_from_test_cases = {
            _test_case_id(row)
            for row in release_test_rows
            if (
                _test_case_id(row)
                and _requirement_id(row)
                in changed_requirement_ids
                and _is_active_test_case(row)
            )
        }

        direct_test_ids = sorted(
            direct_test_ids_from_rtm
            | direct_test_ids_from_test_cases
        )
        log_event(
            "BR_CHG_02_APPLIED",
            agent="Feature / Epic Change Impact Agent",
            rule_id="BR-CHG-02",
            changed_requirements=len(changed_requirement_ids),
            direct_tests=len(direct_test_ids),
        )
        logger.info(
            "Feature Agent direct impact analysis completed.",
            extra={
                "release_id": normalized_release_id,
                "changed_epics": len(changed_epics),
                "changed_stories": len(changed_stories),
                "changed_requirements": len(changed_requirements),
                "direct_tests": len(direct_test_ids),
            },
        )

        release_test_case_lookup = {
            _test_case_id(row): row
            for row in release_test_rows
            if _test_case_id(row)
        }

        all_test_case_lookup = {
            _test_case_id(row): row
            for row in all_test_case_rows
            if _test_case_id(row)
        }

        direct_tests = [
            release_test_case_lookup[test_id]
            for test_id in direct_test_ids
            if test_id in release_test_case_lookup
        ]

        # --------------------------------------------------------
        # 8. Traceability gaps
        # --------------------------------------------------------

        traced_requirement_ids = {
            str(
                _value(
                    row,
                    "Requirement_ID",
                    "RequirementId",
                    "Requirement ID",
                    "Req_ID",
                    "Req ID",
                )
            ).strip()
            for row in rtm_rows
            if (
                _value(
                    row,
                    "Requirement_ID",
                    "RequirementId",
                    "Requirement ID",
                    "Req_ID",
                    "Req ID",
                )
                and _value(
                    row,
                    "Test_Case_ID",
                    "TestCase_ID",
                    "Test Case ID",
                    "Test_ID",
                    "TC_ID",
                )
            )
        }

        # A Test Case's own Requirement_ID is also valid traceability.
        traced_requirement_ids.update(
            _requirement_id(row)
            for row in release_test_rows
            if (
                _requirement_id(row)
                and _test_case_id(row)
            )
        )

        traceability_gaps = [
            {
                "Release_ID": normalized_release_id,
                "Requirement_ID": requirement_id,
                "Gap_Type": "NO_TEST_CASE_MAPPING",
                "Description": (
                    f"Requirement {requirement_id} has "
                    "no test-case mapping in RTM data."
                ),
            }
            for requirement_id in sorted(
                changed_requirement_ids
            )
            if (
                requirement_id
                not in traced_requirement_ids
            )
        ]
        if traceability_gaps:
            logger.warning(
                "Feature Agent found traceability gaps.",
                extra={
                    "release_id": normalized_release_id,
                    "traceability_gap_count": len(
                        traceability_gaps
                    ),
                },
            )
        else:
            logger.info(
                "Feature Agent found no traceability gaps.",
                extra={
                    "release_id": normalized_release_id,
                },
            )

        # --------------------------------------------------------
        # 9. Determine changed modules
        log_event(
            "TRACEABILITY_ANALYSIS_COMPLETED",
            agent="Feature / Epic Change Impact Agent",
            stage="FEATURE",
            traceability_gaps=len(traceability_gaps),
        )

        # --------------------------------------------------------

        changed_module_ids = {
            _module_id(row)
            for row in changed_requirements
            if _module_id(row)
        }

        # Resolve Module_ID through changed parent stories if needed.
        changed_requirement_story_ids = {
            _story_id(row)
            for row in changed_requirements
            if _story_id(row)
        }

        for story in story_rows:

            story_id = _story_id(story)

            if story_id not in (
                changed_requirement_story_ids
            ):
                continue

            module_id = _module_id(story)

            if module_id:
                changed_module_ids.add(
                    module_id
                )

        # --------------------------------------------------------
        # 10. Downstream dependency propagation
        # --------------------------------------------------------

        normalized_changed_module_ids = {
            _normalized(module_id)
            for module_id in changed_module_ids
            if _normalized(module_id)
        }

        # Modules represented by the original 50 release-scoped tests.
        # These modules are treated as already represented by the release.
        release_module_ids = {
            _normalized(_module_id(row))
            for row in release_test_rows
            if _module_id(row)
        }

        # Build a safe adjacency map. defaultdict avoids the accidental
        # NoneType.append failure from any pre-existing key/value state.
        dependency_records_by_source: dict[
            str,
            list[dict[str, Any]],
        ] = defaultdict(list)

        for row in dependency_rows:
            if not isinstance(row, dict):
                continue

            source_id = _normalized(
                _value(
                    row,
                    "Source_Module_ID",
                    "Source Module ID",
                    "Source_Module",
                    "Source",
                )
            )

            dependent_id = _normalized(
                _value(
                    row,
                    "Dependent_Module_ID",
                    "Dependent Module ID",
                    "Target_Module_ID",
                    "Target Module ID",
                    "Dependent",
                    "Target",
                )
            )

            if source_id and dependent_id and source_id != dependent_id:
                dependency_records_by_source[source_id].append(row)

        # Traverse the dependency graph from changed modules.
        # This captures both immediate and transitive downstream module impact.
        impacted_downstream_module_ids: set[str] = set()
        visited_modules: set[str] = set()
        frontier: set[str] = set(normalized_changed_module_ids)

        while frontier:
            current_module_ids = frontier - visited_modules
            if not current_module_ids:
                break

            visited_modules.update(current_module_ids)
            next_frontier: set[str] = set()

            for source_id in current_module_ids:
                for row in dependency_records_by_source.get(source_id, []):
                    dependent_id = _normalized(
                        _value(
                            row,
                            "Dependent_Module_ID",
                            "Dependent Module ID",
                            "Target_Module_ID",
                            "Target Module ID",
                            "Dependent",
                            "Target",
                        )
                    )

                    if not dependent_id:
                        continue

                    if dependent_id in normalized_changed_module_ids:
                        continue

                    impacted_downstream_module_ids.add(dependent_id)

                    if dependent_id not in visited_modules:
                        next_frontier.add(dependent_id)

            frontier = next_frontier

        normalized_impacted_module_ids = {
            _normalized(module_id)
            for module_id in impacted_downstream_module_ids
            if _normalized(module_id)
        }
        print(
        "[FEATURE DEBUG] changed_module_ids:",
        sorted(normalized_changed_module_ids),
    )

        print(
            "[FEATURE DEBUG] impacted_downstream_module_ids:",
            sorted(normalized_impacted_module_ids),
        )

        
        # A downstream dependency in the final report is an edge that leaves
        # the release's directly represented module population. This avoids
        # treating ordinary in-release module relationships as indirect impact.
        dependencies: list[dict[str, Any]] = []
        seen_dependency_keys: set[tuple[str, str, str]] = set()

        for row in dependency_rows:
            if not isinstance(row, dict):
                continue

            source_id = _normalized(
                _value(
                    row,
                    "Source_Module_ID",
                    "Source Module ID",
                    "Source_Module",
                    "Source",
                )
            )

            dependent_id = _normalized(
                _value(
                    row,
                    "Dependent_Module_ID",
                    "Dependent Module ID",
                    "Target_Module_ID",
                    "Target Module ID",
                    "Dependent",
                    "Target",
                )
            )

            dependency_type = _normalized(
                _value(
                    row,
                    "Dependency_Type",
                    "Dependency Type",
                    "Type",
                )
                or "BLOCKS"
            )

            if source_id not in normalized_changed_module_ids:
                continue

            if not dependent_id:
                continue

            if dependent_id in normalized_changed_module_ids:
                continue

            key = (source_id, dependent_id, dependency_type)
            if key in seen_dependency_keys:
                continue

            seen_dependency_keys.add(key)
            dependencies.append(row)

        downstream_only_module_ids = {
            _normalized(
                _value(
                    row,
                    "Dependent_Module_ID",
                    "Dependent Module ID",
                    "Target_Module_ID",
                    "Target Module ID",
                    "Dependent",
                    "Target",
                )
            )
            for row in dependencies
            if _value(
                row,
                "Dependent_Module_ID",
                "Dependent Module ID",
                "Target_Module_ID",
                "Target Module ID",
                "Dependent",
                "Target",
            )
        }
        downstream_only_module_ids.discard("")

        # Existing release-scoped tests that sit anywhere on the downstream
        # module closure. These are the 'downstream module tests' metric.
        downstream_module_tests = [
        row
        for row in all_test_case_rows
        if (
            _is_active_test_case(row)
            and _normalized(_module_id(row))
            in normalized_impacted_module_ids
            and _test_case_id(row)
        )
    ]

        downstream_module_test_ids = sorted({
            _test_case_id(row)
            for row in downstream_module_tests
            if _test_case_id(row)
        })
        
        print(
                "[FEATURE DEBUG] downstream_module_test_ids:",
                sorted(downstream_module_test_ids),
            )
        
        print(
                "[FEATURE DEBUG] downstream_module_tests by module:",
                {
                    module_id: sum(
                        1
                        for row in downstream_module_tests
                        if _normalized(_module_id(row)) == module_id
                    )
                    for module_id in sorted(
                        normalized_impacted_module_ids
                    )
                },
            )
        

        # New active Jira tests outside the 50 release-scoped tests are
        # downstream-only when they map to an immediate downstream module.
        release_test_id_set = {
            _test_case_id(row)
            for row in release_test_rows
            if _test_case_id(row)
        }

        downstream_only_tests = [
            row
            for row in all_test_case_rows
            if (
                _is_active_test_case(row)
                and _test_case_id(row)
                and _test_case_id(row) not in release_test_id_set
                and _normalized(_module_id(row))
                in downstream_only_module_ids
            )
        ]

        downstream_test_ids = sorted({
            _test_case_id(row)
            for row in downstream_only_tests
            if (
                _test_case_id(row)
                and _test_case_id(row)
                not in release_test_id_set
            )
        })

        # These two populations are intentionally disjoint by construction.
        downstream_overlap_ids: list[str] = []
        downstream_overlap_tests: list[dict[str, Any]] = []

        downstream_tests = list(downstream_only_tests)

        downstream_module_test_count = len(downstream_module_test_ids)
        downstream_test_count = len(downstream_test_ids)
        downstream_impacted_test_count = (
            len(downstream_module_test_ids)
        + len(downstream_test_ids)
        )
        log_event(
            "BR_CHG_03_APPLIED",
            agent="Feature / Epic Change Impact Agent",
            rule_id="BR-CHG-03",
            changed_modules=len(changed_module_ids),
            dependent_modules=len(normalized_impacted_module_ids),
            downstream_tests=len(downstream_test_ids),
        )
        logger.info(
            "Feature Agent downstream impact analysis completed.",
            extra={
                "release_id": normalized_release_id,
                "downstream_modules": len(
                    normalized_impacted_module_ids
                ),
                "downstream_module_tests": len(
                    downstream_module_test_ids
                ),
                "downstream_only_tests": len(
                    downstream_test_ids
                ),
                "downstream_impacted_tests": (
                    downstream_impacted_test_count
                ),
            },
        )

        # --------------------------------------------------------
        # Downstream analysis status
        # --------------------------------------------------------

        impact_analysis_status = "COMPLETE"
        impact_analysis_message = ""

        if changed_module_ids and not impacted_downstream_module_ids:
            impact_analysis_status = "INCOMPLETE_IMPACT_ANALYSIS"
            impact_analysis_message = (
                "Changed modules were identified, but no downstream "
                "dependency paths were found."
            )
        elif downstream_module_test_ids or downstream_test_ids:
            impact_analysis_message = (
                f"{downstream_module_test_count} existing release tests "
                "are on downstream-connected modules and "
                f"{downstream_test_count} additional downstream-only tests "
                "were identified."
            )
        elif downstream_only_module_ids:
            impact_analysis_message = (
                "Downstream modules were resolved, but no active "
                "test cases were found for downstream impact."
            )

        # --------------------------------------------------------
        # 11. New-feature / new-Epic protection
        # --------------------------------------------------------


        new_epic_ids = {
            _epic_id(row)
            for row in changed_epics
            if (
                _normalized(
                    _value(
                        row,
                        "Change_Status",
                        "Change Status",
                        "Change_Type",
                        "Change Type",
                        "Status",
                    )
                )
                in {
                    "NEW",
                    "NEW_FEATURE",
                    "ADDED",
                }
                and _epic_id(row)
            )
        }

        story_by_id = {
            _story_id(row): row
            for row in story_rows
            if _story_id(row)
        }

        new_epic_test_ids = sorted(
            {
                _test_case_id(row)
                for row in all_test_case_rows
                if (
                    _is_active_test_case(row)
                    and (
                        _feature_test_epic_ids(
                            row,
                            story_by_id,
                        )
                        & new_epic_ids
                    )
                    and _test_case_id(row)
                )
            }
        )

        new_epics_without_prior_tests = sorted(
            epic_id
            for epic_id
            in new_epic_ids
            if not any(
                (
                    epic_id
                    in _feature_test_epic_ids(
                        row,
                        story_by_id,
                    )
                )
                for row in all_test_case_rows
                if _is_active_test_case(row)
            )
        )

        new_epic_full_coverage_actions = [
            {
                "Epic_ID": epic_id,
                "Action": (
                    "FULL_TEST_CASE_CREATION_AND_EXECUTION"
                ),
                "Must_Test_All_New_Tests": True,
                "Exclusion_Protected": True,
            }
            for epic_id
            in new_epics_without_prior_tests
        ]

        new_requirement_ids = {
            _requirement_id(row)
            for row in changed_requirements
            if (
                _normalized(
                    _value(
                        row,
                        "Change_Status",
                        "Change Status",
                        "Requirement_Status",
                        "Requirement Status",
                    )
                )
                in {
                    "NEW",
                    "NEW_FEATURE",
                    "ADDED",
                }
                and _requirement_id(row)
            )
        }

        rtm_new_feature_test_ids = {
            _test_case_id(row)
            for row in direct_impacts
            if (
                _requirement_id(row)
                in new_requirement_ids
                and _test_case_id(row)
            )
        }

        direct_new_feature_test_ids = {
            _test_case_id(row)
            for row in all_test_case_rows
            if (
                _test_case_id(row)
                and _requirement_id(row)
                in new_requirement_ids
            )
        }

        explicit_new_feature_test_ids = {
            test_id
            for test_id in direct_test_ids
            if _is_new_feature_test(
                all_test_case_lookup.get(
                    test_id,
                    {},
                )
            )
        }

        new_feature_test_ids = sorted(
            set(new_epic_test_ids)
            | rtm_new_feature_test_ids
            | direct_new_feature_test_ids
            | explicit_new_feature_test_ids
        )
        log_event(
            "BR_CHG_05_APPLIED",
            agent="Feature / Epic Change Impact Agent",
            rule_id="BR-CHG-05",
            new_epics=len(new_epic_ids),
            protected_tests=len(new_feature_test_ids),
        )

        new_feature_tests = [
            all_test_case_lookup[test_id]
            for test_id in new_feature_test_ids
            if test_id in test_case_lookup
        ]

        # --------------------------------------------------------
        # 12. Out-of-scope changes
        # --------------------------------------------------------

        out_of_scope_changes = [
            row
            for row
            in out_of_scope_rows
            if _same(
                _value(
                    row,
                    "Release_ID",
                    "ReleaseId",
                    "Release ID",
                    "Release",
                ),
                normalized_release_id,
            )
        ]

        # --------------------------------------------------------
        # 13. Change Impact Map
        # --------------------------------------------------------

        rtm_tests_by_requirement: dict[
            str,
            set[str],
        ] = {}

        for row in rtm_rows:

            mapping_status = _normalized(
                _value(
                    row,
                    "Mapping_Status",
                    "Mapping Status",
                    "Status",
                )
                or "ACTIVE"
            )

            if mapping_status not in {
                "ACTIVE",
                "APPROVED",
                "VALID",
                "ENABLED",
                "CURRENT",
            }:
                continue

            requirement_id = _requirement_id(row)
            test_id = _test_case_id(row)

            if (
                requirement_id
                and test_id
            ):
                rtm_tests_by_requirement.setdefault(
                    requirement_id,
                    set(),
                ).add(test_id)

        test_ids_by_requirement: dict[
            str,
            set[str],
        ] = {}

        for row in release_test_rows:

            requirement_id = _requirement_id(row)
            test_id = _test_case_id(row)

            if (
                requirement_id
                and test_id
                and _is_active_test_case(row)
            ):
                test_ids_by_requirement.setdefault(
                    requirement_id,
                    set(),
                ).add(test_id)

        tests_by_requirement = {
            requirement_id: sorted(
                rtm_tests_by_requirement.get(
                    requirement_id,
                    set(),
                )
                | test_ids_by_requirement.get(
                    requirement_id,
                    set(),
                )
            )
            for requirement_id
            in changed_requirement_ids
        }

        stories_by_id = {
            _story_id(row): row
            for row in story_rows
            if _story_id(row)
        }

        impact_map_by_key: dict[
            tuple[str, str, str],
            dict[str, Any],
        ] = {}

        for requirement in changed_requirements:

            requirement_id = _requirement_id(
                requirement
            )

            if not requirement_id:
                continue

            story_id = _story_id(
                requirement
            )

            story = stories_by_id.get(
                story_id,
                {},
            )

            epic_id = (
                _epic_id(story)
                or _epic_id(requirement)
            )

            if not epic_id:
                continue

            key = (
                epic_id,
                story_id,
                requirement_id,
            )

            impact_map_by_key[key] = {
                "Epic_ID": epic_id,
                "User_Story_ID": story_id,
                "Requirement_ID": requirement_id,
                "Test_Case_IDs": [
                    test_id
                    for test_id
                    in tests_by_requirement.get(
                        requirement_id,
                        [],
                    )
                ],
            }

        change_impact_map = list(
            impact_map_by_key.values()
        )

        # --------------------------------------------------------
        # 14. Structured result
        # --------------------------------------------------------

        result: dict[str, Any] = {
            "release_id": normalized_release_id,
            "release": release,
            "scope": scope,

            "scoped_epic_ids": sorted(
                epic_ids
            ),
            "scoped_story_ids": sorted(
                scoped_story_ids
            ),
            "scoped_requirement_ids": sorted(
                scoped_requirement_ids
            ),

            "changed_epics": changed_epics,

            "changed_stories": changed_stories,
            "changed_story_ids": sorted(
                changed_story_ids
            ),

            "changed_requirements": (
                changed_requirements
            ),
            "changed_requirement_ids": sorted(
                changed_requirement_ids
            ),

            "new_requirement_ids": sorted(
                new_requirement_ids
            ),

            "new_epic_ids": sorted(
                new_epic_ids
            ),

            "new_epics_without_prior_tests": (
                new_epics_without_prior_tests
            ),

            "new_epic_full_coverage_actions": (
                new_epic_full_coverage_actions
            ),

            "change_impact_map": change_impact_map,

            "direct_impacts": direct_impacts,
            "direct_test_ids": direct_test_ids,
            "direct_tests": direct_tests,

            "changed_module_ids": sorted(
                changed_module_ids
            ),

            "downstream_dependencies": (
                dependencies
            ),
            "downstream_dependency_module_ids": sorted(
                downstream_only_module_ids
            ),
            "impacted_downstream_module_ids": sorted(
                normalized_impacted_module_ids
            ),

            "downstream_module_test_ids": (
                downstream_module_test_ids
            ),
            "downstream_test_ids": (
                downstream_test_ids
            ),
            "downstream_tests": (
                downstream_tests
            ),
            "downstream_overlap_ids": (
                downstream_overlap_ids
            ),
            "downstream_overlap_tests": (
                downstream_overlap_tests
            ),
            "downstream_impacted_test_count": (
                downstream_impacted_test_count
            ),

            "impact_analysis_status": (
                impact_analysis_status
            ),
            "impact_analysis_message": (
                impact_analysis_message
            ),

            "downstream_analysis_status": (
                impact_analysis_status
            ),
            "downstream_analysis_message": (
                impact_analysis_message
            ),

            "new_feature_test_ids": (
                new_feature_test_ids
            ),
            "new_feature_tests": (
                new_feature_tests
            ),

            "traceability_gaps": (
                traceability_gaps
            ),

            "out_of_scope_changes": (
                out_of_scope_changes
            ),

            "summary": {
                "in_scope_epics": len(
                    changed_epics
                ),
                "release_test_cases": len({
                    _test_case_id(row)
                    for row in release_test_rows
                    if _test_case_id(row)
                }),
                "total_active_test_cases": len({
                    _test_case_id(row)
                    for row in all_test_case_rows
                    if _test_case_id(row) and _is_active_test_case(row)
                }),
                "changed_user_stories": len(
                    changed_stories
                ),
                "changed_requirements": len(
                    changed_requirements
                ),
                "new_requirements": len(
                    new_requirement_ids
                ),
                "direct_test_cases": len(
                    direct_test_ids
                ),
                "downstream_dependencies": len(
                    dependencies
                ),
                "downstream_module_test_cases": len(
                    downstream_module_test_ids
                ),
                "downstream_test_cases": len(
                    downstream_test_ids
                ),
                "downstream_overlap": len(
                    downstream_overlap_ids
                ),
                "downstream_impacted_tests": (
                    downstream_impacted_test_count
                ),
                "impact_analysis_status": (
                    impact_analysis_status
                ),
                "downstream_analysis_status": (
                    impact_analysis_status
                ),
                "new_feature_tests": len(
                    new_feature_test_ids
                ),
                "traceability_gaps": len(
                    traceability_gaps
                ),
                "out_of_scope_changes": len(
                    out_of_scope_changes
                ),
            },

            "agent_output": {
                "release_id": (
                    normalized_release_id
                ),
                "release_type": release_type,

                "scoped_epic_ids": sorted(
                    epic_ids
                ),
                "scoped_story_ids": sorted(
                    scoped_story_ids
                ),
                "scoped_requirement_ids": sorted(
                    scoped_requirement_ids
                ),

                "changed_story_ids": sorted(
                    changed_story_ids
                ),
                "changed_module_ids": sorted(
                    changed_module_ids
                ),
                "changed_requirement_ids": sorted(
                    changed_requirement_ids
                ),

                "new_requirement_ids": sorted(
                    new_requirement_ids
                ),
                "new_epic_ids": sorted(
                    new_epic_ids
                ),

                "new_epics_without_prior_tests": (
                    new_epics_without_prior_tests
                ),

                "new_epic_full_coverage_actions": (
                    new_epic_full_coverage_actions
                ),

                "change_impact_map": (
                    change_impact_map
                ),

                "direct_test_ids": (
                    direct_test_ids
                ),

                "downstream_dependencies": (
                    dependencies
                ),

                "downstream_dependency_module_ids": sorted(
                    downstream_only_module_ids
                ),

                "impacted_downstream_module_ids": sorted(
                    normalized_impacted_module_ids
                ),

                "downstream_module_test_ids": (
                    downstream_module_test_ids
                ),

                "downstream_test_ids": (
                    downstream_test_ids
                ),

                "downstream_overlap_ids": (
                    downstream_overlap_ids
                ),

                "downstream_overlap_count": len(
                    downstream_overlap_ids
                ),

                "downstream_impacted_test_count": (
                    downstream_impacted_test_count
                ),

                "impact_analysis_status": (
                    impact_analysis_status
                ),

                "impact_analysis_message": (
                    impact_analysis_message
                ),

                "new_feature_test_ids": (
                    new_feature_test_ids
                ),

                "traceability_gaps": (
                    traceability_gaps
                ),

                "traceability_gap_count": len(
                    traceability_gaps
                ),

                "out_of_scope_changes": (
                    out_of_scope_changes
                ),
            },
        }

        # --------------------------------------------------------
        # 15. Safety check
        # --------------------------------------------------------

        all_test_ids = {
            _test_case_id(row)
            for row in release_test_rows
            if _test_case_id(row)
        }

        all_requirement_ids = {
            _requirement_id(row)
            for row in requirement_rows
            if _requirement_id(row)
        }

        if (
            all_test_ids
            and set(direct_test_ids)
            == all_test_ids
            and (
                scoped_story_ids
                or scoped_requirement_ids
            )
            and len(changed_requirement_ids)
            < len(all_requirement_ids)
        ):
            logger.error(
                "Feature Agent safety check failed: "
                "all release tests were marked directly impacted "
                "despite granular release scope.",
                extra={
                    "release_id": normalized_release_id,
                    "release_test_count": len(all_test_ids),
                    "direct_test_count": len(direct_test_ids),
                    "changed_requirement_count": len(
                        changed_requirement_ids
                    ),
                    "total_requirement_count": len(
                        all_requirement_ids
                    ),
                },
            )
            raise ValueError(
                "Every test case was mapped as directly impacted even though "
                "the release uses granular story or requirement scope. "
                "Check release_scope and RTM mappings."
            )

        # --------------------------------------------------------
        # 16. User-facing Markdown
        # --------------------------------------------------------

        result["markdown"] = (
            format_feature_change_cards(result)
        )

        summary = result.get("summary", {})
        log_event(
            "CHANGE_IMPACT_ANALYZED",
            agent="Feature / Epic Change Impact Agent",
            stage="FEATURE",
            status="SUCCESS",
            changed_epics=summary.get("in_scope_epics", 0),
            changed_stories=summary.get("changed_user_stories", 0),
            changed_requirements=summary.get("changed_requirements", 0),
            directly_impacted=summary.get("direct_test_cases", 0),
            downstream_impacted=summary.get("downstream_impacted_tests", 0),
            new_feature_tests=summary.get("new_feature_tests", 0),
        )
        audit_event(
            "CHANGE_IMPACT_COMPLETED",
            agent="Feature / Epic Change Impact Agent",
            release_id=normalized_release_id,
            message=(
                f"Change impact identified "
                f"{summary.get('direct_test_cases', 0)} directly impacted tests."
            ),
            details={
                "changed_epics": summary.get("in_scope_epics", 0),
                "changed_stories": summary.get("changed_user_stories", 0),
                "changed_requirements": summary.get("changed_requirements", 0),
            },
        )
        logger.info(
            "Feature Agent analysis completed successfully.",
            extra={
                "release_id": normalized_release_id,
                "changed_epics": len(changed_epics),
                "changed_stories": len(changed_stories),
                "changed_requirements": len(
                    changed_requirements
                ),
                "direct_tests": len(direct_test_ids),
                "downstream_tests": len(
                    downstream_test_ids
                ),
                "new_feature_tests": len(
                    new_feature_test_ids
                ),
                "traceability_gaps": len(
                    traceability_gaps
                ),
            },
        )

        return result
        

    except Exception as exc:
        logger.exception(
            "Feature Agent analysis failed.",
            extra={
                "release_id": str(release_id or "").strip(),
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        trace_error(
            "FEATURE_AGENT_FAILED",
            agent="Feature / Epic Change Impact Agent",
            error=exc,
        )
        raise



# ============================================================
# Markdown formatting
# ============================================================

def format_feature_change_cards(
    result: dict[str, Any],
) -> str:
    """
    Convert structured Feature Agent output into Markdown.

    The structured dictionary remains the agent-to-agent contract.
    Markdown is the user-facing representation.
    """

    release = result.get(
        "release",
        {},
    )

    changed_epics = result.get(
        "changed_epics",
        [],
    )

    changed_stories = result.get(
        "changed_stories",
        [],
    )

    changed_requirements = result.get(
        "changed_requirements",
        [],
    )

    direct_tests = result.get(
        "direct_tests",
        [],
    )

    dependencies = result.get(
        "downstream_dependencies",
        [],
    )

    downstream_tests = result.get(
        "downstream_tests",
        [],
    )

    new_feature_tests = result.get(
        "new_feature_tests",
        [],
    )

    traceability_gaps = result.get(
        "traceability_gaps",
        [],
    )

    out_of_scope = result.get(
        "out_of_scope_changes",
        [],
    )

    impact_analysis_status = result.get(
        "impact_analysis_status",
        result.get(
            "downstream_analysis_status",
            "COMPLETE",
        ),
    )

    impact_analysis_message = result.get(
        "impact_analysis_message",
        result.get(
            "downstream_analysis_message",
            "",
        ),
    )

    summary = result.get(
        "summary",
        {},
    )

    lines: list[str] = [
        "# Feature / Epic Change Impact",
        "",
        "## Release Information",
        "",
        "> ### "
        f"`{_display(_value(release, 'Release_ID', 'Release ID'))}`",
        ">",
        "> **Release name:** "
        f"{_display(_value(release, 'Release_Name', 'Release Name'))}",
        ">",
        "> **Release type:** "
        f"`{_display(_value(release, 'Release_Type', 'Release Type'))}`",
        ">",
        "> **Planned date:** "
        f"{_display_date(_value(release, 'Planned_Release_Date', 'Planned Release Date'))}",
        ">",
        "> **Status:** "
        f"`{_display(_value(release, 'Status'))}`",
        "",
        "---",
        "",
        "## In-Scope Epics",
        "",
    ]

    if changed_epics:

        for epic in changed_epics:

            epic_id = _display(
                _value(
                    epic,
                    "Epic_ID",
                    "Epic ID",
                )
            )

            epic_name = _display(
                _value(
                    epic,
                    "Epic_Name",
                    "Epic Name",
                    "Name",
                )
            )

            module_id = _display(
                _value(
                    epic,
                    "Module_ID",
                    "Module ID",
                )
            )

            change_status = _display(
                _value(
                    epic,
                    "Change_Status",
                    "Change Status",
                    "Change_Type",
                )
            )

            lines.extend(
                [
                    f"> ### `{epic_id}` — {epic_name}",
                    ">",
                    f"> **Module:** `{module_id}`",
                    ">",
                    f"> **Change:** `{change_status}`",
                    "",
                ]
            )

    else:

        lines.extend(
            [
                "> No in-scope epics found.",
                "",
            ]
        )

    # Stories
    lines.extend(
        [
            "---",
            "",
            "## Changed User Stories",
            "",
        ]
    )

    _append_entity_cards(
        lines=lines,
        records=changed_stories,
        id_fields=(
            "User_Story_ID",
            "Story_ID",
            "User Story ID",
        ),
        name_fields=(
            "User_Story_Name",
            "Story_Name",
            "Title",
            "Description",
        ),
        empty_message=(
            "No changed user stories found."
        ),
    )

    # Requirements
    lines.extend(
        [
            "---",
            "",
            "## Changed Requirements",
            "",
        ]
    )

    _append_entity_cards(
        lines=lines,
        records=changed_requirements,
        id_fields=(
            "Requirement_ID",
            "Req_ID",
            "Requirement ID",
        ),
        name_fields=(
            "Requirement_Name",
            "Requirement_Text",
            "Description",
            "Title",
        ),
        empty_message=(
            "No changed requirements found."
        ),
    )

    # Direct tests
    lines.extend(
        [
            "---",
            "",
            "## Directly Impacted Test Cases",
            "",
        ]
    )

    _append_test_cards(
        lines=lines,
        records=direct_tests,
        empty_message=(
            "No directly impacted test cases found."
        ),
    )

    # Downstream dependencies
    lines.extend(
        [
            "---",
            "",
            "## Downstream Dependencies",
            "",
        ]
    )

    if dependencies:

        for dependency in dependencies:

            source = _display(
                _value(
                    dependency,
                    "Source_Module_ID",
                    "Source Module ID",
                )
            )

            target = _display(
                _value(
                    dependency,
                    "Dependent_Module_ID",
                    "Dependent Module ID",
                    "Target_Module_ID",
                    "Target Module ID",
                )
            )

            dependency_type = _display(
                _value(
                    dependency,
                    "Dependency_Type",
                    "Dependency Type",
                    "Type",
                )
            )

            description = _display(
                _value(
                    dependency,
                    "Description",
                )
            )

            lines.extend(
                [
                    f"> ### `{source}` → `{target}`",
                    ">",
                    f"> **Type:** `{dependency_type}`",
                    ">",
                    f"> **Description:** {description}",
                    "",
                ]
            )

    else:

        if (
            impact_analysis_status
            == "INCOMPLETE_IMPACT_ANALYSIS"
        ):
            lines.extend(
                [
                    "> **Incomplete Impact Analysis**",
                    ">",
                    f"> {impact_analysis_message}",
                    "",
                ]
            )

        else:
            lines.extend(
                [
                    "> No downstream dependencies found.",
                    "",
                ]
            )

    # Downstream tests
    lines.extend(
        [
            "---",
            "",
            "## Downstream Test Cases",
            "",
        ]
    )

    _append_test_cards(
        lines=lines,
        records=downstream_tests,
        empty_message=(
            "No downstream test cases found."
        ),
    )

    # New feature tests
    lines.extend(
        [
            "---",
            "",
            "## New-Feature Protection Tests",
            "",
        ]
    )

    _append_test_cards(
        lines=lines,
        records=new_feature_tests,
        empty_message=(
            "No new-feature protection tests found."
        ),
    )

    # Traceability gaps
    lines.extend(
        [
            "---",
            "",
            "## Traceability Gaps",
            "",
        ]
    )

    if traceability_gaps:

        for gap in traceability_gaps:

            lines.extend(
                [
                    "> ### "
                    f"`{_display(gap.get('Requirement_ID'))}`",
                    ">",
                    "> **Gap:** "
                    f"`{_display(gap.get('Gap_Type'))}`",
                    ">",
                    "> **Description:** "
                    f"{_display(gap.get('Description'))}",
                    "",
                ]
            )

    else:

        lines.extend(
            [
                "> No traceability gaps detected.",
                "",
            ]
        )

    # Out of scope
    lines.extend(
        [
            "---",
            "",
            "## Out-of-Scope Changes",
            "",
        ]
    )

    if out_of_scope:

        for row in out_of_scope:

            identifier = _display(
                _value(
                    row,
                    "Epic_ID",
                    "Requirement_ID",
                    "Change_ID",
                    "Item_ID",
                )
            )

            reason = _display(
                _value(
                    row,
                    "Reason",
                    "Description",
                    "Change_Description",
                )
            )

            lines.extend(
                [
                    f"> ### `{identifier}`",
                    ">",
                    f"> **Reason:** {reason}",
                    "",
                ]
            )

    else:

        lines.extend(
            [
                "> No out-of-scope changes found.",
                "",
            ]
        )

    # Summary
    lines.extend(
        [
            "---",
            "",
            "## Summary",
            "",
            "| Metric | Count |",
            "|---|---:|",
            "| In-scope epics | "
            f"{summary.get('in_scope_epics', 0)} |",
            "| Changed user stories | "
            f"{summary.get('changed_user_stories', 0)} |",
            "| Changed requirements | "
            f"{summary.get('changed_requirements', 0)} |",
            "| New requirements | "
            f"{summary.get('new_requirements', 0)} |",
            "| Direct test cases | "
            f"{summary.get('direct_test_cases', 0)} |",
            "| Downstream dependencies | "
            f"{summary.get('downstream_dependencies', 0)} |",
            "| Downstream module test cases | "
            f"{summary.get('downstream_module_test_cases', 0)} |",
            "| Downstream test cases | "
            f"{summary.get('downstream_test_cases', 0)} |",
            "| Downstream impacted tests | "
            f"{summary.get('downstream_impacted_tests', 0)} |",
            "| Downstream overlap | "
            f"{summary.get('downstream_overlap', 0)} |",
            "| New-feature tests | "
            f"{summary.get('new_feature_tests', 0)} |",
            "| Traceability gaps | "
            f"{summary.get('traceability_gaps', 0)} |",
            "| Out-of-scope changes | "
            f"{summary.get('out_of_scope_changes', 0)} |",
        ]
    )

    return "\n".join(lines)


# ============================================================
# Markdown card helpers
# ============================================================

def _append_entity_cards(
    lines: list[str],
    records: list[dict[str, Any]],
    id_fields: Iterable[str],
    name_fields: Iterable[str],
    empty_message: str,
) -> None:
    """Append generic entity cards."""

    if not records:

        lines.extend(
            [
                f"> {empty_message}",
                "",
            ]
        )

        return

    for record in records:

        identifier = _display(
            _value(
                record,
                *id_fields,
            )
        )

        name = _display(
            _value(
                record,
                *name_fields,
            )
        )

        module_id = _display(
            _value(
                record,
                "Module_ID",
                "Module ID",
            )
        )

        lines.extend(
            [
                f"> ### `{identifier}`",
                ">",
                f"> **Name:** {name}",
                ">",
                f"> **Module:** `{module_id}`",
                "",
            ]
        )


def _append_test_cards(
    lines: list[str],
    records: list[dict[str, Any]],
    empty_message: str,
) -> None:
    """Append test case cards."""

    if not records:

        lines.extend(
            [
                f"> {empty_message}",
                "",
            ]
        )

        return

    for record in records:

        test_case_id = _display(
            _value(
                record,
                "Test_Case_ID",
                "TestCase_ID",
                "Test Case ID",
                "Test_ID",
                "TC_ID",
            )
        )

        test_name = _display(
            _value(
                record,
                "Test_Name",
                "Test_Case_Name",
                "Test Name",
                "Name",
                "Description",
            )
        )

        module_id = _display(
            _value(
                record,
                "Module_ID",
                "Module ID",
            )
        )

        lines.extend(
            [
                f"> ### `{test_case_id}`",
                ">",
                f"> **Test:** {test_name}",
                ">",
                f"> **Module:** `{module_id}`",
                "",
            ]
        )


def analyze_jira_release_scope(
    release_id: str,
    jira_url: str | None = None,
    orchestrator_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deprecated compatibility entry point.

    A2A: Direct Jira access was intentionally removed from the specialist.
    The Master Orchestrator must provide ``orchestrator_context`` containing
    the normalized source_data block. The jira_url argument is ignored for
    compatibility and never used to open a connection.
    """
    if not isinstance(orchestrator_context, dict):
        raise RuntimeError(
            "Feature Agent no longer reads Jira directly. Supply orchestrator_context "
            "from the Master Orchestrator/A2A request."
        )
    return analyze_release_scope(
        str(release_id or "").strip(),
        orchestrator_context.get("source_data", orchestrator_context),
    )

# A2A: Specialist boundary. The Master Orchestrator calls this handler with a
# serializable A2A envelope. The specialist never owns Jira/Excel connectivity.
def handle_a2a_request(request: A2ARequest) -> A2AResponse:

    try:
        data = validate_message(
            request,
            receiver='Feature / Epic Change Impact Agent',
            message_types={'FEATURE_CHANGE_REQUEST', "AGENT_QUERY"},
        )
        release_id = request.release_id

    # A2A: All stage inputs arrive in request["data"], prepared by the orchestrator.
        if request.message_type == "AGENT_QUERY":
            return make_response(
                request,
                sender='Feature / Epic Change Impact Agent',
                data=answer_agent_question(
                question=str(data.get("question") or ""),
                context=data.get("agent_context", data),
            ),
        )

        result = analyze_release_scope(release_id=release_id, source_data=data.get("source_data", {}))

        return make_response(request, sender='Feature / Epic Change Impact Agent', data=result)
    except Exception as exc:

        trace_error(
            "FEATURE_AGENT_FAILED",
            agent="Feature / Epic Change Impact Agent",
            error=exc,
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
    "FEATURE_AGENT_QUERY",
        agent="Feature / Epic Change Impact Agent",
        stage="FEATURE",
        status="SUCCESS",
        question=question,
    )
    return {
        "status": "success",
        "agent": 'Feature / Epic Change Impact Agent',
        "question": question,
        "context": context,
        "markdown": _agent_question_markdown(question, context),
    }


def _agent_question_markdown(question: str, context: dict[str, Any]) -> str:
    import json
    output = context.get("agent_output", context)
    return "\n".join([
        f"# {'Feature / Epic Change Impact Agent'}",
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

