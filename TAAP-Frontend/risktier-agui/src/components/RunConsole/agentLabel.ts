/**
 * Turns a backend-provided agent id into a readable label using only
 * mechanical string rules (word-boundary splitting + capitalization) — there
 * is deliberately no per-agent name lookup table here, so a future agent id
 * the frontend has never seen renders sensibly with zero code changes.
 *
 * Examples: "agent1" -> "Agent 1", "ledger" -> "Ledger",
 * "feature_change_agent" -> "Feature Change Agent".
 */
export function agentLabel(agentId: string): string {
  const spaced = agentId
    .replace(/[_-]+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/([a-zA-Z])(\d)/g, "$1 $2")
    .replace(/(\d)([a-zA-Z])/g, "$1 $2")
    .trim();

  return spaced
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => (/^\d+$/.test(word) ? word : word.charAt(0).toUpperCase() + word.slice(1)))
    .join(" ");
}
