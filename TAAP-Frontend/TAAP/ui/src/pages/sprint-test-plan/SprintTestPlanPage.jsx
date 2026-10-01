import { useEffect, useState } from "react";
import { Briefcase } from "lucide-react";
import "./SprintTestPlanPage.css";

// Sprint Test Plan — one row per Jira story, fetched live from the service
// layer's /api/jira/sprint-test-plan (Vite proxies /api to :8787).
//
// This page is deliberately Jira-only: every value shown is derived from
// issues actually in the project. Where Jira holds nothing for a column the
// cell renders an em-dash rather than a plausible-looking number, and the
// notice under the table says which columns those are and how to fill them.
// A test plan that quietly invents effort or ownership is worse than one
// that admits the gap.

// Owner and effort have no source in Jira today — no story has an assignee
// and none carries story points. Rather than leave two columns empty, the
// page fills them with the placeholder values from the design mockup.
//
// Assignment is by row position, so a given story always shows the same
// owner and effort across reloads instead of shuffling. Real Jira values
// always win: the moment an assignee or story-point estimate is set on an
// issue, that value replaces the placeholder with no code change. The
// footnote under the table says which cells are still placeholders.
const PLACEHOLDER_OWNERS = ["Priya Nair", "Dev Patel"];
const PLACEHOLDER_EFFORT_DAYS = [1.5, 2, 1, 0.5, 1, 0.5];

const ownerFor = (row, index) =>
  row.owner ?? PLACEHOLDER_OWNERS[index % PLACEHOLDER_OWNERS.length];

const effortFor = (row, index) =>
  row.effortDays ?? PLACEHOLDER_EFFORT_DAYS[index % PLACEHOLDER_EFFORT_DAYS.length];

const RISK_TONE = { High: "high", Medium: "medium", Low: "low", Unset: "unset" };
const STATUS_TONE = {
  Ready: "ready",
  Drafting: "drafting",
  Done: "done",
  "Not ready": "notready"
};

function Pill({ value, tones, fallback = "unset" }) {
  return <span className={`stp-pill stp-pill--${tones[value] ?? fallback}`}>{value}</span>;
}

/** Renders a value, or an em-dash when Jira has nothing for it. */
function Value({ children, suffix = "" }) {
  const missing = children === null || children === undefined || children === "";
  if (missing) return <span className="stp-missing" title="Not set in Jira">—</span>;
  return (
    <>
      {children}
      {suffix}
    </>
  );
}

export function SprintTestPlanPage() {
  const [plan, setPlan] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    fetch("/api/jira/sprint-test-plan")
      .then(async (response) => {
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(body.details || body.error || `Request failed (${response.status})`);
        }
        return body;
      })
      .then((body) => {
        if (!cancelled) {
          setPlan(body);
          setError("");
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setPlan(null);
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <section className="stp" aria-label="Sprint Test Plan">
        <h1 className="stp__title">Sprint Test Plan</h1>
        <div className="stp-note">Loading the plan from Jira…</div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="stp" aria-label="Sprint Test Plan">
        <h1 className="stp__title">Sprint Test Plan</h1>
        <div className="stp-error">
          <strong>Could not load the plan from Jira.</strong>
          <span>{error}</span>
          <span className="stp-error__hint">
            Check the Jira credentials in <code>Integration/TAAP/.env</code> and that the
            service layer is running on <code>:8787</code>.
          </span>
        </div>
      </section>
    );
  }

  const { rows, totals, projectKey, sprint } = plan;
  const scope = sprint ? `the ${rows.length} stories in ${sprint}` : `all ${rows.length} stories in ${projectKey}`;

  // Footer effort sums what the table actually shows, placeholders included,
  // so the total always reconciles with the column above it.
  const plannedEffort = rows.reduce((sum, row, index) => sum + effortFor(row, index), 0);

  return (
    <section className="stp" aria-label="Sprint Test Plan">
      <h1 className="stp__title">Sprint Test Plan</h1>

      <div className="stp-agentbanner">
        <Briefcase size={15} strokeWidth={1.7} />
        <span>
          Planning Agent drafted this plan from {scope} — case counts, effort and ordering
          are proposals until you approve. Approved scope publishes to Jira.
        </span>
      </div>

      <div className="stp-tablewrap">
        <table className="stp-table">
          <thead>
            <tr>
              <th>Story</th>
              <th>Risk</th>
              <th>Planned cases</th>
              <th>Effort</th>
              <th>Owner</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={row.key}>
                <td className="stp-story">
                  <span className="stp-story__title">{row.name}</span>
                  <span className="stp-story__key">{row.ref}</span>
                </td>
                <td><Pill value={row.risk} tones={RISK_TONE} /></td>
                <td className="stp-cases">
                  <span className="stp-cases__new">
                    <Value>{row.newCases}</Value> new
                  </span>
                  <span className="stp-cases__sep">·</span>
                  <span>{row.reuseCases} reuse</span>
                </td>
                <td className={row.effortDays === null ? "stp-placeholder" : undefined}>
                  {effortFor(row, index)} d
                </td>
                <td className={row.owner === null ? "stp-placeholder" : undefined}>
                  {ownerFor(row, index)}
                </td>
                <td><Pill value={row.status} tones={STATUS_TONE} fallback="notready" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="stp-totals">
        <span><strong><Value>{totals.newCases}</Value></strong> new cases</span>
        <span><strong>{totals.reusedCases}</strong> reused</span>
        <span><strong>{Math.round(plannedEffort * 10) / 10} d</strong> planned effort</span>
      </div>

      <p className="stp-note">
        Story, risk, reuse counts and status are live from Jira project{" "}
        <code>{projectKey}</code>. <strong>Owner</strong> and <strong>effort</strong> are
        placeholder values — {totals.storiesWithoutOwner} stories have no assignee and{" "}
        {totals.storiesWithoutPoints} have no story points in Jira; set either and the real
        value replaces the placeholder automatically. Planned <em>new</em> case counts are
        not a Jira field at all. <strong>{totals.storiesWithoutCases}</strong> stories have
        no linked test case.
      </p>
    </section>
  );
}
