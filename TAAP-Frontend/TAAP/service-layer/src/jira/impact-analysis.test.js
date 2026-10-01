import test from "node:test";
import assert from "node:assert/strict";
import { fetchJiraImpactAnalysis, impactLinks } from "./impact-analysis.js";

const config = { baseUrl: "https://jira.example.test", email: "test", apiToken: "test", pageSize: 100, maxPages: 5 };
const issue = (key, links = [], extra = {}) => ({ key, fields: { summary: key, issuetype: { name: "Story" }, status: { name: "Open" }, issuelinks: links, ...extra } });
const link = (key, label = "impacts", inward = false) => ({ type: { outward: label, inward: label }, [inward ? "inwardIssue" : "outwardIssue"]: { key } });
function mockJira(t, issues, metadata = []) {
  t.mock.method(globalThis, "fetch", async url => {
    if (url.endsWith("/field")) return Response.json(metadata);
    const key = new URL(url).pathname.split("/").at(-1);
    return issues[key] ? Response.json(issues[key]) : Response.json({}, { status: 404 });
  });
}

test("only downstream labels qualify, preserving Jira direction and wording", () => {
  const result = impactLinks(issue("A-1", [link("A-2"), link("A-3", "is impacted by", true), link("A-4", "relates to"), link("A-5", "is required by", true), link("A-6", "blocks")]));
  assert.deepEqual(result.map(item => item.targetKey), ["A-2", "A-5", "A-6"]);
  assert.equal(result[1].relationship, "is required by");
});

test("multiple roots, cycles, cross-project stories and all relationship evidence are retained", async t => {
  mockJira(t, {
    "A-1": issue("A-1", [link("B-2"), link("B-2"), link("A-4", "relates to")]),
    "A-2": issue("A-2", [link("B-2", "blocks")]),
    "B-2": issue("B-2", [link("B-3")]),
    "B-3": issue("B-3", [link("A-1")])
  });
  const result = await fetchJiraImpactAnalysis({ keys: ["A-1", "A-2", "A-1"], config });
  assert.deepEqual(result.stories.map(story => story.key), ["B-2", "B-3"]);
  assert.equal(result.relationships.length, 4);
  assert.deepEqual(result.warnings, []);
  assert.equal(result.stories[0].url, "https://jira.example.test/browse/B-2");
});

test("explicit impact fields are supported and prose is flagged instead of inferred", async t => {
  mockJira(t, { "A-1": issue("A-1", [], { customfield_42: [{ key: "B-2" }, "Review B-3 later"] }), "B-2": issue("B-2") }, [{ id: "customfield_42", name: "Impacted Stories" }]);
  const result = await fetchJiraImpactAnalysis({ keys: ["A-1"], config });
  assert.deepEqual(result.stories.map(story => story.key), ["B-2"]);
  assert.match(result.warnings[0], /not an issue reference/);
  assert.equal(result.relationships[0].evidence, "Jira field: Impacted Stories");
});

test("unreadable linked issues are partial results, not a false empty success", async t => {
  mockJira(t, { "A-1": issue("A-1", [link("B-2")]) });
  const result = await fetchJiraImpactAnalysis({ keys: ["A-1"], config });
  assert.equal(result.stories.length, 0);
  assert.match(result.warnings[0], /B-2.*incomplete/);
});

test("epic expansion follows pagination and includes stories without acceptance criteria", async t => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    if (url.endsWith("/field")) return Response.json([]);
    if (url.includes("/issue/A-1?")) return Response.json(issue("A-1", [], { issuetype: { name: "Epic" } }));
    if (url.endsWith("/search/jql")) {
      const body = JSON.parse(options.body);
      assert.match(body.jql, /parent = "A-1"/);
      return body.nextPageToken ? Response.json({ issues: [issue("A-3", [link("B-1")])], isLast: true })
        : Response.json({ issues: [issue("A-2")], isLast: false, nextPageToken: "page2" });
    }
    return Response.json(issue("B-1"));
  });
  const result = await fetchJiraImpactAnalysis({ keys: ["A-1"], config });
  assert.deepEqual(result.selectedKeys, ["A-2", "A-3"]);
  assert.deepEqual(result.stories.map(story => story.key), ["B-1"]);
});

test("invalid selection and Jira failures do not return successful empty results", async t => {
  await assert.rejects(fetchJiraImpactAnalysis({ keys: ['A-1" OR project=X'], config }), /valid Jira/);
  t.mock.method(globalThis, "fetch", async () => Response.json({}, { status: 401 }));
  await assert.rejects(fetchJiraImpactAnalysis({ keys: ["A-1"], config }), /401/);
});
