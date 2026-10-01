import test from "node:test";
import assert from "node:assert/strict";
import { extractRiskSection, fetchJiraRiskSection, normalizeRiskData } from "./risk-section.js";

const paragraph = text => ({ type: "paragraph", content: [{ type: "text", text }] });
const heading = (text, level) => ({ type: "heading", attrs: { level }, content: [{ type: "text", text }] });
const config = { baseUrl: "https://jira.example.test", email: "test", apiToken: "test" };

test("ADF extraction includes subsections and stops at the next peer heading", () => {
  const description = { type: "doc", content: [paragraph("Unrelated description"), heading("Risk Analysis", 2),
    paragraph("Payments is affected."), heading("Dependencies", 3), paragraph("Ledger updates."),
    heading("Acceptance Criteria", 2), paragraph("Do not send this.")] };
  assert.equal(extractRiskSection(description), "Payments is affected.\n\n### Dependencies\n\nLedger updates.");
});

test("risk extraction excludes neighboring impact content and handles inline ADF sections", () => {
  assert.equal(extractRiskSection("Risk Analysis:\nRetries may duplicate payments.\nImpact Analysis:\nUnrelated"), "Retries may duplicate payments.");
  assert.equal(extractRiskSection({ type: "doc", content: [paragraph("Risk Analysis: No known risks."), heading("Acceptance Criteria", 2), paragraph("Ignore")] }), "No known risks.");
  assert.equal(extractRiskSection({ type: "doc", content: [heading("Risk Analysis", 2), heading("Impact Analysis", 2), paragraph("Ignore")] }), "");
});

test("risk tables preserve separate cells and recorded rich-text references", () => {
  const cell = text => ({ type: "tableCell", content: [paragraph(text)] });
  assert.equal(normalizeRiskData({ type: "table", content: [{ type: "tableRow", content: [cell("Risk"), cell("Likelihood"), cell("Mitigation")] }, { type: "tableRow", content: [cell("Duplicate charge"), cell("Low"), cell("Idempotency key")] }] }).trim(), "Risk | Likelihood | Mitigation\nDuplicate charge | Low | Idempotency key");
  assert.equal(normalizeRiskData({ type: "mention", attrs: { text: "@Owner" } }), "@Owner");
});

test("Jira failures and mock mode fail explicitly without returning risk data", async t => {
  await assert.rejects(fetchJiraRiskSection({ key: "ABC-2", config: { ...config, isMock: true } }), /mock mode/);
  for (const status of [401, 403, 404]) {
    t.mock.method(globalThis, "fetch", async () => Response.json({ errorMessages: ["Unavailable"] }, { status }));
    await assert.rejects(fetchJiraRiskSection({ key: "ABC-2", config }), error => error.status === status);
  }
});

test("plain, Markdown and Jira wiki sections are isolated without treating ordinary prose as risk", () => {
  assert.equal(extractRiskSection("Description\nSomething might risk analysis later."), "");
  assert.equal(extractRiskSection("**Risk Analysis:**\nPayments changes.\n**Acceptance Criteria**\nIgnore"), "Payments changes.");
  assert.equal(extractRiskSection("h2. Risk Analysis\nPayments\nh3. Data\nLedger\nh2. Notes\nIgnore"), "Payments\nh3. Data\nLedger");
  assert.equal(extractRiskSection("## Risk Analysis\n### Risks\nRisk text\n## Notes\nIgnore"), "### Risks\nRisk text");
  assert.equal(extractRiskSection("Risk Analysis: No risk.\nNotes:\nIgnore"), "No risk.");
});

test("fresh story fetch returns custom risk fields and only the description risk section", async t => {
  t.mock.method(globalThis, "fetch", async url => {
    if (url.endsWith("/field")) return Response.json([{ id: "customfield_42", name: "Risk Analysis" }]);
    assert.match(url, /issue\/ABC-2\?fields=.*customfield_42/);
    return Response.json({ fields: { summary: "Payments", issuetype: { name: "Story" }, customfield_42: { type: "doc", content: [paragraph("Ledger changes.")] },
      description: "## Risk Analysis\nPayments changes.\n## Acceptance Criteria\nIgnore" } });
  });
  const story = await fetchJiraRiskSection({ key: "ABC-2", config });
  assert.deepEqual(story.sections.map(section => section.text), ["Ledger changes.", "Payments changes."]);
  assert.equal(story.url, "https://jira.example.test/browse/ABC-2");
});

test("missing section stays empty; invalid keys and non-stories are rejected", async t => {
  await assert.rejects(fetchJiraRiskSection({ key: "bad/key", config }), /valid Jira/);
  t.mock.method(globalThis, "fetch", async url => url.endsWith("/field") ? Response.json([])
    : Response.json({ fields: { issuetype: { name: "Story" }, description: "Ordinary description" } }));
  assert.deepEqual((await fetchJiraRiskSection({ key: "ABC-2", config })).sections, []);
  t.mock.method(globalThis, "fetch", async url => url.endsWith("/field") ? Response.json([])
    : Response.json({ fields: { issuetype: { name: "Epic" } } }));
  await assert.rejects(fetchJiraRiskSection({ key: "ABC-2", config }), /user story/);
});
