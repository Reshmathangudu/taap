import test from "node:test";
import assert from "node:assert/strict";
import { extractImpactSection, fetchJiraImpactSection } from "./impact-section.js";

const paragraph = text => ({ type: "paragraph", content: [{ type: "text", text }] });
const heading = (text, level) => ({ type: "heading", attrs: { level }, content: [{ type: "text", text }] });
const config = { baseUrl: "https://jira.example.test", email: "test", apiToken: "test" };

test("ADF extraction includes subsections and stops at the next peer heading", () => {
  const description = { type: "doc", content: [paragraph("Unrelated description"), heading("Impact Analysis", 2),
    paragraph("Payments is affected."), heading("Dependencies", 3), paragraph("Ledger updates."),
    heading("Acceptance Criteria", 2), paragraph("Do not send this.")] };
  assert.equal(extractImpactSection(description), "Payments is affected.\n\n## Dependencies\n\nLedger updates.");
});

test("plain, Markdown and Jira wiki sections are isolated without treating ordinary prose as impact", () => {
  assert.equal(extractImpactSection("Description\nSomething might impact analysis later."), "");
  assert.equal(extractImpactSection("**Impact Analysis:**\nPayments changes.\n**Acceptance Criteria**\nIgnore"), "Payments changes.");
  assert.equal(extractImpactSection("h2. Impact Analysis\nPayments\nh3. Data\nLedger\nh2. Notes\nIgnore"), "Payments\nh3. Data\nLedger");
  assert.equal(extractImpactSection("## Impact Analysis\n### Risks\nRisk text\n## Notes\nIgnore"), "### Risks\nRisk text");
  assert.equal(extractImpactSection("Impact Analysis: No impact.\nNotes:\nIgnore"), "No impact.");
});

test("fresh story fetch returns custom impact fields and only the description impact section", async t => {
  t.mock.method(globalThis, "fetch", async url => {
    if (url.endsWith("/field")) return Response.json([{ id: "customfield_42", name: "Impact Analysis" }]);
    assert.match(url, /issue\/ABC-2\?fields=.*customfield_42/);
    return Response.json({ fields: { summary: "Payments", issuetype: { name: "Story" }, customfield_42: { type: "doc", content: [paragraph("Ledger changes.")] },
      description: "## Impact Analysis\nPayments changes.\n## Acceptance Criteria\nIgnore" } });
  });
  const story = await fetchJiraImpactSection({ key: "ABC-2", config });
  assert.deepEqual(story.sections.map(section => section.text), ["Ledger changes.", "Payments changes."]);
  assert.equal(story.url, "https://jira.example.test/browse/ABC-2");
});

test("missing section stays empty; invalid keys and non-stories are rejected", async t => {
  await assert.rejects(fetchJiraImpactSection({ key: "bad/key", config }), /valid Jira/);
  t.mock.method(globalThis, "fetch", async url => url.endsWith("/field") ? Response.json([])
    : Response.json({ fields: { issuetype: { name: "Story" }, description: "Ordinary description" } }));
  assert.deepEqual((await fetchJiraImpactSection({ key: "ABC-2", config })).sections, []);
  t.mock.method(globalThis, "fetch", async url => url.endsWith("/field") ? Response.json([])
    : Response.json({ fields: { issuetype: { name: "Epic" } } }));
  await assert.rejects(fetchJiraImpactSection({ key: "ABC-2", config }), /user story/);
});
