// Real backend client for TestSelectionReport, ExclusionSignoffQueue, and
// ExecutionAuditLog — replaces src/data/mockTests.ts / mockAuditLog.ts.
//
// Talks to the existing REST surface in app/api/api.py (the same one
// RunConsole's AG-UI stream sits alongside, see src/lib/runStatusBus.ts).
// Function names and return shapes intentionally match the mock module's
// exactly (see the note in mockTests.ts) — only the release-scoped
// parameter and the network call underneath are new.

import type {
  AuditEntry,
  Classification,
  FeedbackItem,
  ResidualRisk,
  SignoffStatus,
  TestCase,
} from "../types/testCase";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:4000";

interface ApiExclusion {
  likelihood?: unknown;
  impact?: unknown;
  residual?: unknown;
  signoff?: unknown;
  status?: unknown;
}

interface ApiTestRow {
  id?: unknown;
  name?: unknown;
  module?: unknown;
  tier?: unknown;
  classification?: unknown;
  score?: unknown;
  flags?: unknown;
  factors?: unknown;
  rationale?: unknown;
  exclusion?: ApiExclusion | null;
}

function normalizeTier(value: unknown): TestCase["tier"] {
  const n = Number(value);
  return n === 1 || n === 2 || n === 3 || n === 4 ? n : 4;
}

function normalizeClassification(value: unknown): Classification {
  return value === "must" || value === "rec" || value === "opt" || value === "exclude" ? value : "opt";
}

function normalizeResidual(value: unknown): ResidualRisk {
  return value === "low" || value === "medium" || value === "high" ? value : "low";
}

function normalizeSignoffStatus(value: unknown): SignoffStatus {
  return value === "none" || value === "pending" || value === "signed" ? value : "none";
}

function toTestCase(row: ApiTestRow): TestCase {
  const id = String(row.id ?? "");
  const exclusion = row.exclusion;
  return {
    id,
    name: String(row.name ?? id),
    module: String(row.module ?? "Not available"),
    tier: normalizeTier(row.tier),
    classification: normalizeClassification(row.classification),
    score: Number(row.score ?? 0),
    factors: Array.isArray(row.factors) ? (row.factors as TestCase["factors"]) : [],
    flags: Array.isArray(row.flags) ? (row.flags as string[]) : [],
    rationale: String(row.rationale ?? ""),
    exclusion: exclusion
      ? {
          likelihood: String(exclusion.likelihood ?? "Not available"),
          impact: String(exclusion.impact ?? "Not available"),
          residual: normalizeResidual(exclusion.residual),
          signoff: String(exclusion.signoff ?? "Not required"),
          status: normalizeSignoffStatus(exclusion.status),
        }
      : undefined,
  };
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Request failed (${res.status}): ${path}${body ? ` — ${body}` : ""}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchAllTests(releaseId: string): Promise<TestCase[]> {
  const data = await getJson<{ tests: ApiTestRow[] }>(
    `/api/v1/releases/${encodeURIComponent(releaseId)}/tests`,
  );
  return data.tests.map(toTestCase);
}

export async function fetchPendingExclusions(releaseId: string): Promise<TestCase[]> {
  const tests = await fetchAllTests(releaseId);
  return tests.filter((t) => t.exclusion?.status === "pending");
}

export async function submitSignoff(
  releaseId: string,
  testId: string,
  role: string,
  note: string,
): Promise<{ ok: true }> {
  const res = await fetch(
    `${API_BASE_URL}/api/v1/releases/${encodeURIComponent(releaseId)}/governance/${encodeURIComponent(testId)}/signoff`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, note }),
    },
  );
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Sign-off failed (${res.status})${body ? ` — ${body}` : ""}`);
  }
  return { ok: true };
}

export async function fetchAuditLog(releaseId: string): Promise<AuditEntry[]> {
  const data = await getJson<{ entries: Array<{ time?: unknown; agent?: unknown; text?: unknown }> }>(
    `/api/v1/releases/${encodeURIComponent(releaseId)}/audit`,
  );
  return data.entries.map((e) => ({
    time: String(e.time ?? "--:--"),
    agent: String(e.agent ?? ""),
    message: String(e.text ?? ""),
  }));
}

export function fetchFeedbackLoop(_releaseId: string): Promise<FeedbackItem[]> {
  // No real feedback-loop data source exists on the backend yet (the
  // /audit endpoint's `feedback` field is currently always []) — surface an
  // empty list honestly rather than show the old mock's illustrative entry.
  return Promise.resolve([]);
}

export interface AskAnswer {
  markdown: string;
  agentsConsulted: string[];
}

/**
 * Drill-down Q&A against an already-completed run — e.g. "Which Tier-1
 * tests were prevented from being downgraded during scoring?". Backed by
 * POST /api/v1/agents/ask, which reads only from the cached pipeline state
 * (RiskTierMasterOrchestrator.answer_agent_question) and auto-routes to
 * whichever specialist agent(s) the question is actually about — no agent
 * needs to be picked here, and no pipeline re-run or LLM call happens.
 */
export async function askQuestion(releaseId: string, question: string): Promise<AskAnswer> {
  const res = await fetch(`${API_BASE_URL}/api/v1/agents/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ release_id: releaseId, question }),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Question failed (${res.status})${body ? ` — ${body}` : ""}`);
  }
  const data = (await res.json()) as { markdown?: unknown; agents_consulted?: unknown };
  return {
    markdown: String(data.markdown ?? ""),
    agentsConsulted: Array.isArray(data.agents_consulted) ? data.agents_consulted.map(String) : [],
  };
}

