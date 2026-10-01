from __future__ import annotations
 
import random
import time
from dataclasses import dataclass
from typing import Any, Iterable
 
import requests
from requests.auth import HTTPBasicAuth
import logging
from requests.exceptions import (
    ConnectionError,
    HTTPError,
    ReadTimeout,
    Timeout,
)
 
logger = logging.getLogger(__name__)
 
class JiraError(RuntimeError):
    pass
 
 
@dataclass(frozen=True)
class JiraConfig:
    base_url: str
    email: str
    api_token: str
    project_key: str
    epic_issue_type: str = "Epic"
    story_issue_type: str = "Story"
    epic_id_field: str = ""
    story_id_field: str = ""
    module_id_field: str = ""
    change_status_field: str = ""
    release_label: str = ""
 
 
class JiraClient:
    """Small Jira Cloud REST client with retries and enhanced-search pagination."""
 
    def __init__(self, config: JiraConfig, timeout: int = 60) -> None:
        self.config = config
        self.timeout = timeout
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(config.email, config.api_token)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
 
    # def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
    #     url = f"{self.config.base_url.rstrip('/')}{path}"
    #     for attempt in range(8):
    #         response = self.session.request(method, url, timeout=self.timeout, **kwargs)
    #         if response.status_code == 429:
    #             wait = float(response.headers.get("Retry-After", 2 ** attempt))
    #             time.sleep(wait + random.uniform(0.1, 0.8))
    #             continue
    #         if 500 <= response.status_code < 600:
    #             time.sleep(min(30, 2 ** attempt) + random.uniform(0.1, 0.8))
    #             continue
    #         if response.status_code >= 400:
    #             raise JiraError(
    #                 f"Jira {method} {path} failed: {response.status_code} {response.text[:2000]}"
    #             )
    #         return response
    #     raise JiraError(f"Jira {method} {path} failed after retries")
    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        """
        Execute a Jira REST request with retry support.
 
        Retries:
            - HTTP 429 (Rate Limit)
            - HTTP 500/502/503/504
            - ConnectionError
            - Timeout
            - ReadTimeout
 
        Does NOT retry:
            - Authentication failures (401)
            - Permission errors (403)
            - Invalid requests (400)
            - Not Found (404)
        """
 
        url = f"{self.config.base_url.rstrip('/')}{path}"
 
        MAX_RETRIES = 5
 
        for attempt in range(1, MAX_RETRIES + 1):
 
            try:
 
                response = self.session.request(
                    method,
                    url,
                    timeout=self.timeout,
                    **kwargs,
                )
 
                # ----------------------------
                # Rate Limit
                # ----------------------------
                if response.status_code == 429:
 
                    retry_after = response.headers.get("Retry-After")
 
                    if retry_after:
                        wait = float(retry_after)
                    else:
                        wait = min(2 ** attempt, 30)
 
                    logger.warning(
                        f"Jira Rate Limited (429). "
                        f"Retry {attempt}/{MAX_RETRIES} after {wait}s"
                    )
 
                    time.sleep(wait + random.uniform(0.2, 1.0))
                    continue
 
                # ----------------------------
                # Server Errors
                # ----------------------------
                if response.status_code in (500, 502, 503, 504):
 
                    wait = min(2 ** attempt, 30)
 
                    logger.warning(
                        f"Jira Server Error {response.status_code}. "
                        f"Retry {attempt}/{MAX_RETRIES} after {wait}s"
                    )
 
                    time.sleep(wait + random.uniform(0.2, 1.0))
                    continue
 
                # ----------------------------
                # Client Errors
                # ----------------------------
                if response.status_code >= 400:
 
                    raise JiraError(
                        f"Jira {method} {path} failed "
                        f"({response.status_code})\n"
                        f"{response.text[:2000]}"
                    )
 
                return response
 
            except (ConnectionError, Timeout, ReadTimeout) as ex:
 
                if attempt == MAX_RETRIES:
                    raise JiraError(
                        f"Jira request failed after {MAX_RETRIES} attempts."
                    ) from ex
 
                wait = min(2 ** attempt, 30)
 
                logger.warning(
                    f"Network error: {type(ex).__name__}. "
                    f"Retry {attempt}/{MAX_RETRIES} after {wait}s"
                )
 
                time.sleep(wait + random.uniform(0.2, 1.0))
 
            except HTTPError as ex:
                raise JiraError(str(ex)) from ex
 
        raise JiraError(
            f"Jira {method} {path} failed after {MAX_RETRIES} retry attempts."
        )
       
 
    def test_connection(self) -> dict[str, Any]:
        return self._request("GET", "/rest/api/3/myself").json()
 
    def list_fields(self) -> list[dict[str, Any]]:
        return self._request("GET", "/rest/api/3/field").json()
 
    def issue_types(self) -> list[dict[str, Any]]:
        path = f"/rest/api/3/issue/createmeta/{self.config.project_key}/issuetypes"
        data = self._request("GET", path).json()
        return data.get("issueTypes", [])
 
    def search(self, jql: str, fields: Iterable[str], max_results: int = 100) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        token: str | None = None
        while True:
            body: dict[str, Any] = {
                "jql": jql,
                "fields": list(fields),
                "maxResults": max_results,
            }
            if token:
                body["nextPageToken"] = token
            data = self._request("POST", "/rest/api/3/search/jql", json=body).json()
            issues.extend(data.get("issues", []))
            if data.get("isLast", True):
                break
            token = data.get("nextPageToken")
            if not token:
                break
        return issues
 
    def create_issue(self, fields: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/rest/api/3/issue", json={"fields": fields}).json()
 
    def bulk_create(self, issue_fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(issue_fields) > 50:
            raise ValueError("Jira bulk create accepts at most 50 issues per request")
        payload = {"issueUpdates": [{"fields": fields} for fields in issue_fields]}
        data = self._request("POST", "/rest/api/3/issue/bulk", json=payload).json()
        errors = data.get("errors", [])
        if errors:
            raise JiraError(f"Bulk create returned errors: {errors}")
        return data.get("issues", [])
 
 

 