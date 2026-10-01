import test from "node:test";
import assert from "node:assert/strict";
import { fetchJiraIssueGroups, normalizeJiraIssue, readJiraConfig, searchIssues } from "./rest-client.js";

const paragraph = (...text) => ({ type: "paragraph", content: text.map(value => ({ type: "text", text: value })) });
const heading = text => ({ type: "heading", content: [{ type: "text", text }] });
const doc = (...content) => ({ type: "doc", content });
const config = { baseUrl: "https://jira.example.test", email: "test", apiToken: "test", projectKey: "SCRUM", pageSize: 100, maxPages: 5 };
const story = fields => ({ key: "SCRUM-2", fields: { issuetype: { name: "Story" }, ...fields } });

test("criteria in an ADF custom field preserve inline text and list boundaries", () => {
  const issue = normalizeJiraIssue(story({ customfield_123: doc({ type: "bulletList", content: [
    { type: "listItem", content: [paragraph("Given a ", "customer")] },
    { type: "listItem", content: [paragraph("Then display balance")] }
  ] }) }), config.baseUrl, { acceptanceCriteriaFieldIds: ["customfield_123"] });
  assert.deepEqual(issue.acceptanceCriteria, ["Given a customer", "Then display balance"]);
});

test("description fallback reads only an explicit criteria section", () => {
  const issue = normalizeJiraIssue(story({ description: doc(paragraph("User journey"), heading("Acceptance Criteria"),
    paragraph("Show the balance"), paragraph("Reject invalid accounts"), heading("Dependencies"), paragraph("Not a criterion")) }), config.baseUrl);
  assert.deepEqual(issue.acceptanceCriteria, ["Show the balance", "Reject invalid accounts"]);
  assert.deepEqual(normalizeJiraIssue(story({ description: "An ordinary user story without criteria." }), config.baseUrl).acceptanceCriteria, []);
});

test("custom criteria take precedence and configured field IDs are supported", () => {
  const c = readJiraConfig({ TAAP_IS_MOCK: "true", JIRA_ACCEPTANCE_CRITERIA_FIELDS: "customfield_123, customfield_456" });
  assert.deepEqual(c.acceptanceCriteriaFieldIds, ["customfield_123", "customfield_456"]);
  const issue = normalizeJiraIssue(story({ customfield_123: ["One", "Two"], description: "Acceptance Criteria: fallback", customfield_10014: "SCRUM-1" }), config.baseUrl, { acceptanceCriteriaFieldIds: c.acceptanceCriteriaFieldIds });
  assert.deepEqual(issue.acceptanceCriteria, ["One", "Two"]);
  assert.equal(issue.parentKey, "SCRUM-1");
});

test("Jira criteria headings and separate AC labels are not counted as criteria", () => {
  const issue = normalizeJiraIssue(story({ customfield_123: doc(heading("Acceptance Criteria"), paragraph("AC1:"),
    paragraph("Select beneficiary"), paragraph("AC2:"), paragraph("Enter transfer amount")) }), config.baseUrl,
  { acceptanceCriteriaFieldIds: ["customfield_123"] });
  assert.deepEqual(issue.acceptanceCriteria, ["Select beneficiary", "Enter transfer amount"]);
});

test("requirements fetch follows all pages, excludes empty stories and epic descriptions", async t => {
  const requests = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    if (url.endsWith("/field")) return Response.json([{ id: "customfield_123", name: "Acceptance_Criteria" }]);
    const body = JSON.parse(options.body);
    requests.push(body);
    if (body.jql.includes('"Epic"')) {
      assert.ok(!body.fields.includes("description"));
      return Response.json({ issues: [{ key: "SCRUM-1", fields: { issuetype: { name: "Epic" }, description: "Do not display" } }], isLast: true });
    }
    assert.ok(body.fields.includes("customfield_123"));
    return body.nextPageToken
      ? Response.json({ issues: [story({ parent: { key: "SCRUM-1" }, customfield_123: "Criterion on page 2" })], isLast: true })
      : Response.json({ issues: [{ key: "SCRUM-3", fields: { issuetype: { name: "Story" } } }], isLast: false, nextPageToken: "page2" });
  });
  const result = await fetchJiraIssueGroups({ config, requirementsOnly: true, writeSnapshot: false });
  assert.equal(requests.length, 3);
  assert.equal(result.groups.stories.issues.length, 1);
  assert.deepEqual(result.groups.stories.issues[0].acceptanceCriteria, ["Criterion on page 2"]);
  assert.equal(result.groups.epics.issues[0].description, "");
  assert.equal(result.groups.bugs, undefined);
});

test("pagination fails instead of reporting incomplete results as complete", async t => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ issues: [], isLast: false, nextPageToken: "repeat" }));
  await assert.rejects(searchIssues(config, { jql: "project = SCRUM" }), /pagination/);
  await assert.rejects(searchIssues({ ...config, maxPages: 1 }, { jql: "project = SCRUM" }), /MAX_PAGES/);
});
