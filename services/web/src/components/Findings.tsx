import type { Finding, Verdict } from "../api/types";
import { STATUS_WORD } from "../lib/format";
import { Mark } from "./Mark";

/** Most severe first, so what must change is read before what passed. */
const SEVERITY = { unmet: 0, cannot_determine: 1, met: 2, not_applicable: 3 } as const;

/** One row per requirement on a shared grid: mark, id, what was checked + the quoted clause, status. */
export function Findings({ findings, verdict }: { findings: Finding[]; verdict: Verdict | null }) {
  if (findings.length === 0) {
    return (
      <p className="empty">
        No findings: the run stopped before research, so nothing was checked against the regulations. The route
        and its reason above say why.
      </p>
    );
  }
  const checks = new Map(verdict?.checks.map((c) => [c.requirement_id, c]) ?? []);
  const counts = (["unmet", "cannot_determine", "met", "not_applicable"] as const)
    .map((s) => [s, findings.filter((f) => f.status === s).length] as const)
    .filter(([, n]) => n > 0);
  return (
    <>
    <p className="findings__summary">
      {counts.map(([s, n]) => (
        <span key={s} className="findings__count"><Mark kind={s} /> {n} {STATUS_WORD[s]!.toLowerCase()}</span>
      ))}
      <span className="findings__verdict">
        Verifier: {verdict?.action === "accept" ? "every citation resolves to retrieved text" : verdict?.escalation_reason ?? verdict?.action ?? "not run"}
      </span>
    </p>
    <ol className="findings">
      {[...findings].sort((a, b) => SEVERITY[a.status] - SEVERITY[b.status]).map((f) => {
        const check = checks.get(f.requirement_id);
        return (
          <li key={f.requirement_id} className="finding" data-status={f.status}>
            <Mark kind={f.status} />
            <code className="finding__id">{f.requirement_id}</code>
            <div className="finding__body">
              <h3 className="finding__title">{f.requirement}</h3>
              <p>{f.explanation}</p>
              {f.citations.map((c, i) => (
                <figure key={`${c.passage_id}-${i}`} className="quote">
                  <figcaption>
                    <span className="mono">{c.regulation}</span> · clause <span className="mono">{c.clause_id}</span>
                  </figcaption>
                  <blockquote>{c.quote}</blockquote>
                </figure>
              ))}
              {f.citations.length === 0 && <p className="finding__warn">No citation: this finding is not grounded in retrieved text.</p>}
              {check && !check.supported && (
                <p className="finding__warn">Verifier: {check.reason || "not supported by the retrieved passages"}</p>
              )}
            </div>
            <span className="finding__status">{STATUS_WORD[f.status]}</span>
          </li>
        );
      })}
    </ol>
    </>
  );
}
