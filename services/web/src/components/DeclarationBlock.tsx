import type { ReactNode } from "react";

import type { RunResult, RunStatus } from "../api/types";
import { ms, ROUTE_LABEL, usd } from "../lib/format";
import { Mark } from "./Mark";

/** The result opens like a pack's declaration block: a ruled table of label / value rows. */
export function DeclarationBlock({ status, result }: { status: RunStatus; result: RunResult }) {
  const { routing, classification, totals } = result;
  const claims = classification?.claims ?? [];
  const flags = result.guardrails.flatMap((g) => g.flags);
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
        {row("Route", (
          <span className="decl__route">
            <Mark kind={routing.route} size="lg" />
            <span>
              <strong className="decl__route-name">{routing.route}</strong>
              <span className="decl__route-help">{ROUTE_LABEL[routing.route]}</span>
            </span>
          </span>
        ), "decl__route-row")}
        {row("Reason", routing.reason)}
        {routing.escalation_reason && row("Escalation", <strong>{routing.escalation_reason}</strong>)}
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
