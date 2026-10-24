import { useEffect, useState } from "react";

import { getReadiness } from "../api/client";
import type { Readiness } from "../api/types";
import type { View } from "../lib/useHashRoute";
import { Mark } from "./Mark";

export function Header({ view }: { view: View }) {
  const [ready, setReady] = useState<Readiness | null | undefined>(undefined);

  useEffect(() => {
    const abort = new AbortController();
    const check = () => getReadiness(abort.signal).then((r) => { if (!abort.signal.aborted) setReady(r); });
    void check();
    const timer = setInterval(check, 15_000);
    return () => { abort.abort(); clearInterval(timer); };
  }, []);

  const detail = ready === undefined ? "Checking the API…" : ready === null ? "API unreachable"
    : ready.ready ? `API ready · ${ready.checks.dispatch?.detail.split(" (")[0] ?? ""}`
    : `API not ready · ${Object.values(ready.checks).filter((c) => !c.ok).map((c) => c.detail).join("; ")}`;

  return (
    <header className="shell">
      <a className="shell__wordmark" href="#/">FSSAI Label Check</a>
      <nav aria-label="Main">
        <a href="#/" aria-current={view.name === "check" ? "page" : undefined}>New check</a>
        <a href="#/runs" aria-current={view.name === "runs" ? "page" : undefined}>Recent runs</a>
        <a href="/docs" target="_blank" rel="noreferrer">API docs</a>
      </nav>
      <p className="shell__api" role="status" title={detail}>
        <Mark kind={ready === undefined ? "pending" : ready?.ready ? "done" : "error"} />
        <span>{detail}</span>
      </p>
    </header>
  );
}
