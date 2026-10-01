import { useEffect, useRef, useState } from "react";
import type { TestCase } from "../../types/testCase";

interface Props {
  test: TestCase;
  submitting: boolean;
  noteError: boolean;
  submitError?: string | null;
  onCancel: () => void;
  onConfirm: (role: string, note: string) => void;
}

export default function SignoffModal({ test, submitting, noteError, submitError, onCancel, onConfirm }: Props) {
  const exclusion = test.exclusion!;
  const [role, setRole] = useState("QA Lead");
  const noteRef = useRef<HTMLTextAreaElement>(null);

  const residualLabel = exclusion.residual.charAt(0).toUpperCase() + exclusion.residual.slice(1);

  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") onCancel(); }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return (
    <div className="modal-overlay open" onClick={(e) => { if (e.target === e.currentTarget) onCancel(); }}>
      <div className="modal">
        <h4>Sign off exclusion</h4>
        <p className="sub">{test.id} — residual risk: {residualLabel} — requires {exclusion.signoff}</p>

        <label htmlFor="signoffRole">Approving as</label>
        <select id="signoffRole" value={role} onChange={(e) => setRole(e.target.value)}>
          <option>QA Lead</option>
          <option>Business Owner</option>
        </select>

        <label htmlFor="signoffNote">Approval note (required for audit log)</label>
        <textarea id="signoffNote" ref={noteRef} rows={3} placeholder="Reason for approving this exclusion" />
        {noteError && <p className="error-text show">Enter an approval note before signing off.</p>}
        {submitError && <p className="error-text show">{submitError}</p>}

        <div className="modal-actions">
          <button className="btn" onClick={onCancel}>Cancel</button>
          <button
            className="btn primary"
            disabled={submitting}
            onClick={() => onConfirm(role, noteRef.current?.value.trim() ?? "")}
          >
            Confirm sign-off
          </button>
        </div>
      </div>
    </div>
  );
}
