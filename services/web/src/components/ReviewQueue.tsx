import { useEffect, useState, type FormEvent } from "react";

import { feedbackAvailable, getTrace, listRuns, sendFeedback } from "../api/client";
import type { Citation, Passage, RunSummary, RunTrace } from "../api/types";
import { extraEscalationReason } from "../lib/escalation";
import { shortId, STATUS_WORD, time } from "../lib/format";
import { retrievedPassages, splitAround } from "../lib/review";
import { Mark } from "./Mark";

/**
 * Reviewer console (extra). The queue of runs the system routed to regulatory-review; for one run, every citation
 * next to the full passage it was quoted from; the reviewer's decision recorded as feedback (L6). Nothing here
 * approves a label: a decision says whether escalating was right, and a person still signs off on print.
 */
export function ReviewQueue({ runId }: { runId: string | null }) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const abort = new AbortController();
    listRuns(50, abort.signal, "regulatory-review").then(setRuns, (err: Error) => {
      if (!abort.signal.aborted) setError(err.message);
    });
    return () => abort.abort();
  }, []);

  return (
    <div className="review">
      <section className="panel review__queue" aria-labelledby="review-title">
        <h2 id="review-title">Review queue</h2>
        <p className="tabpanel__intro">
          Labels the system would not decide on its own. Open one, check each citation against the regulation text
          it came from, then record whether escalating was right.
        </p>
        {error && <p className="banner" data-tone="error" role="alert">Could not load the queue. {error}</p>}
        {!error && !runs && <p className="empty" aria-busy="true">Loading…</p>}
        {runs && runs.length === 0 && <p className="empty">Nothing to review: no recent run was routed to a person.</p>}
        {runs && runs.length > 0 && (
          <ul className="review__list">
            {runs.map((r) => (
              <li key={r.run_id}>
                <a href={`#/review/${r.run_id}`} aria-current={r.run_id === runId ? "page" : undefined}>
                  <Mark kind="regulatory-review" />
                  <span className="review__product">{r.product_name ?? "Untitled label"}</span>
                  <span className="review__when num">{time(r.submitted_at)} · <code>{shortId(r.run_id)}</code></span>
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>
      {runId ? <ReviewItem key={runId} runId={runId} />
        : runs && runs.length > 0 && <p className="panel empty">Choose a label from the queue to review it.</p>}
    </div>
  );
}

function ReviewItem({ runId }: { runId: string }) {
  const [trace, setTrace] = useState<RunTrace | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const abort = new AbortController();
    getTrace(runId, abort.signal).then(setTrace, (err: Error) => {
      if (!abort.signal.aborted) setError(err.message);
    });
    return () => abort.abort();
  }, [runId]);

  if (error) return <p className="panel banner" data-tone="error" role="alert">Could not load this run. {error}</p>;
  if (!trace) return <p className="panel empty" aria-busy="true">Loading the run…</p>;
  const passages = retrievedPassages(trace);
  return (
    <section className="panel review__item" aria-labelledby="review-item-title">
      <div className="run__head">
        <h2 id="review-item-title">{trace.request?.label.product_name ?? "Label"}</h2>
        <p className="run__meta">
          Run <code title={runId}>{shortId(runId)}</code> · submitted {time(trace.submitted_at)} ·{" "}
          <a href={`#/runs/${runId}`}>open the full result</a>
        </p>
      </div>
      <dl className="review__why">
        <dt>Why it is here</dt>
        <dd>{trace.routing?.reason ?? "No route recorded."}</dd>
        {trace.routing && extraEscalationReason(trace.routing) && (
          <><dt>Escalation</dt><dd>{extraEscalationReason(trace.routing)}</dd></>
        )}
      </dl>
      {trace.findings.length === 0 ? (
        <p className="empty">No findings: the run stopped before research. The reason above says why.</p>
      ) : (
        <ol className="review__findings">
          {trace.findings.map((f) => (
            <li key={f.requirement_id}>
              <p><strong>{STATUS_WORD[f.status] ?? f.status}</strong> · {f.requirement} <code>{f.requirement_id}</code></p>
              <p>{f.explanation}</p>
              {f.citations.length === 0 && <p className="review__nocite">No citation: no regulation text was found for this.</p>}
              {f.citations.map((c, i) => <CitationPair key={`${c.passage_id}-${i}`} citation={c} passage={passages.get(c.passage_id)} />)}
            </li>
          ))}
        </ol>
      )}
      <Decision runId={runId} />
    </section>
  );
}

/** What the system quoted, beside the whole passage it retrieved, with the quote marked in place. */
function CitationPair({ citation, passage }: { citation: Citation; passage: Passage | undefined }) {
  const parts = passage ? splitAround(passage.text, citation.quote) : null;
  return (
    <div className="review__pair">
      <figure className="quote">
        <figcaption>Quoted · <span className="mono">{citation.regulation} {citation.clause_id}</span></figcaption>
        <blockquote>{citation.quote}</blockquote>
      </figure>
      <figure className="review__source">
        <figcaption>
          Retrieved passage · <span className="mono">{passage ? `${passage.regulation} ${passage.clause_id}` : citation.passage_id}</span>
        </figcaption>
        {!passage && <p className="banner" data-tone="warn">This passage is not in the run's trace, so the quote cannot be checked here.</p>}
        {passage && !parts && <p className="banner" data-tone="warn">The quote is not word for word in this passage.</p>}
        {passage && (parts
          ? <p className="review__passage">{parts[0]}<mark>{parts[1]}</mark>{parts[2]}</p>
          : <p className="review__passage">{passage.text}</p>)}
      </figure>
    </div>
  );
}

type Choice = "accept" | "override";

function Decision({ runId }: { runId: string }) {
  const [available, setAvailable] = useState<boolean | null>(null);
  const [choice, setChoice] = useState<Choice | null>(null);
  const [note, setNote] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const abort = new AbortController();
    feedbackAvailable(abort.signal).then((ok) => { if (!abort.signal.aborted) setAvailable(ok); });
    return () => abort.abort();
  }, []);

  if (available === null) return null;
  if (!available) {
    return <p className="notice">Recording a decision needs the feedback endpoint, which this API does not serve yet.</p>;
  }
  if (state === "sent") {
    return (
      <p className="feedback__done" role="status">
        Decision recorded as feedback. It does not approve the label; a person still signs off on print.
      </p>
    );
  }
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!choice || !note.trim()) return;
    setState("sending");
    setError(null);
    const verb = choice === "accept" ? "accepted the escalation" : "overrode the escalation";
    try {
      await sendFeedback(runId, choice === "accept", `[reviewer] ${verb}: ${note.trim()}`);
      setState("sent");
    } catch (err) {
      setError((err as Error).message);
      setState("idle");
    }
  };
  return (
    <form className="feedback" onSubmit={submit}>
      <fieldset>
        <legend>Your decision on this escalation</legend>
        <div className="feedback__choice" role="group" aria-label="Decision">
          <button type="button" className="findings__count" aria-pressed={choice === "accept"} onClick={() => setChoice("accept")}>
            Escalating was right
          </button>
          <button type="button" className="findings__count" aria-pressed={choice === "override"} onClick={() => setChoice("override")}>
            Override: the system should have answered
          </button>
        </div>
        <div className="field">
          <label htmlFor="review-note">What did you find? One sentence is enough</label>
          <textarea id="review-note" rows={2} maxLength={1900} required value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        <button type="submit" className="button" disabled={!choice || !note.trim() || state === "sending"}
          aria-busy={state === "sending" || undefined}>
          {state === "sending" ? "Recording…" : "Record decision"}
        </button>
      </fieldset>
      <p className="notice">Recorded as feedback for the team (L6). It never approves the label for print.</p>
      {error && <p className="banner" data-tone="error" role="alert">{error}</p>}
    </form>
  );
}
