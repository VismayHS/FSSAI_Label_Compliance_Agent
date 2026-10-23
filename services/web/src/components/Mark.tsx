import type { FindingStatus, Route } from "../api/types";

/** The signature: every status is a square pack mark (outlined square, one inner symbol), always next
 * to words. Kinds map to the marks in DESIGN.md. */
export type MarkKind =
  | FindingStatus
  | Route
  | "done"
  | "error"
  | "pending"
  | "running"
  | "skipped";

export function Mark({ kind, size }: { kind: MarkKind; size?: "lg" }) {
  return <span className="mark" data-kind={kind} data-size={size} aria-hidden="true" />;
}
