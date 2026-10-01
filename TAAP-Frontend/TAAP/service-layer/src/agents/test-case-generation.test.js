import test from "node:test";
import assert from "node:assert/strict";
import { generateTestCasesFromRequirements } from "./test-case-generation.js";

test("discovers the A2A agent card and maps generated test cases for selected requirements", async t => {
  const requests = [];

  t.mock.method(globalThis, "fetch", async (url, options = {}) => {
    requests.push({ url, options });

    if (String(url).endsWith("/.well-known/agent-card.json")) {
      return Response.json({
        name: "test_case_generation_agent",
        version: "0.0.1",
        supportedInterfaces: [{ url: "http://agent.local", protocolBinding: "JSONRPC", protocolVersion: "1.0" }]
      });
    }

    const body = JSON.parse(options.body);
    const context = JSON.parse(body.params.message.parts[0].text);

    assert.equal(options.headers["A2A-Version"], "1.0");
    assert.equal(body.method, "message/send");
    assert.equal(body.params.message.role, "user");
    assert.equal(body.params.message.parts[0].kind, "text");
    assert.equal(context.story_key, "SCRUM-24");
    assert.deepEqual(context.acceptance_criteria, [{ id: "AC-1", text: "Remaining attempts are displayed." }]);

    return Response.json({
      result: {
        task: {
          status: { state: "TASK_STATE_COMPLETED" },
          artifacts: [{
            parts: [{
              text: JSON.stringify({
                story_key: "SCRUM-24",
                requirement_summary: "Display remaining OTP attempts.",
                coverage_analysis: [],
                generated_test_cases: [{
                  generated_test_id: "TC-NEW-SCRUM-24-1",
                  story_key: "SCRUM-24",
                  title: "Display remaining attempts",
                  objective: "Verify remaining attempts are visible.",
                  test_type: "POSITIVE",
                  test_basis: "ACCEPTANCE_CRITERION",
                  priority: "HIGH",
                  mapped_acceptance_criteria: ["AC-1"],
                  coverage_gap: "No existing test covers remaining attempts.",
                  preconditions: ["User is on OTP screen."],
                  test_data: [{ key: "otp", value: "111111" }],
                  steps: [{ step_number: 1, action: "Enter invalid OTP.", expected_result: "Remaining attempts are displayed." }],
                  final_expected_result: "Remaining attempts are shown.",
                  duplicate_check_notes: "No duplicate found."
                }],
                clarifications_required: [],
                generation_summary: "Generated one case."
              })
            }]
          }]
        }
      }
    });
  });

  const result = await generateTestCasesFromRequirements({
    requirements: [{
      key: "SCRUM-24",
      type: "Story",
      summary: "Display remaining OTP attempts",
      description: "The user sees remaining attempts.",
      priority: "High",
      acceptanceCriteria: ["Remaining attempts are displayed."]
    }],
    config: { baseUrl: "http://agent.local", timeoutMs: 120000 },
    now: new Date("2026-09-30T07:15:00Z")
  });

  assert.equal(result.source, "a2a");
  assert.equal(result.agent.name, "test_case_generation_agent");
  assert.deepEqual(result.selectedKeys, ["SCRUM-24"]);
  assert.equal(result.cases.length, 1);
  assert.equal(result.cases[0].id, "TC-NEW-SCRUM-24-1");
  assert.equal(result.cases[0].source, "a2a");
  assert.equal(result.cases[0].owner, "test_case_generation_agent");
  assert.equal(result.cases[0].generatedDetails.final_expected_result, "Remaining attempts are shown.");
  assert.equal(requests.length, 2);
});
