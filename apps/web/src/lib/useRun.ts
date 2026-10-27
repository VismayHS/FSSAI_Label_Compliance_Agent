import { useEffect, useState } from "react";

import { ApiError, getRun, runEventsUrl } from "../api/client";
import { TERMINAL_STATES, type RunStatus } from "../api/types";

export interface RunPoll {
  status: RunStatus | null;
  /** A permanent problem (e.g. no run with this id): polling has stopped. */
  error: string | null;
  /** A passing problem (network blip, 5xx): still polling, with backoff. */
  reconnecting: boolean;
}

const FIRST_MS = 500;
const MAX_MS = 2000;
const MAX_ERROR_MS = 8000;

/** Follows a run until it is completed or failed. Where the browser has EventSource it listens to
 * GET /v1/runs/{id}/events, so each change arrives at once; if the stream fails it falls back to polling
 * GET /v1/runs/{id} (decision 301), backing off from 0.5 s to 2 s while it runs and further on errors.
 * Stops on unmount. Mount it under `key={runId}` so a new run starts from a clean state. */
export function useRun(runId: string | null): RunPoll {
  const [poll, setPoll] = useState<RunPoll>({ status: null, error: null, reconnecting: false });

  useEffect(() => {
    if (!runId) return;
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let delay = FIRST_MS;
    let errorDelay = 1000;

    const tick = async () => {
      try {
        const status = await getRun(runId, abort.signal);
        setPoll({ status, error: null, reconnecting: false });
        if (TERMINAL_STATES.has(status.state)) return;
        delay = Math.min(MAX_MS, delay * 1.5);
        timer = setTimeout(tick, delay);
      } catch (err) {
        if (abort.signal.aborted) return;
        if (err instanceof ApiError && err.status === 404) {
          setPoll({ status: null, error: "No run with this id. It may have been lost when the API restarted.", reconnecting: false });
          return;
        }
        setPoll((p) => ({ ...p, reconnecting: true }));
        errorDelay = Math.min(MAX_ERROR_MS, errorDelay * 2);
        timer = setTimeout(tick, errorDelay);
      }
    };
    let source: EventSource | null = null;
    if (typeof EventSource === "undefined") {
      void tick();
    } else {
      source = new EventSource(runEventsUrl(runId));
      source.addEventListener("status", (e) => {
        setPoll({ status: JSON.parse((e as MessageEvent<string>).data) as RunStatus, error: null, reconnecting: false });
      });
      source.addEventListener("end", () => source?.close());
      source.onerror = () => {  // unknown run, a proxy that drops streams, a restart: poll instead
        source?.close();
        source = null;
        if (!abort.signal.aborted) void tick();
      };
    }
    return () => {
      abort.abort();
      clearTimeout(timer);
      source?.close();
    };
  }, [runId]);

  return runId ? poll : { status: null, error: null, reconnecting: false };
}
