// Shared data shapes for the Risk Tier Agent AGUI components.
//
// These mirror what the Risk-Based Test Selection & Scoring Agent and the
// Exclusion Risk & Governance Agent are expected to publish at their AGUI
// endpoints (see Section 6 "Agent Card & Endpoint Design" of the
// architecture document). Keeping the types in one shared module — rather
// than duplicating them per component — means all three panels agree on
// the shape of the data even though they never share state directly.

export type Classification = "must" | "rec" | "opt" | "exclude";

export type FactorSeverity = "danger" | "warn" | "success";

/** [label, description, percent 0-100, severity] */
export type Factor = [string, string, number, FactorSeverity];

export type ResidualRisk = "low" | "medium" | "high";

export type SignoffStatus = "none" | "pending" | "signed";

export interface ExclusionStatement {
  likelihood: string;
  impact: string;
  residual: ResidualRisk;
  /** Who must sign off, e.g. "QA Lead" or "QA Lead + Business Owner" */
  signoff: string;
  status: SignoffStatus;
}

export interface TestCase {
  id: string;
  name: string;
  module: string;
  tier: 1 | 2 | 3 | 4;
  classification: Classification;
  score: number;
  factors: Factor[];
  flags: string[];
  /** HTML-safe rationale string; may contain <code> rule-id tags */
  rationale: string;
  exclusion?: ExclusionStatement;
}

export interface AuditEntry {
  time: string;
  agent: string;
  message: string;
}

export interface FeedbackItem {
  title: string;
  body: string;
}

export const CLASSIFICATION_LABEL: Record<Classification, string> = {
  must: "Must-test",
  rec: "Recommended",
  opt: "Optional",
  exclude: "Exclude",
};
