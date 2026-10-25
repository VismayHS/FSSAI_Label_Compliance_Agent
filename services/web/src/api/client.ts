// The HTTP contract of contexts/LLM_Context.md §7. Every outcome the UI must show is a typed result,
// so no screen has to guess what a status code meant.
import { clientId } from "../lib/clientId";
import type { FieldError, Readiness, RunStatus, RunSummary, RunTrace } from "./types";

declare global {
  interface Window {
    FSSAI_CONFIG?: { apiBase?: string };
  }
}

const base = () => (window.FSSAI_CONFIG?.apiBase ?? "").replace(/\/$/, "");

export type SubmitOutcome =
  | { kind: "accepted"; runId: string; correlationId: string }
  | { kind: "rejected"; errors: FieldError[]; quarantineId: string | null; correlationId: string }
  | { kind: "rate_limited"; retryAfterS: number }
  | { kind: "error"; message: string };

export class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${base()}${path}`, { signal, headers: { Accept: "application/json" } });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError("The service is unreachable. Check that the API is running.");
  }
  if (!res.ok) {
    const detail = await res.json().then((b: { detail?: unknown }) => b.detail).catch(() => undefined);
    throw new ApiError(typeof detail === "string" ? detail : `The service answered ${res.status}.`, res.status);
  }
  return (await res.json()) as T;
}

export async function submitRun(body: unknown, clientId: string): Promise<SubmitOutcome> {
  let res: Response;
  try {
    res = await fetch(`${base()}/v1/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json", "X-Client-Id": clientId },
      body: typeof body === "string" ? body : JSON.stringify(body),
    });
  } catch {
    return { kind: "error", message: "The service is unreachable. Check that the API is running, then try again." };
  }
  const data = await res.json().catch(() => ({}));
  switch (res.status) {
    case 202:
      return { kind: "accepted", runId: data.run_id, correlationId: data.correlation_id };
    case 422:
      return { kind: "rejected", errors: data.errors ?? [], quarantineId: data.quarantine_id ?? null,
               correlationId: data.correlation_id ?? "" };
    case 429:
      return { kind: "rate_limited", retryAfterS: Number(data.retry_after_s ?? res.headers.get("Retry-After") ?? 1) };
    default:
      return { kind: "error", message: typeof data.detail === "string" ? data.detail : `The service answered ${res.status}.` };
  }
}

export const getRun = (id: string, signal?: AbortSignal) => getJson<RunStatus>(`/v1/runs/${encodeURIComponent(id)}`, signal);
export const getTrace = (id: string, signal?: AbortSignal) => getJson<RunTrace>(`/v1/runs/${encodeURIComponent(id)}/trace`, signal);
export const listRuns = (limit = 20, signal?: AbortSignal) => getJson<RunSummary[]>(`/v1/runs?limit=${limit}`, signal);

export async function getReadiness(signal?: AbortSignal): Promise<Readiness | null> {
  try {
    const res = await fetch(`${base()}/readyz`, { signal });
    return (await res.json()) as Readiness;
  } catch {
    return null;
  }
}


const FEEDBACK_PATH = /^\/v1\/runs\/\{[^}]+\}\/feedback$/;

/** Whether the API serves POST /v1/runs/{run_id}/feedback (Vihaan's router, L6). Until it is merged the
 * feedback form stays hidden rather than offering something that cannot work. */
export async function feedbackAvailable(signal?: AbortSignal): Promise<boolean> {
  try {
    const spec = await getJson<{ paths?: Record<string, Record<string, unknown>> }>("/openapi.json", signal);
    return Object.entries(spec.paths ?? {}).some(([path, ops]) => FEEDBACK_PATH.test(path) && "post" in ops);
  } catch {
    return false;
  }
}

export async function sendFeedback(runId: string, satisfactory: boolean, reason: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${base()}/v1/runs/${runId}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json", "X-Client-Id": clientId() },
      body: JSON.stringify({ satisfactory, reason }),
    });
  } catch {
    throw new ApiError("The service is unreachable. Your feedback was not sent.");
  }
  if (!res.ok) {
    const detail = await res.json().then((b: { detail?: unknown }) => b.detail).catch(() => undefined);
    throw new ApiError(typeof detail === "string" ? detail : `The service answered ${res.status}; feedback not sent.`, res.status);
  }
}
