import type { TestCase } from "../types/testCase";

// Sample data carried over from the HTML prototype (R25.4 major release).
// In production this array disappears entirely — TestSelectionReport and
// ExclusionSignoffQueue each call their own endpoint on the Risk-Based
// Test Selection & Scoring Agent / Exclusion Risk & Governance Agent.
const TESTS: TestCase[] = [
  {
    id: "TC-410", name: "Payment auth — 3D secure retry", module: "Payments — Domestic Transfer", tier: 1, classification: "must", score: 8.9,
    factors: [
      ["Change impact", "High — directly changed", 90, "danger"],
      ["Criticality", "Tier 1 floor", 100, "danger"],
      ["Historical reliability", "Defect-catch protected", 95, "danger"],
      ["Risk appetite adjustment", "No dampening applied", 50, "warn"],
    ],
    flags: ["Defect-catch protection", "Tier 1 floor"],
    rationale: "Must-Test — Reason: <code>BR-HIST-01</code> Defect-Catch Protection (caught DEF-3321, Sev-2, R24.2). Also independently qualifies under <code>BR-CRIT-02</code> Tier 1 floor. Protections combine via OR logic (<code>BR-SEL-02</code>) — never averaged away.",
  },
  {
    id: "TC-411", name: "AML transaction monitoring — high value transfer", module: "Payments — Compliance", tier: 1, classification: "must", score: 9.4,
    factors: [
      ["Change impact", "Not changed this release", 10, "success"],
      ["Criticality", "Tier 1 floor", 100, "danger"],
      ["Historical reliability", "Stable, no defects", 20, "success"],
      ["Risk appetite adjustment", "Regulatory override", 100, "danger"],
    ],
    flags: ["Regulatory — non-negotiable"],
    rationale: "Must-Test — Reason: <code>BR-RISK-01</code> Regulatory Non-Negotiable. Executes every release regardless of change footprint, history, or score. Cannot be removed by any agent (<code>GR-RISK-01</code>).",
  },
  {
    id: "TC-450", name: "International Payments — cross-border FX conversion", module: "Payments — International", tier: 2, classification: "must", score: 7.8,
    factors: [
      ["Change impact", "New epic, first release", 100, "danger"],
      ["Criticality", "Tier 2", 65, "warn"],
      ["Historical reliability", "No history — new feature", 50, "warn"],
      ["Risk appetite adjustment", "New feature override", 100, "danger"],
    ],
    flags: ["New feature — full coverage"],
    rationale: "Must-Test — Reason: <code>BR-CHG-05</code> New Feature Full-Coverage Rule. Newly introduced epic with no prior test cases; exempt from any exclusion scoring in its first release (<code>GR-CHG-02</code>).",
  },
  {
    id: "TC-415", name: "Checkout session — concurrent cart lock", module: "Checkout", tier: 1, classification: "must", score: 7.6,
    factors: [
      ["Change impact", "High — directly changed", 76, "danger"],
      ["Criticality", "Tier 1", 90, "danger"],
      ["Historical reliability", "2 failures in 10 runs", 42, "warn"],
      ["Risk appetite adjustment", "Major release, full breadth", 70, "warn"],
    ],
    flags: [],
    rationale: "Must-Test — Reason: <code>BR-SEL-01</code> Weighted Composite Score. High change impact combined with Tier 1 criticality produces a qualifying composite score without needing a protection flag.",
  },
  {
    id: "TC-901", name: "Beneficiary nickname validation — new field", module: "Beneficiary Management", tier: 2, classification: "must", score: 6.0,
    factors: [
      ["Change impact", "Medium — linked change", 55, "warn"],
      ["Criticality", "Tier 2", 60, "warn"],
      ["Historical reliability", "Insufficient — 1 execution", 50, "warn"],
      ["Risk appetite adjustment", "Defaults to inclusion", 60, "warn"],
    ],
    flags: ["Insufficient history — defaults to inclusion"],
    rationale: "Must-Test — Reason: <code>BR-HIST-05</code> Insufficient History Rule. Fewer than 3 historical executions; treated as 'Unknown Reliability' and defaults to inclusion, not exclusion (<code>GR-HIST-02</code>).",
  },
  {
    id: "TC-501", name: "Refund partial amount", module: "Payments — Refunds", tier: 2, classification: "rec", score: 5.2,
    factors: [
      ["Change impact", "Medium", 48, "warn"],
      ["Criticality", "Tier 2", 50, "warn"],
      ["Historical reliability", "Reliable, low value", 30, "success"],
      ["Risk appetite adjustment", "Standard major-release breadth", 40, "warn"],
    ],
    flags: [],
    rationale: "Recommended — moderate composite score under Tier 2. No protection flag triggered; included to meet the Tier 2 ≥70% regression floor (<code>BR-CRIT-03</code>).",
  },
  {
    id: "TC-502", name: "Checkout summary — tax recalculation", module: "Checkout", tier: 2, classification: "rec", score: 4.8,
    factors: [
      ["Change impact", "Medium", 44, "warn"],
      ["Criticality", "Tier 2", 50, "warn"],
      ["Historical reliability", "Reliable, low value", 28, "success"],
      ["Risk appetite adjustment", "Standard major-release breadth", 38, "warn"],
    ],
    flags: [],
    rationale: "Recommended — moderate composite score. Contributes toward the Tier 2 mandatory regression floor for this release.",
  },
  {
    id: "TC-503", name: "Order confirmation email trigger", module: "Notifications", tier: 3, classification: "opt", score: 4.1,
    factors: [
      ["Change impact", "Low", 25, "success"],
      ["Criticality", "Tier 3", 35, "success"],
      ["Historical reliability", "Flaky — 3 of 10 runs", 50, "warn"],
      ["Risk appetite adjustment", "Tier 3, risk-based", 30, "success"],
    ],
    flags: ["Flaky — routed to stabilization, not scored as risk"],
    rationale: "Optional — Reason: <code>BR-HIST-03</code> Flaky Test Neutral Rule. Flakiness is excluded from the reliability score calculation and cannot itself justify exclusion (<code>GR-HIST-03</code>); routed to the automation stabilization backlog instead.",
  },
  {
    id: "TC-820", name: "Legacy invoice export", module: "Billing", tier: 3, classification: "opt", score: 3.2,
    factors: [
      ["Change impact", "None", 5, "success"],
      ["Criticality", "Tier 3", 30, "success"],
      ["Historical reliability", "Flaky — 2 of 10 runs", 55, "warn"],
      ["Risk appetite adjustment", "Tier 3, risk-based", 25, "success"],
    ],
    flags: ["Flaky — routed to stabilization, not scored as risk"],
    rationale: "Optional — low change relevance and Tier 3 criticality, but flakiness prevents an Exclude classification per <code>GR-HIST-03</code>. Held at Optional pending stabilization.",
    exclusion: { likelihood: "Medium", impact: "Billing report inaccuracy, no customer-facing impact", residual: "medium", signoff: "QA Lead", status: "pending" },
  },
  {
    id: "TC-802", name: "Currency label formatting", module: "Checkout — UI", tier: 4, classification: "exclude", score: 1.4,
    factors: [
      ["Change impact", "None", 4, "success"],
      ["Criticality", "Tier 4", 10, "success"],
      ["Historical reliability", "100% pass, 15 runs, zero defects", 5, "success"],
      ["Risk appetite adjustment", "Tier 4, high tolerance", 8, "success"],
    ],
    flags: [],
    rationale: "Exclude — Reason: <code>BR-SEL-03</code> Unchanged + Low-Criticality + Reliable. No code change this release, Tier 4, and a clean 15-run history with zero linked defects.",
    exclusion: { likelihood: "Low", impact: "Cosmetic only", residual: "low", signoff: "Not required", status: "none" },
  },
  {
    id: "TC-830", name: "Cart empty state rendering", module: "Checkout — UI", tier: 4, classification: "exclude", score: 1.1,
    factors: [
      ["Change impact", "None", 3, "success"],
      ["Criticality", "Tier 4", 8, "success"],
      ["Historical reliability", "100% pass, 15 runs, zero defects", 4, "success"],
      ["Risk appetite adjustment", "Tier 4, high tolerance", 6, "success"],
    ],
    flags: [],
    rationale: "Exclude — Reason: <code>BR-SEL-03</code>. No change relevance, lowest criticality tier, clean history — meets the Stale/Zero-Failure Candidate criteria from the Historical Intelligence Agent.",
    exclusion: { likelihood: "Low", impact: "Cosmetic only", residual: "low", signoff: "Not required", status: "none" },
  },
  {
    id: "TC-840", name: "Beneficiary limits — sub-flow negative path", module: "Beneficiary Management", tier: 2, classification: "exclude", score: 3.6,
    factors: [
      ["Change impact", "Low — unrelated sub-flow", 20, "success"],
      ["Criticality", "Tier 2", 55, "warn"],
      ["Historical reliability", "Reliable, low value", 22, "success"],
      ["Risk appetite adjustment", "Tier 2, moderate tolerance", 30, "success"],
    ],
    flags: [],
    rationale: "Exclude — scoped correctly per <code>BR-CHG-04</code>; this release's change only affects the OTP retry-limit sub-flow, not this negative-path case. Composite score qualifies for exclusion within Tier 2's 25% cap.",
    exclusion: { likelihood: "Medium", impact: "Possible customer complaint if limit enforcement regresses", residual: "medium", signoff: "QA Lead", status: "pending" },
  },
  {
    id: "TC-845", name: "Payment auth — adjacent fallback path", module: "Payments — Domestic Transfer", tier: 1, classification: "exclude", score: 4.9,
    factors: [
      ["Change impact", "Low — adjacent, not directly changed", 35, "success"],
      ["Criticality", "Tier 1-adjacent", 70, "warn"],
      ["Historical reliability", "Reliable, no defects", 25, "success"],
      ["Risk appetite adjustment", "Tier 1 proximity caution", 45, "warn"],
    ],
    flags: [],
    rationale: "Exclude — composite score qualifies, but Tier 1 adjacency raises residual risk to High. Requires both QA Lead and Business Owner sign-off before finalization (<code>BR-GOV-02</code>); release cannot ship 'Test Selection Approved' while this remains unsigned (<code>GR-GOV-01</code>).",
    exclusion: { likelihood: "Medium", impact: "Tier 1-adjacent — payment flow proximity", residual: "high", signoff: "QA Lead + Business Owner", status: "pending" },
  },
  {
    id: "TC-846", name: "Payment auth — retry counter reset", module: "Payments — Domestic Transfer", tier: 1, classification: "exclude", score: 5.1,
    factors: [
      ["Change impact", "Low — adjacent, not directly changed", 38, "success"],
      ["Criticality", "Tier 1-adjacent", 72, "warn"],
      ["Historical reliability", "Reliable, no defects", 28, "success"],
      ["Risk appetite adjustment", "Tier 1 proximity caution", 48, "warn"],
    ],
    flags: [],
    rationale: "Exclude — same Tier 1 proximity pattern as TC-845. Residual risk rated High; blocked from finalization until Business Owner sign-off is recorded.",
    exclusion: { likelihood: "Medium", impact: "Tier 1-adjacent — payment flow proximity", residual: "high", signoff: "QA Lead + Business Owner", status: "pending" },
  },
];

// Shaped as an async "fetch" on purpose: TestSelectionReport and
// ExclusionSignoffQueue call these as if they were network requests, so
// swapping in a real `fetch("/agui/risk-tier/test-selection")` call (or an
// MSW-mocked one, or a TanStack Query hook wrapping it) later is a one-line
// change at the call site, not a component rewrite.
export function fetchAllTests(): Promise<TestCase[]> {
  return Promise.resolve(TESTS.map((t) => ({ ...t })));
}

export function fetchPendingExclusions(): Promise<TestCase[]> {
  return Promise.resolve(
    TESTS.filter((t) => t.exclusion && t.exclusion.status === "pending").map((t) => ({ ...t, exclusion: { ...t.exclusion! } }))
  );
}

export function submitSignoff(testId: string, _role: string, _note: string): Promise<{ ok: true }> {
  const t = TESTS.find((x) => x.id === testId);
  if (t?.exclusion) t.exclusion.status = "signed";
  return Promise.resolve({ ok: true });
}
