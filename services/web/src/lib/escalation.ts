import type { RunResult, RunStatus } from "../api/types";

export type EscalationKind = "incomplete" | "guardrail" | "out_of_scope" | "unverified";

export interface Escalation {
  kind: EscalationKind;
  /** One line: why a person has to decide. */
  title: string;
  /** What that means and what the reviewer should look at. */
  detail: string;
}

/**
 * Why a run went to regulatory-review, in plain words. Read from the result's structured fields only
 * (completeness, input guardrail, scope, verdict), never from free text, so it holds whatever wording
 * the agents use. Null for any other route.
 */
export function escalation(result: RunResult): Escalation | null {
  if (result.routing.route !== "regulatory-review") return null;
  if (!result.complete) {
    return {
      kind: "incomplete", title: "The check did not finish",
      detail: "It hit a time or step limit, or the language model was unavailable, so it stopped without an answer. "
        + "Check the label again later. If it keeps happening, give the run id to the team.",
    };
  }
  if (result.guardrails.some((g) => g.stage === "input" && !g.allowed)) {
    return {
      kind: "guardrail", title: "Some label text reads like instructions to the system",
      detail: "The text in the flagged fields looks like an attempt to steer the checker (prompt injection). "
        + "The system did not act on it and checked nothing further. A reviewer should read those fields on the label.",
    };
  }
  if (result.classification && !result.classification.in_scope) {
    return {
      kind: "out_of_scope", title: "This product category is outside what the system covers",
      detail: `The system only has the rules for the categories in its corpus, not "${result.classification.category}". `
        + "A reviewer checks this label against the regulations directly.",
    };
  }
  return {
    kind: "unverified", title: "The answer could not be verified against the regulation text",
    detail: "The supporting text was not found, the passages conflict, or an exemption may apply. "
      + "The system escalates instead of guessing. The Trace tab shows every search it made and the text it read.",
  };
}

/** Plain-text hand-off for the reviewer: what to open and why. Pasted into chat or email, never rendered as HTML. */
export function handoffText(status: RunStatus, result: RunResult, traceUrl: string): string {
  const esc = escalation(result);
  return [
    "FSSAI label check: needs regulatory review",
    `Product: ${status.request?.label.product_name ?? "(not recorded)"}`,
    `Why: ${esc?.title ?? result.routing.reason}`,
    `System reason: ${result.routing.reason}${result.routing.escalation_reason ? ` (${result.routing.escalation_reason})` : ""}`,
    `Run: ${status.run_id}`,
    `Correlation id: ${status.correlation_id ?? result.correlation_id}`,
    `Trace: ${traceUrl}`,
  ].join("\n");
}
