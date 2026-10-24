import { useEffect, useState } from "react";

import { getTrace } from "../api/client";
import type { Passage, RunTrace, StepRecord } from "../api/types";
import { ms, tokens, usd } from "../lib/format";
import Counter from "./reactbits/Counter/Counter";
import { Mark } from "./Mark";

/** D5: the whole run, reconstructed from its id. Every step in order with its inputs and outputs. */
export function Trace({ runId }: { runId: string }) {
  const [trace, setTrace] = useState<RunTrace | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const abort = new AbortController();
    getTrace(runId, abort.signal).then(setTrace, (err: Error) => {
      if (!abort.signal.aborted) setError(err.message);
    });
    return () => abort.abort();
  }, [runId]);

  if (error) return <p className="banner" data-tone="error" role="alert">Could not load the trace. {error}</p>;
  if (!trace) return <p className="empty" aria-busy="true">Loading the trace…</p>;

  const totals = trace.totals;
  return (
    <div className="trace">
      {totals && (
        <dl className="totals">
          <div><dt>Latency</dt><dd><Counter value={Math.round(totals.latency_ms)} suffix=" ms" fontSize="var(--t-lg)" tabular /></dd></div>
          <div><dt>Queue wait</dt><dd className="num">{ms(trace.queue_wait_ms)}</dd></div>
          <div><dt>Steps</dt><dd><Counter value={totals.steps} fontSize="var(--t-lg)" tabular /></dd></div>
          <div><dt>Tool calls</dt><dd><Counter value={totals.tool_calls} fontSize="var(--t-lg)" tabular /></dd></div>
          <div><dt>LLM calls</dt><dd><Counter value={totals.llm_calls} fontSize="var(--t-lg)" tabular /></dd></div>
          <div><dt>Tokens</dt><dd className="num">{tokens(totals.prompt_tokens, totals.completion_tokens)}</dd></div>
          <div><dt>Cost</dt><dd className="num">{usd(totals.cost_usd)}</dd></div>
        </dl>
      )}

      {Object.keys(trace.agents).length > 0 && (
        <div className="table-wrap">
          <table className="agents">
            <caption>By agent</caption>
            <thead>
              <tr><th scope="col">Agent</th><th scope="col">Steps</th><th scope="col">Tool calls</th><th scope="col">LLM calls</th><th scope="col">Errors</th><th scope="col">Latency</th><th scope="col">Tokens</th><th scope="col">Cost</th></tr>
            </thead>
            <tbody>
              {Object.entries(trace.agents).map(([agent, a]) => (
                <tr key={agent}>
                  <th scope="row">{agent}</th>
                  <td>{a.steps}</td><td>{a.tool_calls}</td><td>{a.llm_calls}</td><td>{a.errors}</td>
                  <td>{ms(a.latency_ms)}</td><td>{tokens(a.prompt_tokens, a.completion_tokens)}</td><td>{usd(a.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {Object.keys(trace.prompt_versions).length > 0 && (
        <p className="trace__prompts">
          Prompt versions:{" "}
          {Object.entries(trace.prompt_versions).map(([name, v]) => <code key={name}>{name}@{v}</code>)}
        </p>
      )}

      <h3 className="trace__heading">Steps in order</h3>
      {trace.steps.length === 0 ? (
        <p className="empty">{trace.state === "failed" ? "The run failed before any step was recorded." : "No steps recorded yet."}</p>
      ) : (
        <div className="steps-wrap">
          <div className="steps__head" aria-hidden="true">
            <span /><span>#</span><span>Step · agent</span><span>Kind</span><span className="num-head">Latency</span><span className="num-head">Tokens</span><span className="num-head">Cost</span><span>Prompt</span>
          </div>
          <ol className="steps">
            {trace.steps.map((s) => (
              <li key={s.step_index} className="step" data-error={s.error ? true : undefined}>
                <details>
                  <summary>
                    <Mark kind={s.error ? "error" : "done"} />
                    <span className="step__index num">{s.step_index}</span>
                    <span className="step__name"><code>{s.name}</code> <span className="step__agent">{s.agent}</span></span>
                    <span className="step__kind">{s.kind}{s.error ? ", failed" : ""}</span>
                    <span className="step__metric">{ms(s.latency_ms)}</span>
                    <span className="step__metric">{tokens(s.prompt_tokens, s.completion_tokens)}</span>
                    <span className="step__metric">{usd(s.cost_usd)}</span>
                    <span className="step__prompt">{s.prompt_name ? <code>{s.prompt_name}@{s.prompt_version}</code> : null}</span>
                  </summary>
                  <StepDetail step={s} />
                </details>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

function StepDetail({ step }: { step: StepRecord }) {
  const passages = (step.output.passages as Passage[] | undefined) ?? null;
  const restOutput = Object.fromEntries(Object.entries(step.output).filter(([k]) => k !== "passages"));
  return (
    <div className="step__detail">
      {step.error && <p className="banner" data-tone="error">Error: {step.error}</p>}
      {"query" in step.input && (
        <p>Query: <q className="step__query">{String(step.input.query)}</q>{step.input.regulation ? <> · in <code>{String(step.input.regulation)}</code></> : null}</p>
      )}
      {passages && (
        passages.length === 0 ? <p className="empty">No passages returned.</p> : (
          <ol className="passages">
            {passages.map((p) => (
              <li key={p.passage_id}>
                <p className="passages__ref"><code>{p.regulation}</code> · clause <code>{p.clause_id}</code>{p.score != null && <> · score <span className="num">{p.score}</span></>}</p>
                <p>{p.text}</p>
              </li>
            ))}
          </ol>
        )
      )}
      <details className="raw">
        <summary>Raw input and output</summary>
        <pre>{JSON.stringify({ input: step.input, output: passages ? restOutput : step.output }, null, 2)}</pre>
      </details>
    </div>
  );
}
