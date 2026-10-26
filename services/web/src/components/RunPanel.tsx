import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";

import { submitRun } from "../api/client";

import type { LabelCheckRequest, Readiness, RunStatus } from "../api/types";
import { clientId } from "../lib/clientId";
import { SECTION_41_EXAMPLE } from "../lib/example";
import { ms, ROUTE_MEANING, shortId, time } from "../lib/format";
import { useRun } from "../lib/useRun";
import { AgentStrip } from "./AgentStrip";
import { DeclarationBlock } from "./DeclarationBlock";
import { DemoNotice } from "./DemoNotice";
import { Feedback } from "./Feedback";
import { Findings } from "./Findings";
import { Mark } from "./Mark";
import { PrintReport } from "./PrintReport";
import LatticeLoader from "./reactbits/LatticeLoader/LatticeLoader";
import { Trace } from "./Trace";

type Tab = "findings" | "trace" | "request";

const TAB_INTRO: Record<Tab, string> = {
  findings: "One row per requirement the system checked, most serious first, each with the regulation text it rests on.",
  trace: "Every step the system took, in order, with what it searched for and the text it got back. For audit and debugging.",
  request: "Exactly what was submitted for this check.",
};

export function RunPanel({ runId, focus, onAccepted, initialTab, onRequest, ready }: {
  runId: string | null; focus: boolean; onAccepted: (runId: string) => void; initialTab?: "trace";
  onRequest: (runId: string, request: LabelCheckRequest) => void; ready?: Readiness | null;
}) {
  if (!runId) return <EmptyRun onAccepted={onAccepted} ready={ready} />;
  return <RunView key={runId} runId={runId} focus={focus} initialTab={initialTab ?? "findings"} onRequest={onRequest}
    ready={ready} />;
}

function EmptyRun({ onAccepted, ready }: { onAccepted: (runId: string) => void; ready?: Readiness | null }) {
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
      <DemoNotice ready={ready} />
      <ol className="howto">
        <li><strong>Describe the label.</strong> Type what is printed on the pack into the form. It starts filled in
          with an example you can edit or clear.</li>
        <li><strong>Press Check label.</strong> The system reads the label against the two FSSAI regulations, in the six
          steps below, and shows each one as it runs.</li>
        <li><strong>Read the result.</strong> Every requirement it checked is marked met, unmet or cannot determine,
          with the exact regulation text it rests on, and the label gets one of three recommendations.</li>
      </ol>
      <AgentStrip steps={null} working={false} />
      <div className="run__example">
        <div>
          <h3>Try the example</h3>
          <p>A breakfast cereal claims &ldquo;Source of protein&rdquo; and declares 8 g of protein per 100 g. Is the claim
            allowed? The rule is in the Claims regulation, which the Labelling regulation never mentions: finding it is
            what this system is built for. (It is the course spec&rsquo;s &sect;4.1 test case.)</p>
        </div>
        <button type="button" className="button" onClick={runExample} disabled={busy} aria-busy={busy || undefined}>
          {busy ? "Checking…" : "Check the example label"}
        </button>
      </div>
      {error && <p className="banner" data-tone="error" role="alert">{error}</p>}
      <RouteGuide />
      <p className="notice">The service never approves a label for print. A regulatory affairs professional decides.</p>
    </section>
  );
}

/** What each recommendation means, in plain words, before anyone has run a check. */
function RouteGuide() {
  return (
    <>
    <h3 className="route-guide__title" id="route-guide-title">What the three recommendations mean</h3>
    <dl className="route-guide" aria-labelledby="route-guide-title">
      {(["clear-for-print", "revise-and-recheck", "regulatory-review"] as const).map((route) => (
        <div key={route}>
          <dt><Mark kind={route} /> <span className="mono">{route}</span></dt>
          <dd>{ROUTE_MEANING[route]}</dd>
        </div>
      ))}
    </dl>
    </>
  );
}

function RunView({ runId, focus, initialTab, onRequest, ready }: {
  runId: string; focus: boolean; initialTab: Tab; onRequest: (runId: string, request: LabelCheckRequest) => void;
  ready?: Readiness | null;
}) {
  const { status, error, reconnecting } = useRun(runId);
  const request = status?.request ?? null;
  useEffect(() => {
    if (request) onRequest(runId, request);
  }, [runId, request, onRequest]);
  const [tab, setTabState] = useState<Tab>(initialTab);
  const setTab = (next: Tab) => {
    setTabState(next);
    // Keep the address shareable without a navigation: #/runs/<id>/trace opens straight on the trace.
    history.replaceState(null, "", `#/runs/${runId}${next === "trace" ? "/trace" : ""}`);
  };
  // The printable report exists only while printing (the button, or the browser's own print), so the findings
  // are never on the page twice for screen readers.
  const [printing, setPrinting] = useState(false);
  useEffect(() => {
    const before = () => flushSync(() => setPrinting(true));
    const after = () => setPrinting(false);
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => {
      window.removeEventListener("beforeprint", before);
      window.removeEventListener("afterprint", after);
    };
  }, []);
  const savePdf = () => {
    flushSync(() => setPrinting(true));
    window.print();
  };
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
        {result && status && (
          <button type="button" className="button-link" onClick={savePdf}>Save findings as PDF</button>
        )}
      </div>
      {printing && result && status && <PrintReport status={status} result={result} />}

      <DemoNotice ready={ready} />
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
            <p className="tabpanel__intro">{TAB_INTRO[tab]}</p>
            {tab === "findings" && <Findings findings={result.findings} verdict={result.verdict} />}
            {tab === "trace" && <Trace runId={runId} />}
            {tab === "request" && (
              <pre className="code-block">{JSON.stringify(status.request, null, 2)}</pre>
            )}
          </div>
          <Feedback key={runId} runId={runId} />
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
