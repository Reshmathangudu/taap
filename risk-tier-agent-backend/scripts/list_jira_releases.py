from __future__ import annotations

import json
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.integrations.mcp_jira_client import MCPJiraClient

# Mirrors the exact release-recognition rules the pipeline uses in
# app/orchestrator/master_orchestrator.py (_jira_issue_category,
# _extract_work_item_id) — this script exists to answer, ahead of running
# the real pipeline, "which release IDs would the app actually find in
# whichever Jira account is currently configured in .env?".
#
# Every line printed to the terminal is also written to a .txt report, and
# the full raw issue data plus the structured findings are written to a
# .json file, both under <RISK_TIER_OUTPUT_DIR>/jira_release_inventory/.
# This script never touches app/persistence/ (the real Jira cache) — it is
# read-only against Jira and only ever writes these two report files.

WORK_ITEM_TAG_RE = re.compile(r"\[\s*([A-Za-z]{2,10}-\d+(?:\.\d+)?)\s*\]")


class Report:
    """Collects every printed line so it can also be flushed to a .txt file."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def print(self, text: str = "") -> None:
        print(text)
        self.lines.extend(text.split("\n"))

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def _issue_type(issue: dict[str, Any]) -> str:
    fields = issue.get("fields") or {}
    issue_type = fields.get("issuetype") or {}
    if isinstance(issue_type, dict):
        return str(issue_type.get("name") or "").strip()
    return str(issue_type or "").strip()


def _summary(issue: dict[str, Any]) -> str:
    return str((issue.get("fields") or {}).get("summary") or "").strip()


def _labels(issue: dict[str, Any]) -> list[str]:
    labels = (issue.get("fields") or {}).get("labels") or []
    if not isinstance(labels, list):
        labels = [labels]
    return [str(label).strip() for label in labels if label]


def _fix_versions(issue: dict[str, Any]) -> list[str]:
    raw = (issue.get("fields") or {}).get("fixVersions") or []
    if not isinstance(raw, list):
        raw = [raw]
    names: list[str] = []
    for version in raw:
        if isinstance(version, dict):
            name = version.get("name") or version.get("value") or ""
        else:
            name = version
        name = str(name or "").strip()
        if name:
            names.append(name)
    return names


def _work_item_id(issue: dict[str, Any]) -> str:
    """Same convention as _extract_work_item_id: a bracketed tag in the
    summary (e.g. "[REL-25.4] ...") wins; otherwise falls back to the raw
    Jira issue key."""
    match = WORK_ITEM_TAG_RE.search(_summary(issue))
    if match:
        return match.group(1).strip()
    return str(issue.get("key") or "").strip()


def main() -> int:
    settings = get_settings()
    project_key = settings.jira_project_key
    r = Report()

    r.print("=== Jira release inventory (account currently set in .env) ===")
    r.print(f"JIRA_BASE_URL:    {settings.jira_base_url or '(not set)'}")
    r.print(f"JIRA_PROJECT_KEY: {project_key or '(not set)'}")

    if not project_key:
        r.print("\nJIRA_PROJECT_KEY is not set - nothing to query.")
        _flush(settings, project_key or "UNSET", r, payload=None)
        return 1

    client = MCPJiraClient()

    try:
        issues = client.search(
            f'project = "{project_key}" ORDER BY key ASC',
            ["summary", "issuetype", "labels", "fixVersions", "key"],
        )
    except Exception as exc:
        r.print(f"\nJira search FAILED -> {type(exc).__name__}: {exc}")
        r.print(traceback.format_exc())
        _flush(settings, project_key, r, payload=None)
        return 1

    r.print(f"\nTotal issues fetched: {len(issues)}")

    counts: dict[str, int] = {}
    for issue in issues:
        name = _issue_type(issue) or "UNKNOWN"
        counts[name] = counts.get(name, 0) + 1

    r.print("\nIssue type breakdown:")
    for name in sorted(counts):
        r.print(f"  {name:<20} {counts[name]}")

    # --- What the pipeline would recognize as a "release" ---
    release_typed = [issue for issue in issues if _issue_type(issue).upper() == "RELEASE"]
    prefix_matched = [
        issue for issue in issues
        if issue not in release_typed and _work_item_id(issue).upper().startswith("REL-")
    ]

    fix_version_names: dict[str, list[str]] = {}
    for issue in issues:
        for version in _fix_versions(issue):
            fix_version_names.setdefault(version, []).append(str(issue.get("key") or ""))

    label_release_candidates: dict[str, list[str]] = {}
    for issue in issues:
        for label in _labels(issue):
            if label.upper().startswith("REL") or re.match(r"^\d+\.\d+$", label):
                label_release_candidates.setdefault(label, []).append(str(issue.get("key") or ""))

    r.print("\nIssues typed 'Release':")
    if release_typed:
        for issue in release_typed:
            r.print(f"  {issue.get('key', '')}: {_summary(issue)}")
    else:
        r.print("  (none)")

    r.print("\nIssues matched only via a '[REL-...]' summary tag or REL- key prefix:")
    if prefix_matched:
        for issue in prefix_matched:
            r.print(f"  {issue.get('key', '')}: {_summary(issue)}  (work_item_id={_work_item_id(issue)})")
    else:
        r.print("  (none)")

    r.print("\nFix Versions found on any issue:")
    if fix_version_names:
        for version, keys in sorted(fix_version_names.items()):
            r.print(f"  {version!r:<20} set on {len(keys)} issue(s): {', '.join(keys[:8])}{' ...' if len(keys) > 8 else ''}")
    else:
        r.print("  (none - no issue in this project has a Fix Version set)")

    r.print("\nLabels that look like a release identifier (e.g. 'REL-25.4', '25.4'):")
    if label_release_candidates:
        for label, keys in sorted(label_release_candidates.items()):
            r.print(f"  {label!r:<20} on {len(keys)} issue(s): {', '.join(keys[:8])}{' ...' if len(keys) > 8 else ''}")
    else:
        r.print("  (none)")

    # Mirrors _load_jira_source_data's actual resolution order exactly. A
    # release is considered to EXIST via, in order:
    #   1. an issue typed 'Release', or
    #   2. an issue whose work_item_id (from a '[REL-...]' summary tag, or
    #      else the raw issue key) starts with 'REL-', or
    #   3. (fallback, only if 1/2 found nothing) a Fix Version matching the
    #      requested id, scanned across ALL issues, or
    #   4. (fallback, only if 1/2/3 found nothing) a label matching the
    #      requested id exactly, scanned across ALL issues.
    resolvable_today = sorted(
        {issue.get("key") or "" for issue in release_typed}
        | {_work_item_id(issue) for issue in prefix_matched}
        | set(fix_version_names.keys())
        | set(label_release_candidates.keys())
    )

    r.print("\n=== Release identifiers this account currently supports ===")
    if resolvable_today:
        for value in resolvable_today:
            r.print(f"  {value}")
        r.print(
            "\nThese are the release IDs '_load_jira_source_data' can "
            "resolve today (via a Release-typed issue, REL- key/tag, Fix "
            "Version, or matching label). Query the pipeline with one of "
            "these values."
        )
    else:
        r.print(
            "  NONE. This project has no issue typed 'Release', no "
            "'[REL-...]' summary tag, no REL- prefixed key, no Fix Version, "
            "and no release-looking label on any issue. Every release query "
            "against this account will fail until one of those is added in "
            "Jira."
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "jira_base_url": settings.jira_base_url,
        "jira_project_key": project_key,
        "total_issues": len(issues),
        "issue_type_counts": counts,
        "resolvable_today": resolvable_today,
        "release_typed_issues": [
            {"key": issue.get("key"), "summary": _summary(issue)} for issue in release_typed
        ],
        "fix_versions": fix_version_names,
        "all_labels_seen": label_release_candidates,
        "raw_issues": issues,
    }
    _flush(settings, project_key, r, payload)
    return 0


def _flush(settings: Any, project_key: str, r: "Report", payload: dict[str, Any] | None) -> None:
    out_dir = Path(settings.output_dir) / "jira_release_inventory"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = out_dir / f"{project_key}_{stamp}"

    txt_path = base.with_suffix(".txt")
    txt_path.write_text(r.text(), encoding="utf-8")

    json_path = base.with_suffix(".json")
    if payload is not None:
        json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    print(f"\nSaved report to: {txt_path}")
    if payload is not None:
        print(f"Saved raw data to: {json_path}")


if __name__ == "__main__":
    raise SystemExit(main())
