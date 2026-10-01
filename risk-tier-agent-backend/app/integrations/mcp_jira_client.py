from __future__ import annotations

import asyncio
import json
import threading
import os
import sys
from pathlib import Path
from typing import Any

from app.config import get_settings

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client


def _project_venv_python(project_root: Path) -> str:
    """
    Return this project's own .venv interpreter, if one exists.

    sys.executable is whatever interpreter is running the *current*
    process (e.g. the ADK web server / uvicorn). That process is not
    guaranteed to have been launched from this project's own virtualenv —
    if it was started under a different (possibly stale or incompatible)
    environment, sys.executable would spawn the Jira MCP child process
    with that wrong interpreter too, even though jira_server.py itself now
    always resolves to this project's file. Preferring the project's own
    .venv here makes the child spawn correct regardless of which
    interpreter is running the parent process.
    """
    venv_dir = project_root / ".venv"

    candidates = (
        venv_dir / "Scripts" / "python.exe",
        venv_dir / "bin" / "python",
        venv_dir / "bin" / "python3",
    )

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return ""


class MCPJiraClient:
    """
    Thin adapter used by the Master Orchestrator.

    Public interface:
    - ping()
    - list_fields()
    - search(jql, fields)
    - get_issue(issue_key, fields)
    - create_issue(project_key, summary, description, issue_type)
    - add_comment(issue_key, comment)
    - update_issue(issue_key, summary, description, priority)
    - delete_issue(issue_key, confirm)

    search() transparently follows Jira enhanced-search pagination so callers
    receive all matching issues rather than only the first page.
    """

    def __init__(
        self,
        transport: str | None = None,
        server_url: str | None = None,
        server_script: str | Path | None = None,
        python_executable: str | None = None,
        page_size: int | None = None,
        max_pages: int | None = None,
    ) -> None:
        self.transport = (
            transport
            or os.getenv("JIRA_MCP_TRANSPORT", "stdio")
        ).strip().lower()

        self.settings = get_settings()

        self.server_url = (
            server_url
            or os.getenv("JIRA_MCP_URL", "").strip()
            or ""
        )

        # app/integrations/mcp_jira_client.py -> parents[0]=app/integrations,
        # parents[1]=app, parents[2]=project root.
        project_root = Path(__file__).resolve().parents[2]

        default_server_script = (
            project_root / "app" / "mcp" / "jira_server.py"
        )

        configured_server_script = (
            server_script
            or self.settings.jira_mcp_server_script
        )

        if configured_server_script:
            candidate = Path(configured_server_script)
            # A relative JIRA_MCP_SERVER_SCRIPT must not be resolved against
            # the spawning process's current working directory — that is
            # whatever directory the server happened to be launched from,
            # which is not guaranteed to be this project's root and can
            # silently pick up an unrelated jira_server.py (and venv) from
            # another folder on disk. Always anchor it to this project.
            self.server_script = (
                candidate
                if candidate.is_absolute()
                else (project_root / candidate)
            )
        else:
            self.server_script = default_server_script

        self.python_executable = (
            python_executable
            or os.getenv("JIRA_MCP_PYTHON", "").strip()
            or _project_venv_python(project_root)
            or sys.executable
        )

        configured_page_size = str(page_size if page_size is not None else self.settings.jira_mcp_page_size)

        try:
            self.page_size = max(
                1,
                min(100, int(configured_page_size)),
            )
        except ValueError:
            self.page_size = 100

        configured_max_pages = str(max_pages if max_pages is not None else self.settings.jira_mcp_max_pages)

        try:
            self.max_pages = max(
                1,
                int(configured_max_pages),
            )
        except ValueError:
            self.max_pages = 1000

    def ping(self) -> Any:
        return self._call_tool("ping", {})

    def list_fields(self) -> list[dict[str, Any]]:
        result = self._call_tool("list_fields", {})

        return _extract_dict_list(
            result,
            preferred_keys=(
                "fields",
                "result",
                "data",
                "payload",
                "items",
                "values",
            ),
        )

    def search(
        self,
        jql: str,
        fields: list[str],
    ) -> list[dict[str, Any]]:
        """
        Return all issues matching the JQL by following nextPageToken.
        """
        normalized_jql = str(jql or "").strip()
        if not normalized_jql:
            return []

        normalized_fields = list(
            dict.fromkeys(
                str(field).strip()
                for field in fields
                if str(field).strip()
            )
        )

        all_issues: list[dict[str, Any]] = []
        next_page_token: str | None = None
        seen_tokens: set[str] = set()

        for _page_number in range(1, self.max_pages + 1):
            arguments: dict[str, Any] = {
                "jql": normalized_jql,
                "fields": normalized_fields,
                "max_results": self.page_size,
            }

            if next_page_token:
                arguments["next_page_token"] = next_page_token

            result = self._call_tool(
                "search_issues",
                arguments,
            )

            page_issues = _extract_dict_list(
                result,
                preferred_keys=(
                    "issues",
                    "result",
                    "data",
                    "payload",
                    "items",
                    "values",
                ),
            )

            all_issues.extend(page_issues)

            page_token = _extract_next_page_token(result)

            is_last = _extract_is_last(result)

            if is_last:
                break
            if not page_token:
                raise RuntimeError("Jira MCP returned an incomplete page without a nextPageToken.")

            if page_token in seen_tokens:
                raise RuntimeError(
                    "Jira MCP pagination returned the same "
                    "nextPageToken twice."
                )

            seen_tokens.add(page_token)
            next_page_token = page_token
        else:
            raise RuntimeError(
                f"Jira MCP search exceeded the maximum page limit "
                f"({self.max_pages}) for JQL: {normalized_jql}"
            )

        return _deduplicate_issues(all_issues)

    def get_issue(
        self,
        issue_key: str,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_issue_key = str(issue_key or "").strip()

        if not normalized_issue_key:
            raise ValueError("issue_key is required.")

        result = self._call_tool(
            "get_issue",
            {
                "issue_key": normalized_issue_key,
                "fields": fields or [],
            },
        )

        if isinstance(result, dict):
            return result

        return {}

    def create_issue(
        self,
        project_key: str,
        summary: str,
        description: str = "",
        issue_type: str = "Task",
    ) -> dict[str, Any]:
        normalized_project_key = str(project_key or "").strip()
        normalized_summary = str(summary or "").strip()

        if not normalized_project_key:
            raise ValueError("project_key is required.")
        if not normalized_summary:
            raise ValueError("summary is required.")

        result = self._call_tool(
            "create_issue",
            {
                "project_key": normalized_project_key,
                "summary": normalized_summary,
                "description": str(description or ""),
                "issue_type": str(issue_type or "Task").strip() or "Task",
            },
        )

        return result if isinstance(result, dict) else {}

    def add_comment(
        self,
        issue_key: str,
        comment: str,
    ) -> dict[str, Any]:
        normalized_issue_key = str(issue_key or "").strip()
        normalized_comment = str(comment or "").strip()

        if not normalized_issue_key:
            raise ValueError("issue_key is required.")
        if not normalized_comment:
            raise ValueError("comment is required.")

        result = self._call_tool(
            "add_comment",
            {
                "issue_key": normalized_issue_key,
                "comment": normalized_comment,
            },
        )

        return result if isinstance(result, dict) else {}

    def update_issue(
        self,
        issue_key: str,
        summary: str | None = None,
        description: str | None = None,
        priority: str | None = None,
    ) -> dict[str, Any]:
        normalized_issue_key = str(issue_key or "").strip()

        if not normalized_issue_key:
            raise ValueError("issue_key is required.")

        result = self._call_tool(
            "update_issue",
            {
                "issue_key": normalized_issue_key,
                "summary": summary,
                "description": description,
                "priority": priority,
            },
        )

        return result if isinstance(result, dict) else {}

    def delete_issue(
        self,
        issue_key: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        normalized_issue_key = str(issue_key or "").strip()

        if not normalized_issue_key:
            raise ValueError("issue_key is required.")

        result = self._call_tool(
            "delete_issue",
            {
                "issue_key": normalized_issue_key,
                "confirm": bool(confirm),
            },
        )

        return result if isinstance(result, dict) else {}

    def _call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        async def _runner() -> Any:
            if self.server_url:
                async with streamable_http_client(
                    self.server_url
                ) as (
                    read_stream,
                    write_stream,
                    _,
                ):
                    async with ClientSession(
                        read_stream,
                        write_stream,
                    ) as session:
                        await session.initialize()
                        result = await session.call_tool(
                            tool_name,
                            arguments,
                        )
                        return _normalize_mcp_result(result)

            mcp_env = os.environ.copy()

            # The application settings are the authoritative source for Jira
            # configuration. Forward them explicitly to the child MCP server
            # process instead of relying on the child process to load .env.
            jira_base_url = getattr(self.settings, "jira_base_url", None)
            jira_email = getattr(self.settings, "jira_email", None)
            jira_api_token = getattr(self.settings, "jira_api_token", None)

            if jira_base_url:
                mcp_env["JIRA_BASE_URL"] = str(jira_base_url).strip()
            if jira_email:
                mcp_env["JIRA_EMAIL"] = str(jira_email).strip()
            if jira_api_token:
                mcp_env["JIRA_API_TOKEN"] = str(jira_api_token).strip()

            server_params = StdioServerParameters(
                command=self.python_executable,
                args=[str(self.server_script)],
                env=mcp_env,
            )

            async with stdio_client(
                server_params
            ) as (
                read_stream,
                write_stream,
            ):
                async with ClientSession(
                    read_stream,
                    write_stream,
                ) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        tool_name,
                        arguments,
                    )
                    return _normalize_mcp_result(result)

        return _run_async_safely(_runner)


def _run_async_safely(async_callable):
    """
    Run an async callable from both normal synchronous code and an already
    running asyncio event loop (for example ADK Web / FastAPI).

    The MCP client API exposed to the orchestrator is synchronous, so when
    called from inside an active event loop we execute the coroutine in a
    dedicated worker thread with its own event loop instead of calling
    asyncio.run() in the active loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(async_callable())

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _worker() -> None:
        try:
            result["value"] = asyncio.run(async_callable())
        except BaseException as exc:  # re-raise original exception in caller
            error["value"] = exc

    thread = threading.Thread(
        target=_worker,
        name="mcp-jira-async-worker",
        daemon=True,
    )
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]

    return result.get("value")


def _normalize_mcp_result(result: Any) -> Any:
    """
    Convert MCP tool output into plain Python data.
    """
    structured = getattr(
        result,
        "structuredContent",
        None,
    )

    if structured is None:
        structured = getattr(
            result,
            "structured_content",
            None,
        )

    if structured is not None:
        return _unwrap_payload(structured)

    content = getattr(
        result,
        "content",
        None,
    )

    if isinstance(content, list):
        for item in content:
            text = getattr(
                item,
                "text",
                None,
            )

            if not text:
                continue

            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return text

            return _unwrap_payload(parsed)

    return result


def _unwrap_payload(payload: Any) -> Any:
    """
    Unwrap common MCP/FastMCP wrapper shapes.
    """
    if not isinstance(payload, dict):
        return payload

    # Only unwrap a single-key wrapper. Do not unwrap a real search result
    # containing issues + pagination metadata.
    if len(payload) == 1:
        for key in ("result", "data", "payload"):
            if key in payload:
                return payload[key]

    return payload


def _extract_dict_list(
    payload: Any,
    *,
    preferred_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    """
    Extract a list of dictionaries from common MCP/FastMCP response shapes.

    Some MCP responses wrap the actual list under implementation-specific
    keys. Prefer known keys first, then recursively inspect nested dict/list
    values so Jira field metadata cannot silently become an empty list.
    """
    if isinstance(payload, list):
        return [
            item
            for item in payload
            if isinstance(item, dict)
        ]

    if not isinstance(payload, dict):
        return []

    for key in preferred_keys:
        if key not in payload:
            continue

        value = payload[key]

        if isinstance(value, list):
            items = [
                item
                for item in value
                if isinstance(item, dict)
            ]
            if items:
                return items

        if isinstance(value, dict):
            nested = _extract_dict_list(
                value,
                preferred_keys=preferred_keys,
            )
            if nested:
                return nested

    # Final recursive fallback for wrappers such as:
    # {"structuredContent": {"content": [{"text": "[...]"}]}}
    for value in payload.values():
        if isinstance(value, (dict, list)):
            nested = _extract_dict_list(
                value,
                preferred_keys=preferred_keys,
            )
            if nested:
                return nested

    return []


def _extract_next_page_token(
    payload: Any,
) -> str | None:
    if not isinstance(payload, dict):
        return None

    token = payload.get("nextPageToken")

    if token is None:
        token = payload.get("next_page_token")

    if token is None:
        for wrapper_key in (
            "result",
            "data",
            "payload",
        ):
            nested = payload.get(wrapper_key)

            if isinstance(nested, dict):
                token = nested.get(
                    "nextPageToken"
                ) or nested.get(
                    "next_page_token"
                )

                if token:
                    break

    token = str(token).strip() if token else ""

    return token or None


def _extract_is_last(
    payload: Any,
) -> bool:
    if not isinstance(payload, dict):
        return True

    value = payload.get("isLast")

    if value is None:
        value = payload.get("is_last")

    if value is None:
        for wrapper_key in (
            "result",
            "data",
            "payload",
        ):
            nested = payload.get(wrapper_key)

            if isinstance(nested, dict):
                value = nested.get("isLast")

                if value is None:
                    value = nested.get("is_last")

                if value is not None:
                    break

    if isinstance(value, bool):
        return value

    if value is None:
        return True

    return str(value).strip().lower() in {
        "true",
        "1",
        "yes",
        "y",
    }


def _deduplicate_issues(
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Remove accidental duplicate pages while preserving Jira order.
    """
    seen: set[str] = set()
    deduplicated: list[dict[str, Any]] = []

    for issue in issues:
        issue_key = str(
            issue.get("key")
            or issue.get("id")
            or ""
        ).strip()

        if issue_key:
            if issue_key in seen:
                continue
            seen.add(issue_key)

        deduplicated.append(issue)

    return deduplicated
