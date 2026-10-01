import test from "node:test";
import assert from "node:assert/strict";
import { fetchJiraTestCases } from "./test-cases.js";

const config = { baseUrl: "https://jira.example.test", email: "test", apiToken: "test", pageSize: 100, maxPages: 20 };
const issue = (key, type, fields = {}) => ({ key, fields: { summary: key, issuetype: { name: type }, ...fields } });

test("multiple epics expand all pages; story overlap and linked tests are deduplicated", async t => {
  const story1 = issue("A-10", "Story", { parent: { key: "A-1" }, issuelinks: [{ outwardIssue: { key: "B-99" } }] });
  const story2 = issue("A-20", "Story", { parent: { key: "A-2" }, issuelinks: [{ inwardIssue: { key: "B-99" } }] });
  const records = { "A-1": issue("A-1", "Epic"), "A-2": issue("A-2", "Epic"), "A-10": story1, "B-99": issue("B-99", "Test") };
  const queries = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    if (url.endsWith("/field")) return Response.json([{ id: "customfield_10", name: "Test_Case_ID" }, { id: "customfield_20", name: "Epic Link" }]);
    if (url.includes("/issue/")) return Response.json(records[url.match(/\/issue\/([^?]+)/)[1]]);
    const body = JSON.parse(options.body); queries.push(body);
    if (body.jql.includes('parent = "A-1"')) {
      assert.match(body.jql, /cf\[20\]/);
      return Response.json(body.nextPageToken ? { issues: [issue("A-11", "Story")], isLast: true } : { issues: [story1], isLast: false, nextPageToken: "next" });
    }
    if (body.jql.includes('parent = "A-2"')) return Response.json({ issues: [story2], isLast: true });
    assert.match(body.jql, /parent in/);
    assert.match(body.jql, /"A-11"/);
    return Response.json({ issues: [issue("A-50", "Test Case", { parent: { key: "A-10" }, priority: { name: "High" }, assignee: { displayName: "Owner" } }),
      issue("A-51", "Sub-task", { parent: { key: "A-20" }, customfield_10: "TC-51" }),
      issue("A-52", "Task", { parent: { key: "A-20" } }),
      issue("A-53", "Test", { parent: { key: "UNRELATED-1" } })], isLast: true });
  });
  const result = await fetchJiraTestCases({ keys: ["A-1", "A-2", "A-10", "A-1"], config });
  assert.deepEqual(result.selectedKeys, ["A-1", "A-2", "A-10"]);
  assert.deepEqual(result.storyKeys, ["A-10", "A-11", "A-20"]);
  assert.deepEqual(result.cases.map(row => row.id), ["A-50", "A-51", "B-99"]);
  assert.deepEqual(result.cases[2].requirementKeys, ["A-10", "A-20"]);
  assert.equal(result.cases[0].owner, "Owner");
  assert.equal(result.cases[0].automation, "Not provided");
  assert.ok(queries.some(query => query.nextPageToken === "next"));
});

test("single story fetch is scoped and empty results do not fabricate cases", async t => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    if (url.endsWith("/field")) return Response.json([]);
    if (url.includes("/issue/")) return Response.json(issue("A-10", "Story"));
    assert.equal(JSON.parse(options.body).jql, 'parent in ("A-10")');
    return Response.json({ issues: [], isLast: true });
  });
  const result = await fetchJiraTestCases({ keys: ["A-10"], config });
  assert.deepEqual(result.cases, []);
  assert.deepEqual(result.storyKeys, ["A-10"]);
});

test("invalid selections, mock data and Jira errors fail explicitly", async t => {
  for (const keys of [[], ["A-1 OR project=X"]]) await assert.rejects(fetchJiraTestCases({ keys, config }), /valid Jira/);
  await assert.rejects(fetchJiraTestCases({ keys: ["A-1"], config: { ...config, isMock: true } }), /mock mode/);
  t.mock.method(globalThis, "fetch", async () => Response.json({ errorMessages: ["Forbidden"] }, { status: 403 }));
  await assert.rejects(fetchJiraTestCases({ keys: ["A-1"], config }), error => error.status === 403);
  t.mock.method(globalThis, "fetch", async url => Response.json(url.endsWith("/field") ? [] : issue("A-1", "Bug")));
  await assert.rejects(fetchJiraTestCases({ keys: ["A-1"], config }), /not an epic or user story/);
});

test("excludes Bug issues and Bug test types, retaining the actual subtask issue type", async t => {
  t.mock.method(globalThis, "fetch", async url => {
    if (url.endsWith("/field")) return Response.json([{ id: "customfield_10", name: "Test Case ID" }, { id: "customfield_11", name: "Test Type" }]);
    if (url.includes("/issue/A-1?")) return Response.json(issue("A-1", "Story", { issuelinks: [{ outwardIssue: { key: "A-5" } }] }));
    if (url.includes("/issue/A-5?")) return Response.json(issue("A-5", "Bug", { customfield_10: "TC-5" }));
    return Response.json({ isLast: true, issues: [
      issue("A-2", "Bug", { parent: { key: "A-1" }, customfield_10: "TC-2" }),
      issue("A-3", "Sub-task", { parent: { key: "A-1" }, customfield_11: { value: " Bug " } }),
      issue("A-4", "Sub-task", { parent: { key: "A-1" }, customfield_11: { value: "Functional" } })
    ] });
  });
  const result = await fetchJiraTestCases({ keys: ["A-1"], config });
  assert.deepEqual(result.cases.map(row => [row.id, row.type]), [["A-4", "Sub-task"]]);
});
