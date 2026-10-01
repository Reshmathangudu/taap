# from __future__ import annotations

# import base64
# import os
# from contextlib import asynccontextmanager
# from pathlib import Path
# from typing import Any

# import truststore

# # Use the Windows / enterprise certificate store before httpx opens HTTPS connections.
# truststore.inject_into_ssl()

# import httpx
# from dotenv import load_dotenv
# from mcp.server.fastmcp import FastMCP

# # Load project .env.
# load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# mcp = FastMCP("jira-mcp", json_response=True)


# def _required_env(name: str) -> str:
#     value = os.getenv(name, "").strip()
#     if not value:
#         raise RuntimeError(f"{name} is required for the Jira MCP server.")
#     return value


# def _jira_base_url() -> str:
#     return _required_env("JIRA_BASE_URL").rstrip("/")


# def _jira_headers() -> dict[str, str]:
#     email = _required_env("JIRA_EMAIL")
#     api_token = _required_env("JIRA_API_TOKEN")

#     token = base64.b64encode(
#         f"{email}:{api_token}".encode("utf-8")
#     ).decode("ascii")

#     return {
#         "Authorization": f"Basic {token}",
#         "Accept": "application/json",
#         "Content-Type": "application/json",
#     }


# @asynccontextmanager
# async def _jira_http_client():
#     async with httpx.AsyncClient(
#         base_url=_jira_base_url(),
#         headers=_jira_headers(),
#         timeout=60.0,
#     ) as client:
#         yield client


# async def _request_json(
#     method: str,
#     path: str,
#     *,
#     params: dict[str, Any] | None = None,
#     json_body: dict[str, Any] | None = None,
# ) -> Any:
#     async with _jira_http_client() as client:
#         response = await client.request(
#             method=method,
#             url=path,
#             params=params,
#             json=json_body,
#         )

#     if response.status_code >= 400:
#         raise RuntimeError(
#             f"Jira API {method} {path} failed "
#             f"with {response.status_code}: {response.text}"
#         )

#     return response.json()


# @mcp.tool()
# async def ping() -> dict[str, Any]:
#     """Verify that the MCP server can see the required Jira credentials."""
#     return {
#         "ok": True,
#         "base_url_set": bool(os.getenv("JIRA_BASE_URL")),
#         "email_set": bool(os.getenv("JIRA_EMAIL")),
#         "token_set": bool(os.getenv("JIRA_API_TOKEN")),
#     }


# @mcp.tool()
# async def list_fields() -> list[dict[str, Any]]:
#     """Return Jira fields in a compact normalized form."""
#     fields = await _request_json("GET", "/rest/api/3/field")

#     if not isinstance(fields, list):
#         return []

#     normalized: list[dict[str, Any]] = []

#     for field in fields:
#         if not isinstance(field, dict):
#             continue

#         normalized.append(
#             {
#                 "id": field.get("id", ""),
#                 "key": field.get("key", ""),
#                 "name": field.get("name", ""),
#                 "clauseNames": field.get("clauseNames", []),
#                 "custom": field.get("custom", False),
#                 "schema": field.get("schema", {}),
#             }
#         )

#     return normalized


# @mcp.tool()
# async def search_issues(
#     jql: str,
#     fields: list[str],
#     max_results: int = 100,
#     next_page_token: str | None = None,
# ) -> dict[str, Any]:
#     """
#     Execute one page of Jira enhanced JQL search.

#     Pagination is intentionally handled by the MCP client.
#     """
#     if max_results <= 0:
#         raise ValueError("max_results must be greater than zero.")

#     max_results = min(max_results, 100)

#     payload: dict[str, Any] = {
#         "jql": str(jql or "").strip(),
#         "fields": list(
#             dict.fromkeys(
#                 str(field).strip()
#                 for field in (fields or [])
#                 if str(field).strip()
#             )
#         ),
#         "maxResults": max_results,
#     }

#     if next_page_token:
#         payload["nextPageToken"] = next_page_token

#     data = await _request_json(
#         "POST",
#         "/rest/api/3/search/jql",
#         json_body=payload,
#     )

#     issues = data.get("issues", [])
#     if not isinstance(issues, list):
#         issues = []

#     return {
#         "issues": issues,
#         "total": data.get("total", len(issues)),
#         "maxResults": data.get("maxResults", max_results),
#         "nextPageToken": data.get("nextPageToken"),
#         "isLast": data.get(
#             "isLast",
#             not bool(data.get("nextPageToken")),
#         ),
#     }


# @mcp.tool()
# async def get_issue(
#     issue_key: str,
#     fields: list[str] | None = None,
# ) -> dict[str, Any]:
#     """Return one Jira issue with the requested fields."""
#     normalized_issue_key = str(issue_key or "").strip()

#     if not normalized_issue_key:
#         raise ValueError("issue_key is required.")

#     params: dict[str, Any] = {}

#     if fields:
#         params["fields"] = ",".join(
#             dict.fromkeys(
#                 str(field).strip()
#                 for field in fields
#                 if str(field).strip()
#             )
#         )

#     result = await _request_json(
#         "GET",
#         f"/rest/api/3/issue/{normalized_issue_key}",
#         params=params,
#     )

#     return result if isinstance(result, dict) else {}


# def main() -> None:
#     transport = os.getenv(
#         "JIRA_MCP_TRANSPORT",
#         "stdio",
#     ).strip().lower()

#     if transport in {
#         "streamable-http",
#         "streamable_http",
#         "http",
#     }:
#         mcp.run(transport="streamable-http")
#     else:
#         mcp.run()


# if __name__ == "__main__":
#     main()



#jira_server.py 
from __future__ import annotations

import base64
import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
import truststore
from mcp.server.fastmcp import FastMCP

# Use the Windows / enterprise certificate store before httpx opens HTTPS
# connections.
truststore.inject_into_ssl()


mcp = FastMCP(
    "jira-mcp",
    json_response=True,
)


# ---------------------------------------------------------------------------
# Runtime configuration
# ---------------------------------------------------------------------------
#
# IMPORTANT:
# This MCP server does NOT load a .env file.
#
# Jira configuration must be supplied by the process that launches/connects
# to this MCP server (for example, the Google ADK MCP client/runtime).
#
# Required runtime environment variables:
#
#   JIRA_BASE_URL
#   JIRA_EMAIL
#   JIRA_API_TOKEN
#
# The server only reads these values at request/runtime time.
# ---------------------------------------------------------------------------


def _required_runtime_env(name: str) -> str:
    """
    Read a required runtime-provided environment variable.

    The MCP server does not load .env files and does not manage credentials.
    The parent/runtime process is responsible for supplying these values.
    """
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(
            f"{name} was not supplied by the MCP client/runtime."
        )

    return value


def _jira_base_url() -> str:
    """
    Return the runtime-provided Jira base URL.
    """
    return _required_runtime_env(
        "JIRA_BASE_URL"
    ).rstrip("/")


def _jira_headers() -> dict[str, str]:
    """
    Build Jira authentication headers from runtime-provided credentials.

    Credentials are never exposed as MCP tool arguments.
    """
    email = _required_runtime_env(
        "JIRA_EMAIL"
    )

    api_token = _required_runtime_env(
        "JIRA_API_TOKEN"
    )

    credentials = (
        f"{email}:{api_token}"
    ).encode("utf-8")

    encoded_credentials = (
        base64.b64encode(
            credentials
        ).decode("ascii")
    )

    return {
        "Authorization": (
            f"Basic {encoded_credentials}"
        ),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


@asynccontextmanager
async def _jira_http_client():
    """
    Create an authenticated Jira HTTP client.

    The credentials come from the runtime environment supplied by the
    MCP client / ADK host.
    """
    async with httpx.AsyncClient(
        base_url=_jira_base_url(),
        headers=_jira_headers(),
        timeout=60.0,
    ) as client:
        yield client


async def _request_json(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    """
    Execute one Jira REST API request and return JSON.

    Jira authentication is handled internally by the runtime-provided
    credentials.
    """
    async with _jira_http_client() as client:
        response = await client.request(
            method=method,
            url=path,
            params=params,
            json=json_body,
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Jira API {method} {path} failed "
            f"with {response.status_code}: {response.text}"
        )

    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Jira API {method} {path} returned "
            "a non-JSON response."
        ) from exc


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def ping() -> dict[str, Any]:
    """
    Verify that the MCP server can see Jira runtime configuration.

    This does NOT return credential values.
    """
    base_url = os.getenv(
        "JIRA_BASE_URL",
        "",
    ).strip()

    email = os.getenv(
        "JIRA_EMAIL",
        "",
    ).strip()

    api_token = os.getenv(
        "JIRA_API_TOKEN",
        "",
    ).strip()

    return {
        "ok": bool(
            base_url
            and email
            and api_token
        ),
        "base_url_set": bool(base_url),
        "email_set": bool(email),
        "token_set": bool(api_token),
        "credential_source": "MCP client runtime",
    }


@mcp.tool()
async def list_fields() -> list[dict[str, Any]]:
    """
    Return Jira fields in a compact normalized form.
    """
    fields = await _request_json(
        "GET",
        "/rest/api/3/field",
    )

    if not isinstance(fields, list):
        return []

    normalized: list[dict[str, Any]] = []

    for field in fields:
        if not isinstance(
            field,
            dict,
        ):
            continue

        normalized.append(
            {
                "id": field.get(
                    "id",
                    "",
                ),
                "key": field.get(
                    "key",
                    "",
                ),
                "name": field.get(
                    "name",
                    "",
                ),
                "clauseNames": field.get(
                    "clauseNames",
                    [],
                ),
                "custom": field.get(
                    "custom",
                    False,
                ),
                "schema": field.get(
                    "schema",
                    {},
                ),
            }
        )

    return normalized


@mcp.tool()
async def search_issues(
    jql: str,
    fields: list[str],
    max_results: int = 100,
    next_page_token: str | None = None,
) -> dict[str, Any]:
    """
    Execute one page of Jira enhanced JQL search.

    Pagination is intentionally handled by the MCP client.
    """
    if max_results <= 0:
        raise ValueError(
            "max_results must be greater than zero."
        )

    max_results = min(
        max_results,
        100,
    )

    normalized_fields = list(
        dict.fromkeys(
            str(field).strip()
            for field in (
                fields or []
            )
            if str(field).strip()
        )
    )

    payload: dict[str, Any] = {
        "jql": str(
            jql or ""
        ).strip(),
        "fields": normalized_fields,
        "maxResults": max_results,
    }

    if next_page_token:
        payload["nextPageToken"] = (
            next_page_token
        )

    data = await _request_json(
        "POST",
        "/rest/api/3/search/jql",
        json_body=payload,
    )

    if not isinstance(
        data,
        dict,
    ):
        return {
            "issues": [],
            "total": 0,
            "maxResults": max_results,
            "nextPageToken": None,
            "isLast": True,
        }

    issues = data.get(
        "issues",
        [],
    )

    if not isinstance(
        issues,
        list,
    ):
        issues = []

    return {
        "issues": issues,
        "total": data.get(
            "total",
            len(issues),
        ),
        "maxResults": data.get(
            "maxResults",
            max_results,
        ),
        "nextPageToken": data.get(
            "nextPageToken"
        ),
        "isLast": data.get(
            "isLast",
            not bool(
                data.get(
                    "nextPageToken"
                )
            ),
        ),
    }


@mcp.tool()
async def get_issue(
    issue_key: str,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """
    Return one Jira issue with the requested fields.
    """
    normalized_issue_key = str(
        issue_key or ""
    ).strip()

    if not normalized_issue_key:
        raise ValueError(
            "issue_key is required."
        )

    params: dict[str, Any] = {}

    if fields:
        normalized_fields = list(
            dict.fromkeys(
                str(field).strip()
                for field in fields
                if str(field).strip()
            )
        )

        if normalized_fields:
            params["fields"] = ",".join(
                normalized_fields
            )

    result = await _request_json(
        "GET",
        f"/rest/api/3/issue/{normalized_issue_key}",
        params=params,
    )

    return (
        result
        if isinstance(
            result,
            dict,
        )
        else {}
    )


def _adf_description(text: str | None) -> dict[str, Any]:
    """
    Wrap plain text in the minimal Atlassian Document Format Jira requires
    for description/comment bodies.
    """
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": text or "",
                    }
                ],
            }
        ],
    }


@mcp.tool()
async def create_issue(
    project_key: str,
    summary: str,
    description: str = "",
    issue_type: str = "Task",
) -> dict[str, Any]:
    """
    Create a Jira issue.
    """
    normalized_project_key = str(project_key or "").strip()
    normalized_summary = str(summary or "").strip()

    if not normalized_project_key:
        raise ValueError("project_key is required.")
    if not normalized_summary:
        raise ValueError("summary is required.")

    result = await _request_json(
        "POST",
        "/rest/api/3/issue",
        json_body={
            "fields": {
                "project": {"key": normalized_project_key},
                "summary": normalized_summary,
                "description": _adf_description(description),
                "issuetype": {
                    "name": str(issue_type or "Task").strip() or "Task"
                },
            }
        },
    )

    return {
        "status": "success",
        "issue_key": result.get("key", ""),
        "issue_id": result.get("id", ""),
    }


@mcp.tool()
async def add_comment(
    issue_key: str,
    comment: str,
) -> dict[str, Any]:
    """
    Add a comment to a Jira issue.
    """
    normalized_issue_key = str(issue_key or "").strip()
    normalized_comment = str(comment or "").strip()

    if not normalized_issue_key:
        raise ValueError("issue_key is required.")
    if not normalized_comment:
        raise ValueError("comment is required.")

    result = await _request_json(
        "POST",
        f"/rest/api/3/issue/{normalized_issue_key}/comment",
        json_body={"body": _adf_description(normalized_comment)},
    )

    return {
        "status": "success",
        "issue_key": normalized_issue_key,
        "comment_id": result.get("id", ""),
    }


@mcp.tool()
async def update_issue(
    issue_key: str,
    summary: str | None = None,
    description: str | None = None,
    priority: str | None = None,
) -> dict[str, Any]:
    """
    Update selected Jira issue fields (summary, description, priority).
    """
    normalized_issue_key = str(issue_key or "").strip()

    if not normalized_issue_key:
        raise ValueError("issue_key is required.")

    fields: dict[str, Any] = {}

    if summary and summary.strip():
        fields["summary"] = summary.strip()

    if description is not None:
        fields["description"] = _adf_description(description)

    if priority and priority.strip():
        fields["priority"] = {"name": priority.strip()}

    if not fields:
        return {
            "status": "no_changes",
            "issue_key": normalized_issue_key,
        }

    await _request_json(
        "PUT",
        f"/rest/api/3/issue/{normalized_issue_key}",
        json_body={"fields": fields},
    )

    return {
        "status": "success",
        "issue_key": normalized_issue_key,
        "updated_fields": list(fields),
    }


@mcp.tool()
async def delete_issue(
    issue_key: str,
    confirm: bool = False,
) -> dict[str, Any]:
    """
    Delete a Jira issue. Requires confirm=true; otherwise returns
    confirmation_required without deleting anything.
    """
    normalized_issue_key = str(issue_key or "").strip()

    if not normalized_issue_key:
        raise ValueError("issue_key is required.")

    if not confirm:
        return {
            "status": "confirmation_required",
            "issue_key": normalized_issue_key,
            "message": "Set confirm=true to permanently delete the issue.",
        }

    await _request_json(
        "DELETE",
        f"/rest/api/3/issue/{normalized_issue_key}",
    )

    return {
        "status": "success",
        "deleted": True,
        "issue_key": normalized_issue_key,
    }


# ---------------------------------------------------------------------------
# Server startup
# ---------------------------------------------------------------------------


def main() -> None:
    """
    Start the Jira MCP server.

    The MCP client / Google ADK runtime is responsible for providing:
        JIRA_BASE_URL
        JIRA_EMAIL
        JIRA_API_TOKEN
    """
    transport = os.getenv(
        "JIRA_MCP_TRANSPORT",
        "stdio",
    ).strip().lower()

    if transport in {
        "streamable-http",
        "streamable_http",
        "http",
    }:
        mcp.run(
            transport="streamable-http"
        )
    else:
        mcp.run()


if __name__ == "__main__":
    main()