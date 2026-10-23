import { useState } from "react";

import { Header } from "./components/Header";
import { RecentRuns } from "./components/RecentRuns";
import { RequestPanel } from "./components/RequestPanel";
import { RunPanel } from "./components/RunPanel";
import { useHashRoute } from "./lib/useHashRoute";

export default function App() {
  const [view, go] = useHashRoute();
  const [submitted, setSubmitted] = useState<string | null>(null);
  const open = (runId: string) => {
    setSubmitted(runId);
    go({ name: "check", runId });
  };
  return (
    <>
      <a className="skip-link" href="#main">Skip to the check</a>
      <Header view={view} />
      <main id="main" className={view.name === "runs" ? "layout layout--single" : "layout"}>
        {view.name === "runs" ? (
          <RecentRuns />
        ) : (
          <>
            <RequestPanel onAccepted={open} />
            <RunPanel runId={view.runId} focus={submitted === view.runId} onAccepted={open} />
          </>
        )}
      </main>
    </>
  );
}
