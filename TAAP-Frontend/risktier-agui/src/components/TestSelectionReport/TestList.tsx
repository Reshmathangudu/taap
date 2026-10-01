import type { FilterValue } from "./state";
import type { TestCase } from "../../types/testCase";
import { CLASSIFICATION_LABEL } from "../../types/testCase";

interface Props {
  releaseId: string | null;
  rows: TestCase[];
  total: number;
  filter: FilterValue;
  search: string;
  onFilterChange: (f: FilterValue) => void;
  onSearchChange: (s: string) => void;
  onOpen: (t: TestCase) => void;
}

const FILTERS: { value: FilterValue; label: string }[] = [
  { value: "all", label: "All" },
  { value: "must", label: "Must-test" },
  { value: "rec", label: "Recommended" },
  { value: "opt", label: "Optional" },
  { value: "exclude", label: "Exclude" },
];

export default function TestList({ releaseId, rows, total, filter, search, onFilterChange, onSearchChange, onOpen }: Props) {
  return (
    <>
      <h1>Test case classification{releaseId ? ` — ${releaseId}` : ""}</h1>
      <p className="rta-ts-subtitle">
        Must-Test / Recommended / Optional / Exclude — every classification carries a factor-level rationale (BR-SEL-05).
      </p>

      <div className="rta-ts-toolbar">
        <input
          type="text"
          className="rta-ts-search"
          placeholder="Search test cases by name or ID"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
        {FILTERS.map((f) => (
          <button
            key={f.value}
            className={"rta-ts-chip" + (filter === f.value ? " active" : "")}
            onClick={() => onFilterChange(f.value)}
          >
            {f.label}
          </button>
        ))}
      </div>

      <table>
        <colgroup>
          <col style={{ width: "54%" }} />
          <col style={{ width: "12%" }} />
          <col style={{ width: "22%" }} />
          <col style={{ width: "12%" }} />
        </colgroup>
        <thead>
          <tr>
            <th>Test case</th>
            <th>Tier</th>
            <th>Classification</th>
            <th>Score</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={4} className="empty-row">
                No test cases match "{search}". Try a different search or filter.
              </td>
            </tr>
          ) : (
            rows.map((t) => (
              <tr key={t.id} onClick={() => onOpen(t)}>
                <td data-label="Test case">{t.id} — {t.name}</td>
                <td data-label="Tier"><span className={"badge tier" + t.tier}>Tier {t.tier}</span></td>
                <td data-label="Classification"><span className={"badge " + t.classification}>{CLASSIFICATION_LABEL[t.classification]}</span></td>
                <td data-label="Score">{t.score.toFixed(1)}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
      <p className="footer-note">
        <span>Click a row for the full factor breakdown and rationale.</span>
        <span>{rows.length} of {total} shown</span>
      </p>
    </>
  );
}
