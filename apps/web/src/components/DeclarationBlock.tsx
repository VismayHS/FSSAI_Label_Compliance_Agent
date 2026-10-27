import { useState, type ReactNode } from "react";

import type { RunResult, RunStatus } from "../api/types";
import { escalation, extraEscalationReason, handoffText } from "../lib/escalation";
import { ms, usd } from "../lib/format";
import { Mark } from "./Mark";

/** This run's outcome in plain words: what the recommendation means and what to do next. */
export function whatItMeans(result: RunResult): string {
  const checked = result.findings.length;
  const attention = result.findings.filter((f) => f.status === "unmet" || f.status === "cannot_determine");
  const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);
  switch (result.routing.route) {
    case "clear-for-print":
      return `All ${checked} ${plural(checked, "requirement", "requirements")} it checked ${plural(checked, "is", "are")} met and every `
        + "quote matched the regulation text. A regulatory professional still signs off.";
    case "revise-and-recheck":
      if (attention.length === 0) return "Fix what is unmet, then check again.";
      return `${attention.length} of ${checked} checked ${plural(checked, "requirement", "requirements")} `
        + `${plural(attention.length, "needs", "need")} attention: ${attention.map((f) => f.requirement).join("; ")}. `
        + `Fix ${plural(attention.length, "it", "them")} on the label, then check again.`;
    default:
      return `${escalation(result)?.title ?? "The system could not answer with confidence"}, so a regulatory affairs `
        + "professional decides. It does not guess.";
  }
}

/** Copies a plain-text hand-off (run id, reason, trace link) for the person who takes over an escalated label. */
function CopyHandoff({ status, result }: { status: RunStatus; result: RunResult }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const copy = async () => {
    const traceUrl = `${window.location.origin}${window.location.pathname}#/runs/${status.run_id}/trace`;
    try {
      await navigator.clipboard.writeText(handoffText(status, result, traceUrl));
      setState("copied");
    } catch {
      setState("failed");
    }
  };
  return (
    <span className="handoff__copy">
      <button type="button" className="button" onClick={copy}>Copy details for the reviewer</button>
      <span role="status" className="handoff__status">
        {state === "copied" ? "Copied: run id, reason and trace link." : state === "failed"
          ? "Copy is blocked in this browser. Select the run id below instead." : ""}
      </span>
    </span>
  );
}

/** The result opens like a pack's declaration block: a ruled table of label / value rows. */
export function DeclarationBlock({ status, result }: { status: RunStatus; result: RunResult }) {
  const { routing, classification, totals } = result;
  const claims = classification?.claims ?? [];
  const flags = result.guardrails.flatMap((g) => g.flags);
  const esc = escalation(result);
  const row = (label: string, value: ReactNode, className?: string) => (
    <tr className={className}>
      <th scope="row">{label}</th>
      <td>{value}</td>
    </tr>
  );
  return (
    <table className="decl" data-route={routing.route}>
      <caption className="visually-hidden">Outcome of this check</caption>
      <colgroup><col className="decl__labels" /><col /></colgroup>
      <tbody>
        {row("Recommendation", (
          <span className="decl__route">
            <Mark kind={routing.route} size="lg" />
            <span>
              <strong className="decl__route-name">{routing.route}</strong>
              <span className="decl__route-help">{whatItMeans(result)}</span>
            </span>
          </span>
        ), "decl__route-row")}
        {row("Reason given", routing.reason)}
        {extraEscalationReason(routing) && row("Escalation", <strong>{extraEscalationReason(routing)}</strong>)}
        {esc && row("What happens next", (
          <div className="handoff">
            <p>{esc.detail}</p>
            <p>A regulatory affairs professional reviews this label. Send them the details:</p>
            <CopyHandoff status={status} result={result} />
          </div>
        ))}
        {flags.length > 0 && row("Guardrails", <ul className="plain">{flags.map((f) => <li key={f} className="mono">{f}</li>)}</ul>)}
        {row("Category", classification
          ? `${classification.category} · ${classification.in_scope ? "in scope" : "outside our corpus"}`
          : "Not classified")}
        {row("Claims", claims.length === 0 ? "None detected" : claims.map((c, i) => (
          <span key={`${c.text}-${i}`} className="decl__claim">
            {c.text}
            <span className="decl__claim-type"> · {c.claim_type.replace(/_/g, " ")}{c.nutrient ? `, ${c.nutrient}` : ""}</span>
          </span>
        )))}
        {row("Run", (
          <span className="decl__run">
            <span className="mono">{status.run_id}</span>
            <span className="num">{totals.steps} steps · {ms(totals.latency_ms)} · {usd(totals.cost_usd)}</span>
          </span>
        ))}
      </tbody>
    </table>
  );
}
