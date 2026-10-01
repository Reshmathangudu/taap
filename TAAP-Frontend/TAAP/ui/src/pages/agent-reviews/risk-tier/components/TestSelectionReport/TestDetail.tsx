import type { TestCase } from "../../types/testCase";
import { CLASSIFICATION_LABEL } from "../../types/testCase";
import { dispatchNavigateToSignoff } from "../../lib/aguiEvents";

interface Props {
  test: TestCase;
  onBack: () => void;
}

function factorColor(sev: string): string {
  if (sev === "danger") return "var(--danger-strong)";
  if (sev === "warn") return "var(--warn-strong)";
  return "var(--success-strong)";
}

export default function TestDetail({ test, onBack }: Props) {
  const exclusion = test.exclusion;

  return (
    <>
      <h1>{test.id} — {test.name}</h1>
      <p className="rta-ts-subtitle">
        {test.module} · Tier {test.tier} · {CLASSIFICATION_LABEL[test.classification]}
      </p>

      <div className="panel">
        <div className="detail-head">
          <h3 style={{ margin: 0 }}>
            Composite risk score <span className="muted">(BR-SEL-01)</span>
          </h3>
          <div className="detail-score">{test.score.toFixed(1)}<small>/100</small></div>
        </div>

        {test.factors.map(([label, desc, pct, sev]) => (
          <div className="factor" key={label}>
            <div className="factor-row"><span>{label}</span><span>{desc}</span></div>
            <div className="factor-track">
              <div className="factor-fill" style={{ width: `${pct}%`, background: factorColor(sev) }} />
            </div>
          </div>
        ))}

        {test.flags.length > 0 && (
          <div style={{ marginTop: 10 }}>
            {test.flags.map((f) => <span key={f} className="badge flag">{f}</span>)}
          </div>
        )}

        <div className="rationale-box" dangerouslySetInnerHTML={{ __html: test.rationale }} />
      </div>

      {exclusion && (
        <div className="panel">
          <h3>Exclusion risk statement <span className="muted">(BR-GOV-01)</span></h3>
          <div className="stat-row">
            <div><span>Likelihood</span><strong>{exclusion.likelihood}</strong></div>
            <div><span>Business impact</span><strong>{exclusion.impact}</strong></div>
            <div>
              <span>Residual risk</span>
              <span className={"badge risk-" + exclusion.residual}>
                {exclusion.residual.charAt(0).toUpperCase() + exclusion.residual.slice(1)}
              </span>
            </div>
          </div>
          <div className="signoff-row">
            <span style={{ fontSize: 12, color: "var(--text-2)" }}>
              {exclusion.status === "none"
                ? "No sign-off required"
                : `Requires: ${exclusion.signoff} — ${exclusion.status === "pending" ? "pending" : "signed"}`}
            </span>
            {exclusion.status === "pending" && (
              <button
                className="btn sm primary"
                onClick={() => dispatchNavigateToSignoff(test.id)}
              >
                Send to Exclusion Sign-off panel →
              </button>
            )}
          </div>
          <p style={{ fontSize: 11, color: "var(--text-3)", margin: "10px 0 0" }}>
            This panel does not host the sign-off queue itself (that lives in the
            separate Exclusion Sign-off AGUI component). The button above only
            dispatches an <code>agui:navigate-to-signoff</code> event carrying this
            test's id — see <code>src/lib/aguiEvents.ts</code>.
          </p>
        </div>
      )}

      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn" onClick={onBack}>← Back to classification list</button>
      </div>
    </>
  );
}
