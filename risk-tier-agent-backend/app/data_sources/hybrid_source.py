from __future__ import annotations

from typing import Any

from app.integrations.jira_client import JiraClient
from app.repository.test_repository import TestRepository


class HybridRiskTierSource:
    """Jira supplies Epics/Stories; SQLite supplies the large test repository."""

    def __init__(self, jira: JiraClient, tests: TestRepository) -> None:
        self.jira = jira
        self.tests = tests

    def load_release_hierarchy(self, release_label: str) -> dict[str, list[dict[str, Any]]]:
        c = self.jira.config
        fields = [
            "summary", "status", "issuetype", "parent", "labels",
            c.epic_id_field, c.story_id_field, c.module_id_field, c.change_status_field,
        ]
        jql = (
            f'project = "{c.project_key}" AND labels = "{release_label}" '
            f'AND issuetype in ("{c.epic_issue_type}", "{c.story_issue_type}")'
        )
        issues = self.jira.search(jql, fields)
        epics: list[dict[str, Any]] = []
        stories: list[dict[str, Any]] = []
        active_story_ids: list[str] = []
        epic_id_by_key: dict[str, str] = {}

        # First pass builds the Epic Jira-key -> business Epic_ID map.
        for issue in issues:
            f = issue.get("fields", {})
            issue_type = str(f.get("issuetype", {}).get("name", ""))
            if issue_type != c.epic_issue_type:
                continue
            epic_id = str(f.get(c.epic_id_field) or "").strip()
            if not epic_id:
                continue
            epic_id_by_key[str(issue.get("key") or "")] = epic_id
            epics.append({
                "Epic_ID": epic_id,
                "Epic_Name": f.get("summary"),
                "Module_ID": _option(f.get(c.module_id_field)),
                "Change_Status": _option(f.get(c.change_status_field)),
                "Jira_Key": issue.get("key"),
            })

        # Second pass converts Stories and resolves each parent Epic_ID.
        for issue in issues:
            f = issue.get("fields", {})
            issue_type = str(f.get("issuetype", {}).get("name", ""))
            if issue_type != c.story_issue_type:
                continue
            story_id = str(f.get(c.story_id_field) or "").strip()
            if not story_id:
                continue
            active_story_ids.append(story_id)
            parent_key = str((f.get("parent") or {}).get("key") or "")
            stories.append({
                "Story_ID": story_id,
                "Epic_ID": epic_id_by_key.get(parent_key),
                "Epic_Jira_Key": parent_key,
                "Story_Description": f.get("summary"),
                "Change_Status": _option(f.get(c.change_status_field)),
                "Jira_Key": issue.get("key"),
            })

        return {
            "02_Epics": epics,
            "03_User_Stories": stories,
            "06_Test_Cases": self.tests.active_tests(active_story_ids),
        }


def _option(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("value") or value.get("name") or value.get("id")
    return value
