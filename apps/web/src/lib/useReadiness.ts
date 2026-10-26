import { useEffect, useState } from "react";

import { getReadiness } from "../api/client";
import type { Readiness } from "../api/types";

/** GET /readyz now and every 15 s. undefined = still checking, null = unreachable. */
export function useReadiness(): Readiness | null | undefined {
  const [ready, setReady] = useState<Readiness | null | undefined>(undefined);
  useEffect(() => {
    const abort = new AbortController();
    const check = () => getReadiness(abort.signal).then((r) => { if (!abort.signal.aborted) setReady(r); });
    void check();
    const timer = setInterval(check, 15_000);
    return () => { abort.abort(); clearInterval(timer); };
  }, []);
  return ready;
}

/** Plain names for the parts that decide a result, in pipeline order. */
const REASONING: [seam: string, name: string][] = [
  ["gate", "input validation"], ["guardrails", "safety checks"], ["classifier", "classifier"],
  ["retriever", "regulation search"], ["researcher", "researcher"], ["llm", "language model"],
  ["verifier", "verifier"], ["router", "router"],
];

/** The reasoning parts still running on the contracts' stand-ins, by plain name. */
export function standIns(ready: Readiness | null | undefined): string[] {
  const parts = ready?.components;
  if (!parts) return [];
  return REASONING.filter(([seam]) => parts[seam]?.stand_in).map(([, name]) => name);
}
