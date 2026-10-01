"""
Copy the relevant pattern into your existing master_orchestrator.py.
The specialist-agent function names below match the names used in your project.
"""
from __future__ import annotations

import os

from app.data_sources.hybrid_source import HybridRiskTierSource
from app.integrations.jira_client import JiraClient, JiraConfig
from app.repositories.test_repository import TestRepository


def build_hybrid_source() -> HybridRiskTierSource:
    config = JiraConfig(
        base_url=os.environ["JIRA_BASE_URL"],
        email=os.environ["JIRA_EMAIL"],
        api_token=os.environ["JIRA_API_TOKEN"],
        project_key=os.environ["JIRA_PROJECT_KEY"],
        epic_issue_type=os.getenv("JIRA_EPIC_ISSUE_TYPE", "Epic"),
        story_issue_type=os.getenv("JIRA_STORY_ISSUE_TYPE", "Story"),
        epic_id_field=os.environ["JIRA_FIELD_EPIC_ID"],
        story_id_field=os.environ["JIRA_FIELD_STORY_ID"],
        module_id_field=os.environ["JIRA_FIELD_MODULE_ID"],
        change_status_field=os.environ["JIRA_FIELD_CHANGE_STATUS"],
        release_label=os.environ["JIRA_RELEASE_LABEL"],
    )
    return HybridRiskTierSource(
        JiraClient(config),
        TestRepository(os.getenv("TEST_REPOSITORY_DB", "data/test_repository.db")),
    )


def inject_external_data_into_pipeline(repository, release_id: str) -> dict:
    """
    repository is your existing ExcelRepository. It still supplies requirements,
    RTM, modules, history, defects, policies, weights and thresholds.
    """
    external = build_hybrid_source().load_release_hierarchy(release_id)

    source_data = {
        "00_Modules": repository.rows("00_Modules"),
        "01_Releases": repository.rows("01_Releases"),
        "02_Epics": external["02_Epics"],
        "03_User_Stories": external["03_User_Stories"],
        "04_Requirements": repository.rows("04_Requirements"),
        "05_RTM": repository.rows("05_RTM"),
        "06_Test_Cases": external["06_Test_Cases"],
        "A1_Release_Scope": repository.rows("A1_Release_Scope"),
        "A1_Dependencies": repository.rows("A1_Dependencies"),
        "A1_Out_of_Scope": repository.rows("A1_Out_of_Scope"),
        "A2_Criticality_Factors": repository.rows("A2_Criticality_Factors"),
        "A2_Tier_Change_Log": repository.rows("A2_Tier_Change_Log"),
        "A3_Test_Executions": repository.rows("A3_Test_Executions"),
        "A3_Defects": repository.rows("A3_Defects"),
        "A3_Flaky_Tests": repository.rows("A3_Flaky_Tests"),
        "A4_Risk_Policies": repository.rows("A4_Risk_Policies"),
        "A4_Regulatory_Tests": repository.rows("A4_Regulatory_Tests"),
        "A4_Release_Rules": repository.rows("A4_Release_Rules"),
        "A5_Scoring_Weights": repository.rows("A5_Scoring_Weights"),
        "A5_Thresholds": repository.rows("A5_Thresholds"),
    }
    return source_data

# In your execute_risk_tier_pipeline():
# source_data = inject_external_data_into_pipeline(repository, normalized_release_id)
#
# feature = analyze_release_scope(release_id=normalized_release_id, source_data=source_data)
# criticality = classify_application_criticality(source_data=source_data)
# history = analyze_historical_execution(source_data=source_data)
# policy = calibrate_risk_policy(release_id=normalized_release_id, source_data=source_data)
# scoring = calculate_test_selection(
#     source_data=source_data,
#     change_impact=feature,
#     criticality=criticality,
#     history=history,
#     policy=policy,
# )
# governance = evaluate_exclusion_governance(scoring=scoring, policy=policy)
