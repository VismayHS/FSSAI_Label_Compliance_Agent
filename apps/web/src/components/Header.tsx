import type { Readiness } from "../api/types";
import type { View } from "../lib/useHashRoute";
import { Mark } from "./Mark";

export function Header({ view, ready }: { view: View; ready: Readiness | null | undefined }) {
  // Plain words on the bar; the technical detail (queue, store) is in the tooltip for whoever runs it.
  const detail = ready ? Object.entries(ready.checks).map(([k, c]) => `${k}: ${c.detail}`).join("; ") : "";
  const label = ready === undefined ? "Checking the service…" : ready === null ? "API unreachable"
    : ready.ready ? "Service ready"
    : `Service not ready: ${Object.values(ready.checks).filter((c) => !c.ok).map((c) => c.detail).join("; ")}`;

  return (
    <header className="shell">
      <a className="shell__wordmark" href="#/">FSSAI Label Check</a>
      <nav aria-label="Main">
        <a href="#/" aria-current={view.name === "check" ? "page" : undefined}>New check</a>
        <a href="#/runs" aria-current={view.name === "runs" ? "page" : undefined}>Recent runs</a>
        <a href="#/review" aria-current={view.name === "review" ? "page" : undefined}>Review queue</a>
        <a href="/docs" target="_blank" rel="noreferrer">API docs</a>
      </nav>
      <p className="shell__api" role="status" title={detail || label}>
        <Mark kind={ready === undefined ? "pending" : ready?.ready ? "done" : "error"} />
        <span>{label}</span>
      </p>
    </header>
  );
}
