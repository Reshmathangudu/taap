from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from app.config import get_settings
from app.prompts.loader import load_prompt
from app.agents.requirements_agent.models import RequirementAnalysis


class RequirementsConfigurationError(RuntimeError):
    pass


class RequirementsUpstreamError(RuntimeError):
    pass


def _text(value: Any) -> str:
    """Extract Jira plain text or ADF, preserving paragraph boundaries."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_text(item) for item in value)
    if isinstance(value, dict):
        kind = value.get("type")
        if kind == "hardBreak":
            return "\n"
        if kind == "mention":
            return str(value.get("attrs", {}).get("text", ""))
        text = str(value.get("text", "")) + _text(value.get("content"))
        if kind in {"paragraph", "heading", "listItem", "tableRow"}:
            text += "\n"
        return text
    return str(value)


def _normalize_issue(issue: dict[str, Any], settings: Any) -> dict[str, Any]:
    fields = issue.get("fields") or {}
    key = issue["key"]
    links = []
    for link in fields.get("issuelinks") or []:
        for direction in ("inward", "outward"):
            target = link.get(f"{direction}Issue")
            if target:
                links.append({
                    "key": target.get("key"),
                    "relationship": (link.get("type") or {}).get(direction, "unknown"),
                    "summary": (target.get("fields") or {}).get("summary", ""),
                })
    return {
        "key": key,
        "url": f"{settings.jira_base_url.rstrip('/')}/browse/{key}",
        "summary": fields.get("summary", ""),
        "description": _text(fields.get("description")).strip(),
        "acceptance_criteria": _text(fields.get(settings.jira_acceptance_criteria_field)).strip(),
        "acceptance_criteria_field_configured": bool(settings.jira_acceptance_criteria_field),
        "issue_type": (fields.get("issuetype") or {}).get("name", ""),
        "status": (fields.get("status") or {}).get("name", ""),
        "priority": (fields.get("priority") or {}).get("name", ""),
        "components": [item.get("name", "") for item in fields.get("components") or []],
        "labels": fields.get("labels") or [],
        "parent": (fields.get("parent") or {}).get("key"),
        "links": links,
        "attachments": [{"filename": item.get("filename"), "mime_type": item.get("mimeType")}
                        for item in fields.get("attachment") or []],
        "updated": fields.get("updated"),
    }


def fetch_jira_requirements(issue_keys: list[str] | None = None) -> dict[str, Any]:
    """Read explicit issue keys, or configured project Epic/Story issues. Never writes Jira."""
    settings = get_settings()
    for name in ("jira_base_url", "jira_email", "jira_api_token", "jira_project_key"):
        if not getattr(settings, name):
            raise RequirementsConfigurationError(f"{name.upper()} is required.")
    parsed = urlsplit(settings.jira_base_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RequirementsConfigurationError("JIRA_BASE_URL must be an HTTPS base URL without credentials, query, or fragment.")
    project = settings.jira_project_key.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", project):
        raise RequirementsConfigurationError("JIRA_PROJECT_KEY is invalid.")
    keys = list(dict.fromkeys(key.strip().upper() for key in (issue_keys or [])))
    if len(keys) > settings.requirements_max_issues:
        raise ValueError("Too many requirements; submit a smaller group of issue keys.")
    if any(not re.fullmatch(re.escape(project) + r"-\d+", key) for key in keys):
        raise ValueError("Issue keys must belong to the configured Jira project.")
    types = [settings.jira_epic_issue_type, settings.jira_story_issue_type]
    jql = f"project = {json.dumps(project)}"
    if keys:
        jql += " AND key in (" + ",".join(json.dumps(key) for key in keys) + ")"
    else:
        jql += " AND issuetype in (" + ",".join(json.dumps(kind) for kind in types) + ")"
    jql += " ORDER BY key ASC"
    fields = ["summary", "description", "issuetype", "status", "priority", "components",
              "labels", "parent", "issuelinks", "attachment", "updated"]
    if settings.jira_acceptance_criteria_field:
        fields.append(settings.jira_acceptance_criteria_field)
    from app.integrations.mcp_jira_client import MCPJiraClient
    try:
        issues = MCPJiraClient().search(jql, fields)
    except Exception:
        # Transport exceptions can contain remote response bodies; do not expose those.
        raise RequirementsUpstreamError("Jira requirements fetch failed. Check connectivity, credentials, permissions, and pagination limits.") from None
    if len(issues) > settings.requirements_max_issues:
        raise ValueError("Project scope exceeds REQUIREMENTS_MAX_ISSUES; provide explicit issue_keys.")
    returned = {issue.get("key") for issue in issues}
    if keys and set(keys) - returned:
        raise ValueError("Requested Jira issues were not returned: " + ", ".join(sorted(set(keys) - returned)))
    if keys and returned - set(keys):
        raise RequirementsUpstreamError("Jira returned issues outside the requested issue keys.")
    if any(not isinstance(key, str) or not re.fullmatch(re.escape(project) + r"-\d+", key) for key in returned):
        raise RequirementsUpstreamError("Jira returned an issue outside the requested project.")
    return {
        "project_key": project,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "requirements": [_normalize_issue(issue, settings) for issue in issues],
        "limitations": [
            "Attachments and screenshots are metadata only; their contents were not read.",
            "Linked issues are references, not a complete upstream/downstream system inventory.",
            "Confluence pages and Jira comments are not fetched; supply relevant text as walkthrough_notes.",
        ],
    }


def _analysis_input(source: dict[str, Any], walkthrough_notes: str) -> str:
    content = json.dumps({"jira_requirement": source, "walkthrough_notes": walkthrough_notes}, ensure_ascii=False)
    if len(content) > get_settings().requirements_max_input_chars:
        raise ValueError("Requirement and walkthrough notes exceed REQUIREMENTS_MAX_INPUT_CHARS; narrow the input.")
    return content


def _generate_analysis(source: dict[str, Any], walkthrough_notes: str) -> RequirementAnalysis:
    settings = get_settings()
    content = _analysis_input(source, walkthrough_notes)
    if not settings.openai_api_key:
        raise RequirementsConfigurationError("OPENAI_API_KEY is required for requirements analysis.")
    from litellm import completion
    instruction = load_prompt("requirements_analysis.md")
    instruction += "\nReturn a JSON object matching this schema exactly:\n" + json.dumps(RequirementAnalysis.model_json_schema())
    try:
        response = completion(
            model=settings.llm_model,
            api_key=settings.openai_api_key,
            messages=[{"role": "system", "content": instruction}, {"role": "user", "content": content}],
            response_format={"type": "json_object"},
            max_completion_tokens=settings.requirements_max_tokens,
            timeout=settings.llm_timeout_seconds,
        )
        if response.choices[0].finish_reason != "stop":
            raise ValueError("Incomplete model response")
        return RequirementAnalysis.model_validate_json(response.choices[0].message.content)
    except Exception:
        raise RequirementsUpstreamError("Requirements analysis failed or returned an incomplete/invalid report. Retry with a smaller requirement or check model configuration.") from None


def analyze_jira_requirements(
    issue_keys: list[str] | None = None,
    walkthrough_notes: str = "",
) -> dict[str, Any]:
    """Fetch Jira requirements and create validated testing drafts plus local traceability."""
    snapshot = fetch_jira_requirements(issue_keys)
    # Validate the complete batch before spending model calls on any requirement.
    for source in snapshot["requirements"]:
        _analysis_input(source, walkthrough_notes)
    reports = []
    for source in snapshot["requirements"]:
        analysis = _generate_analysis(source, walkthrough_notes)
        report = analysis.model_dump()
        mappings = []
        for index, case in enumerate(report["test_cases"], start=1):
            # IDs and mapping targets come from trusted code, never model-generated issue keys.
            case["id"] = f"{source['key']}-TC-{index:03d}"
            mappings.append({
                "requirement_key": source["key"],
                "requirement_url": source["url"],
                "test_case_id": case["id"],
                "acceptance_criteria": case["acceptance_criteria"],
                "jira_xray_test_key": None,
                "publication_status": "draft_not_published",
            })
        reports.append({"source": source, "analysis": report, "traceability": mappings,
                        "estimate_review_owner": "QE Lead / Test Manager"})
    return {
        "status": "draft" if reports else "no_requirements",
        "project_key": snapshot["project_key"],
        "fetched_at": snapshot["fetched_at"],
        "requirements": reports,
        "limitations": snapshot["limitations"] + [
            "Manual tests and automation outlines are reviewable drafts; generated automation has not been executed.",
            "Estimates require QE Lead/Test Manager review. No Jira/Xray issues or links have been created.",
        ],
    }
