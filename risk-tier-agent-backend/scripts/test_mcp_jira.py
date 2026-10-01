from __future__ import annotations

import sys
from typing import Any
import traceback

from app.integrations.mcp_jira_client import MCPJiraClient


def _issue_type(issue: dict[str, Any]) -> str:
    fields = issue.get("fields") or {}
    issue_type = fields.get("issuetype") or {}
    if isinstance(issue_type, dict):
        return str(issue_type.get("name") or "").strip()
    return str(issue_type or "").strip()


def _summary(issue: dict[str, Any]) -> str:
    return str((issue.get("fields") or {}).get("summary") or "").strip()


def main() -> int:
    client = MCPJiraClient()

    print("=== Jira MCP diagnostic ===")

    try:
        ping = client.ping()
        print(f"ping: OK -> {ping}")
    except Exception as exc:
        print(f"ping: FAILED -> {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 1

    try:
        fields = client.list_fields()
        print(f"list_fields: OK -> {len(fields)} fields")
    except Exception as exc:
        print(f"list_fields: FAILED -> {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 1

    try:
        issues = client.search(
            'project = "SCRUM" ORDER BY key ASC',
            ["summary", "issuetype", "status", "labels", "parent"],
        )
        print(f"search: OK -> {len(issues)} issues")
    except Exception as exc:
        print(f"search: FAILED -> {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 1

    counts: dict[str, int] = {}
    for issue in issues:
        name = _issue_type(issue) or "UNKNOWN"
        counts[name] = counts.get(name, 0) + 1

    print("\nIssue type counts:")
    for name in sorted(counts):
        print(f"  {name:<24} {counts[name]}")

    releases = [
        issue
        for issue in issues
        if _issue_type(issue).upper() == "RELEASE"
    ]
    if releases:
        print("\nRelease issues:")
        for issue in releases:
            print(f"  {issue.get('key', '')}: {_summary(issue)}")

    # Show the custom fields most important to the Risk Tier integration.
    interesting_terms = (
        "release",
        "regulatory",
        "test case",
        "module",
        "policy",
        "flaky",
        "defect",
        "execution",
        "mapping",
    )
    interesting_fields = [
        (str(field.get("id") or ""), str(field.get("name") or ""))
        for field in fields
        if any(
            term in str(field.get("name") or "").lower()
            for term in interesting_terms
        )
    ]

    print("\nRelevant Jira fields:")
    for field_id, name in interesting_fields:
        print(f"  {field_id:<24} {name}")

    print("\nMCP/Jira diagnostic completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
