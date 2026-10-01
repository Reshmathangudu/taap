# Jira requirements analysis

The existing criticality agent scores module criticality from orchestrator data.
The separate `app/agents/requirements_agent` analyzes business requirements before
test execution. It uses the existing Jira MCP client and the configured LiteLLM model.

## Configuration

Copy `.env.example` to `.env` in this directory and fill in `JIRA_API_TOKEN` and
`OPENAI_API_KEY` locally. Do not commit credentials. Use ordinary dotenv syntax:
`https://...`, without escaped colons or trailing backslashes. The backend resolves
this file relative to its directory, regardless of the launch directory. Process
environment variables take precedence. Restart the server after configuration changes.

`JIRA_PROJECT_KEY`, `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`,
`JIRA_MCP_PAGE_SIZE`, `JIRA_MCP_MAX_PAGES`, and `JIRA_MCP_SERVER_SCRIPT` are configurable.
Relative MCP script paths resolve from this backend directory. An explicit MCP client
constructor page size/page limit overrides settings. Page size must be 1–100.
`JIRA_ACCEPTANCE_CRITERIA_FIELD` optionally selects the tenant's acceptance-criteria
custom-field ID. Acceptance criteria can also appear in the description.

## Run

From this directory in the backend's Python environment:

```powershell
python -m pip install -r requirements-agent.txt
adk run app/agents/requirements_agent
```

Example request to the standalone agent: `Analyze SCRUM-12 and SCRUM-15. Walkthrough
notes: the account summary must show pending transfers; the sandbox API contract is pending.`

The existing backend API also registers `POST /requirements/analyze`:

```json
{
  "issue_keys": ["SCRUM-12", "SCRUM-15"],
  "walkthrough_notes": "Stakeholders confirmed the affected account journey..."
}
```

Omit `issue_keys` to search configured Epic/Story types in the project. Explicit
keys can select any requirement issue type in that project. Search follows all MCP
pages; scopes larger than `REQUIREMENTS_MAX_ISSUES` are rejected without LLM calls.
Use explicit keys for large projects. Each requirement is analyzed independently;
this does not discover a complete cross-project dependency graph. Oversized source
text is rejected, not silently truncated. No matches returns `no_requirements`.

The response contains source Jira keys, URLs and timestamps plus:

- Requirement summary, changes, journeys, business impact and missing-information questions.
- Impacted modules, upstream/downstream systems and regression areas, with evidence/assumptions.
- Manual test cases and automated test designs with actions, expected results and blockers.
- Test plan, customer/account/API/integration/environment data needs.
- Provisional effort ranges and roles for QE Lead/Test Manager review.
- Risks, mitigations and dependencies.
- Local traceability rows mapping each source issue to generated test IDs and criteria.

Reports are returned as JSON drafts. They are not persisted automatically. Jira/Xray
publication is not implemented: `jira_xray_test_key` is null and `publication_status`
is `draft_not_published`. Automation output is a design/implementation outline, not
an executed test suite. To implement runnable automation, supply the application/API
contracts, framework, environments and selectors. To publish, configure the tenant's
Xray edition, authentication, test fields and link relationship separately.

Confluence text and walkthrough notes can be supplied in `walkthrough_notes`.
Confluence page fetching, Jira comment fetching, and screenshot interpretation are
not implemented. Attachments are metadata only. All retrieved content is treated
as untrusted evidence in a separate model message; the analysis model has no tools.
Schema validation rejects malformed/truncated responses. Remote error bodies and
credentials are excluded from endpoint error responses.

Configuration errors return HTTP 503, Jira/model failures 502, invalid scope/input
422. Existing backend dependencies are still needed to run the full risk-tier API;
`requirements-agent.txt` supports the standalone requirements agent and its tests.

## Verify

```powershell
python -m unittest discover -s tests -v
```

Tests use mocked Jira/model responses and never contact Jira or publish artifacts.
