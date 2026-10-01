import type { AuditEntry, FeedbackItem } from "../types/testCase";

const AUDIT_LOG: AuditEntry[] = [
  { time: "09:00", agent: "Orchestrator", message: "Release scope frozen. Sequencing sub-agents 1–4 in dependency order (BR-ORC-01)." },
  { time: "09:14", agent: "Change Impact", message: "Resolved 8 epics → 78 test cases via RTM. 12 unlinked PRs logged to Out-of-Scope Change Log." },
  { time: "09:22", agent: "Criticality", message: "Published Criticality Tier Matrix — 24 modules, 0 downgrades." },
  { time: "09:31", agent: "Historical Intelligence", message: "TC-410 flagged High Value — Do Not Exclude (BR-HIST-01, defect DEF-3321)." },
  { time: "09:31", agent: "Risk Appetite", message: "Major-release profile applied. 18 test cases loaded to Regulatory Must-Test List." },
  { time: "09:40", agent: "Scoring", message: "TC-410 classified Must-Test — Reason: BR-HIST-01 Defect-Catch Protection (score 8.9 would not independently qualify)." },
  { time: "09:41", agent: "Scoring", message: "TC-410 exclusion flagged by initial composite, then overridden to Must-Test by defect-catch protection — resolution logged per BR-ORC-03." },
  { time: "09:52", agent: "Governance", message: "TC-802 Exclusion Risk Statement generated — residual risk Low, no sign-off required." },
  { time: "10:05", agent: "Governance", message: "TC-845 rated High residual risk — routed to Business Owner sign-off queue. Suite finalization blocked (GR-GOV-01)." },
];

const FEEDBACK: FeedbackItem[] = [
  {
    title: "Missed exclusion — R25.3",
    body: 'TC-802 was excluded, but a related cosmetic defect escalated to a customer complaint 10 days post-release. TC-802 reweighted to "High Value" for the next 6 releases and fed back to the Historical Execution Intelligence Agent.',
  },
];

export function fetchAuditLog(): Promise<AuditEntry[]> {
  return Promise.resolve(AUDIT_LOG);
}

export function fetchFeedbackLoop(): Promise<FeedbackItem[]> {
  return Promise.resolve(FEEDBACK);
}
