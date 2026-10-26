import type { Passage, RunTrace } from "../api/types";

/** Every passage the run retrieved, by id, from its tool steps (the trace keeps them in full: D5). */
export function retrievedPassages(trace: RunTrace): Map<string, Passage> {
  const found = new Map<string, Passage>();
  for (const step of trace.steps) {
    if (step.kind !== "tool") continue;
    const passages = (step.output as { passages?: unknown }).passages;
    if (!Array.isArray(passages)) continue;
    for (const p of passages as Passage[]) {
      if (p && typeof p.passage_id === "string" && typeof p.text === "string") found.set(p.passage_id, p);
    }
  }
  return found;
}

/** The passage split around the quoted span, for highlighting; null when the quote is not verbatim in it
 * (which the reviewer must see: the verifier should have caught that). */
export function splitAround(text: string, quote: string): [string, string, string] | null {
  const at = quote ? text.indexOf(quote) : -1;
  return at < 0 ? null : [text.slice(0, at), quote, text.slice(at + quote.length)];
}
