import { createPortal } from "react-dom";

import type { RunResult, RunStatus } from "../api/types";
import { escalation, extraEscalationReason } from "../lib/escalation";
import { STATUS_WORD, time } from "../lib/format";
import { whatItMeans } from "./DeclarationBlock";
import { SEVERITY } from "./Findings";

/**
 * The findings as one printable document (extra: PDF export). Hidden on screen; "Save as PDF" prints it alone.
 * Every finding is listed whatever the on-screen filter, most severe first, each with its verbatim citations.
 * Label text is rendered as text, never as markup.
 */
export function PrintReport({ status, result }: { status: RunStatus; result: RunResult }) {
  const { routing } = result;
  const esc = escalation(result);
  const findings = [...result.findings].sort((a, b) => SEVERITY[a.status] - SEVERITY[b.status]);
  const trace = `${window.location.origin}${window.location.pathname}#/runs/${status.run_id}/trace`;
  return createPortal(
    <article className="print-report">
      <h1>FSSAI label compliance finding</h1>
      <p className="print-report__meta">
        {status.request?.label.product_name ?? "Label"} · run {status.run_id} · submitted {time(status.submitted_at)}
      </p>
      <p className="print-report__notice">{result.notice}</p>
      <h2>Recommendation: {routing.route}</h2>
      <p>{whatItMeans(result)}</p>
      <p><strong>Reason given:</strong> {routing.reason}</p>
      {extraEscalationReason(routing) && <p><strong>Escalation:</strong> {extraEscalationReason(routing)}</p>}
      {esc && <p>{esc.detail}</p>}
      {!result.complete && <p><strong>This run did not complete, so it carries no confident answer.</strong></p>}
      <h2>Findings ({findings.length})</h2>
      {findings.length === 0 ? <p>No findings: the run stopped before research.</p> : (
        <ol className="print-report__findings">
          {findings.map((f) => (
            <li key={f.requirement_id}>
              <p><strong>{STATUS_WORD[f.status] ?? f.status}</strong> · {f.requirement} <span className="mono">({f.requirement_id})</span></p>
              <p>{f.explanation}</p>
              {f.citations.map((c, i) => (
                <blockquote key={`${c.passage_id}-${i}`}>
                  <p>&ldquo;{c.quote}&rdquo;</p>
                  <footer>{c.regulation} {c.clause_id}</footer>
                </blockquote>
              ))}
            </li>
          ))}
        </ol>
      )}
      <p className="print-report__meta">Full trace of every step: {trace}</p>
    </article>,
    document.body,
  );
}
