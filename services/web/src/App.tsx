import { useCallback, useState } from "react";

import type { LabelCheckRequest } from "./api/types";

import { Header } from "./components/Header";
import { RecentRuns } from "./components/RecentRuns";
import { RequestPanel } from "./components/RequestPanel";
import { RunPanel } from "./components/RunPanel";
import { useHashRoute } from "./lib/useHashRoute";
import { useReadiness } from "./lib/useReadiness";

export default function App() {
  const [view, go] = useHashRoute();
  const ready = useReadiness();
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [prefill, setPrefill] = useState<{ runId: string; request: LabelCheckRequest } | null>(null);
  const onRequest = useCallback((runId: string, request: LabelCheckRequest) => {
    setPrefill((p) => (p?.runId === runId ? p : { runId, request }));
  }, []);
  const formRun = view.name === "check" && view.runId && prefill?.runId === view.runId ? prefill : null;
  const open = (runId: string) => {
    setSubmitted(runId);
    go({ name: "check", runId });
  };
  return (
    <>
      <a className="skip-link" href="#main">Skip to the check</a>
      <Header view={view} ready={ready} />
      <main id="main" className={view.name === "runs" ? "layout layout--single" : "layout"}>
        {view.name === "runs" ? (
          <RecentRuns />
        ) : (
          <>
            <RequestPanel initialKey={formRun?.runId ?? "new"} initial={formRun?.request} onAccepted={open} />
            <RunPanel runId={view.runId} focus={submitted === view.runId} onAccepted={open} initialTab={view.tab} onRequest={onRequest} ready={ready} />
          </>
        )}
      </main>
    </>
  );
}
