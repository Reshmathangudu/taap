from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse


_PROJECT_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9_]*)-\d+\b", re.IGNORECASE)
_RELEASE_ID_RE = re.compile(r"\bREL-[A-Z0-9._-]+\b", re.IGNORECASE)
_JQL_LABEL_RE = re.compile(
    r"""labels?\s*(?:=|IN\s*\()\s*["']?([A-Z0-9._-]+)["']?""",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class JiraLinkContext:
    """Small normalized view of a Jira URL used by the orchestrator."""

    raw_url: str
    base_url: str = ""
    project_key: str = ""
    issue_key: str = ""
    release_label: str = ""
    jql: str = ""


def parse_jira_link(jira_link: str | None) -> JiraLinkContext:
    """
    Parse the Jira links accepted by the Risk Tier orchestrator.

    Supported examples include:
      - https://site.atlassian.net/browse/SCRUM-94
      - https://site.atlassian.net/jira/software/projects/SCRUM/boards/1
      - https://site.atlassian.net/issues/?jql=project%20%3D%20SCRUM
      - Jira issue/search links whose JQL or URL contains REL-25.4

    The current Master Orchestrator consumes `project_key` and
    `release_label`; the other fields are retained for diagnostics and future
    use.
    """
    raw = str(jira_link or "").strip()
    if not raw:
        return JiraLinkContext(raw_url="")

    # Accept a bare Jira issue key as a convenience.
    if "://" not in raw:
        issue_match = _PROJECT_KEY_RE.search(raw)
        release_match = _RELEASE_ID_RE.search(raw)
        issue_key = issue_match.group(0).upper() if issue_match else ""
        project_key = (
            issue_key.rsplit("-", 1)[0]
            if issue_key
            else ""
        )
        return JiraLinkContext(
            raw_url=raw,
            project_key=project_key,
            issue_key=issue_key,
            release_label=(
                release_match.group(0).upper()
                if release_match
                else ""
            ),
        )

    parsed = urlparse(raw)
    base_url = (
        f"{parsed.scheme}://{parsed.netloc}"
        if parsed.scheme and parsed.netloc
        else ""
    )

    path = unquote(parsed.path or "")
    query = parse_qs(parsed.query or "", keep_blank_values=True)

    # Jira may put JQL in either `jql` or occasionally another encoded query
    # parameter. Prefer the explicit jql parameter.
    jql_values = query.get("jql") or query.get("JQL") or []
    jql = unquote(str(jql_values[0])) if jql_values else ""

    issue_key = ""
    project_key = ""

    # /browse/SCRUM-94 and similar issue URLs.
    issue_match = _PROJECT_KEY_RE.search(path)
    if issue_match:
        issue_key = issue_match.group(0).upper()
        project_key = issue_key.rsplit("-", 1)[0]

    # /projects/SCRUM/... and /jira/software/projects/SCRUM/...
    if not project_key:
        project_match = re.search(
            r"/projects?/([A-Z][A-Z0-9_]*)\b",
            path,
            re.IGNORECASE,
        )
        if project_match:
            project_key = project_match.group(1).upper()

    # Project key may be present only in JQL.
    if not project_key and jql:
        project_jql_match = re.search(
            r"""\bproject\s*=\s*["']?([A-Z][A-Z0-9_]*)["']?""",
            jql,
            re.IGNORECASE,
        )
        if project_jql_match:
            project_key = project_jql_match.group(1).upper()

    # Some Jira URLs use projectKey=SCRUM.
    if not project_key:
        for key in ("projectKey", "project", "project_key"):
            values = query.get(key) or []
            if not values:
                continue
            candidate = str(values[0]).strip().upper()
            if re.fullmatch(r"[A-Z][A-Z0-9_]*", candidate):
                project_key = candidate
                break

    release_label = ""

    # First prefer an explicit labels clause in JQL.
    if jql:
        label_match = _JQL_LABEL_RE.search(jql)
        if label_match:
            candidate = label_match.group(1).strip()
            if _RELEASE_ID_RE.fullmatch(candidate):
                release_label = candidate.upper()

        if not release_label:
            release_match = _RELEASE_ID_RE.search(jql)
            if release_match:
                release_label = release_match.group(0).upper()

    # Fall back to any REL-* token present in the URL itself.
    if not release_label:
        release_match = _RELEASE_ID_RE.search(unquote(raw))
        if release_match:
            release_label = release_match.group(0).upper()

    return JiraLinkContext(
        raw_url=raw,
        base_url=base_url,
        project_key=project_key,
        issue_key=issue_key,
        release_label=release_label,
        jql=jql,
    )