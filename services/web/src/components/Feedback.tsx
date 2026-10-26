import { useEffect, useState, type FormEvent } from "react";

import { feedbackAvailable, sendFeedback } from "../api/client";

/** L6: the analyst says whether this result was satisfactory, and why. Hidden until the API serves the
 * feedback endpoint; the reason is plain text and is sent, never rendered back as markup. */
export function Feedback({ runId }: { runId: string }) {
  const [available, setAvailable] = useState(false);
  const [satisfactory, setSatisfactory] = useState<boolean | null>(null);
  const [reason, setReason] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const abort = new AbortController();
    feedbackAvailable(abort.signal).then((ok) => { if (!abort.signal.aborted) setAvailable(ok); });
    return () => abort.abort();
  }, []);

  if (!available) return null;
  if (state === "sent") {
    return <p className="feedback__done" role="status">Feedback recorded. It feeds the quality chart (L6).</p>;
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (satisfactory === null) return;
    setState("sending");
    setError(null);
    try {
      await sendFeedback(runId, satisfactory, reason.trim());
      setState("sent");
    } catch (err) {
      setError((err as Error).message);
      setState("idle");
    }
  };

  return (
    <form className="feedback" onSubmit={submit}>
      <fieldset>
        <legend>Was this result satisfactory?</legend>
        <div className="feedback__choice" role="group" aria-label="Satisfactory">
          {([true, false] as const).map((v) => (
            <button key={String(v)} type="button" className="findings__count" aria-pressed={satisfactory === v}
              onClick={() => setSatisfactory(v)}>
              {v ? "Yes, satisfactory" : "No, not satisfactory"}
            </button>
          ))}
        </div>
        <div className="field">
          {/* The feedback endpoint requires a reason (1 to 2000 characters): the team reads it to fix the system. */}
          <label htmlFor="feedback-reason">Why? One sentence is enough</label>
          <textarea id="feedback-reason" rows={2} maxLength={2000} required value={reason}
            onChange={(e) => setReason(e.target.value)} />
        </div>
        <button type="submit" className="button"
          disabled={satisfactory === null || !reason.trim() || state === "sending"}
          aria-busy={state === "sending" || undefined}>
          {state === "sending" ? "Sending…" : "Send feedback"}
        </button>
      </fieldset>
      {error && <p className="banner" data-tone="error" role="alert">{error}</p>}
    </form>
  );
}
