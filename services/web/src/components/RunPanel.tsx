import { useEffect, useRef, useState } from "react";

import { submitRun } from "../api/client";

import type { RunStatus } from "../api/types";
import { clientId } from "../lib/clientId";
import { SECTION_41_EXAMPLE } from "../lib/example";
import { ms, shortId, time } from "../lib/format";
import { useRun } from "../lib/useRun";
import { AgentStrip } from "./AgentStrip";
import { DeclarationBlock } from "./DeclarationBlock";
import { Findings } from "./Findings";
import LatticeLoader from "./reactbits/LatticeLoader/LatticeLoader";
import { Trace } from "./Trace";

type Tab = "findings" | "trace" | "request";

export function RunPanel({ runId, focus, onAccepted }: { runId: string | null; focus: boolean; onAccepted: (runId: string) => void }) {
  if (!runId) return <EmptyRun onAccepted={onAccepted} />;
  return <RunView key={runId} runId={runId} focus={focus} />;
}

function EmptyRun({ onAccepted }: { onAccepted: (runId: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const runExample = async () => {
    setBusy(true);
    setError(null);
    const outcome = await submitRun(SECTION_41_EXAMPLE, clientId());
    setBusy(false);
    if (outcome.kind === "accepted") onAccepted(outcome.runId);
    else setError(outcome.kind === "error" ? outcome.message : "The example was not accepted. Check it in the form to see why.");
  };
  return (
    <section className="panel run run--empty" aria-labelledby="run-empty-title">
      <h2 id="run-empty-title">Check a label before it goes to print</h2>
      <p className="run__lede">
        Each requirement gets a finding that cites the regulation and clause it rests on, with the quoted words.
        The label is then routed to <strong>clear-for-print</strong>, <strong>revise-and-recheck</strong> or{" "}
        <strong>regulatory-review</strong>.
      </p>
      <AgentStrip steps={null} working={false} />
      <div className="run__example">
        <div>
          <h3>The §4.1 case</h3>
          <p>A pack claims “Source of protein”. Is the claim permitted, given the protein on its nutrition panel? The answer
            sits in the Claims regulation, which the Labelling regulation never points to.</p>
        </div>
        <button type="button" className="button" onClick={runExample} disabled={busy} aria-busy={busy || undefined}>
          {busy ? "Checking…" : "Check the §4.1 example"}
        </button>
      </div>
      {error && <p className="banner" data-tone="error" role="alert">{error}</p>}
      <p className="notice">The service never approves a label for print. A regulatory affairs professional decides.</p>
    </section>
  );
}

function RunView({ runId, focus }: { runId: string; focus: boolean }) {
  const { status, error, reconnecting } = useRun(runId);
  const [tab, setTab] = useState<Tab>("findings");
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (!focus) return;
    heading.current?.focus({ preventScroll: true });
    heading.current?.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, [focus]);

  if (error) {
    return (
      <section className="panel run" aria-live="polite">
        <p className="banner" data-tone="error" role="alert">{error}</p>
        <p><a href="#/">Start a new check</a></p>
      </section>
    );
  }
  const working = !status || status.state === "queued" || status.state === "running";
  const result = status?.result ?? null;

  return (
    <section className="panel run" aria-labelledby="run-title" aria-busy={working || undefined}>
      <div className="run__head">
        <h2 id="run-title" ref={heading} tabIndex={-1}>{status?.request?.label.product_name ?? "Result"}</h2>
        <p className="run__meta">
          Run <code title={runId}>{shortId(runId)}</code>
          {status && <> · submitted {time(status.submitted_at)}</>}
          {status?.correlation_id && <> · correlation <code>{status.correlation_id}</code></>}
        </p>
      </div>

      {reconnecting && <p className="banner" data-tone="warn" role="status">Connection lost. Retrying…</p>}

      {working && (
        <div className="run__waiting" role="status">
          <LatticeLoader status="working" shape="square" grid={3} pattern="arrow" color="var(--path)" glow={false} cellSize={7} gap={2}
            label={status?.state === "running" ? "Agents are checking the label" : "Queued for a worker"} showTimer fontSize={14} />
        </div>
      )}

      {status?.state === "failed" && <FailedRun status={status} />}

      {result && status && (
        <>
          <DeclarationBlock status={status} result={result} />
          {!result.complete && (
            <p className="banner" data-tone="warn" role="status">
              This run did not complete, so it carries no confident answer. It has been routed to a person.
            </p>
          )}
          <p className="notice">{result.notice}</p>
        </>
      )}

      <AgentStrip steps={result?.steps ?? null} working={working} />

      {result && status && (
        <>
          <div className="tabs" role="tablist" aria-label="Run details">
            {(["findings", "trace", "request"] as Tab[]).map((t) => (
              <button key={t} id={`tab-${t}`} role="tab" type="button" className="tab" aria-selected={tab === t}
                aria-controls={`panel-${t}`} tabIndex={tab === t ? 0 : -1} onClick={() => setTab(t)}
                onKeyDown={(e) => {
                  const order: Tab[] = ["findings", "trace", "request"];
                  const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
                  if (!step) return;
                  const next = order[(order.indexOf(t) + step + order.length) % order.length]!;
                  setTab(next);
                  document.getElementById(`tab-${next}`)?.focus();
                }}>
                {t === "findings" ? `Findings ${result.findings.length}` : t === "trace" ? `Trace · ${result.totals.steps} steps` : "Request"}
              </button>
            ))}
          </div>
          <div id={`panel-${tab}`} role="tabpanel" aria-labelledby={`tab-${tab}`} className="tabpanel">
            {tab === "findings" && <Findings findings={result.findings} verdict={result.verdict} />}
            {tab === "trace" && <Trace runId={runId} />}
            {tab === "request" && (
              <pre className="code-block">{JSON.stringify(status.request, null, 2)}</pre>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function FailedRun({ status }: { status: RunStatus }) {
  return (
    <div className="banner" data-tone="error" role="alert">
      <p className="banner__title">The run failed: {status.error ?? "unknown error"}.</p>
      <p>Nothing was concluded about this label. Check it again; if it keeps failing, give the run id and correlation id to the team.</p>
      <p className="banner__meta">Last update {time(status.updated_at)} · {ms(Date.parse(status.updated_at) - Date.parse(status.submitted_at))} after submission.</p>
    </div>
  );
}
