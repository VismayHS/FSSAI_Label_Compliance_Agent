import { vi } from "vitest";

import type { RunStatus, RunTrace } from "../api/types";
import completed from "./fixtures/run-completed.json";
import trace from "./fixtures/trace.json";

export const RUN_ID = (completed as RunStatus).run_id;
export const completedRun = () => structuredClone(completed) as RunStatus;
export const fullTrace = () => structuredClone(trace) as RunTrace;

type Handler = (init: RequestInit | undefined, url: string) => Response | Promise<Response>;

export const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

/** A tiny fake API: routes are "METHOD path" (path without query string) or a RegExp on the path. */
export function mockApi(routes: Record<string, Handler | Handler[]>) {
  const calls: { method: string; url: string; init?: RequestInit }[] = [];
  const queues = new Map(Object.entries(routes).map(([k, v]) => [k, Array.isArray(v) ? [...v] : v]));
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.split("?")[0]!;
    calls.push({ method, url, init });
    const key = `${method} ${path}`;
    const entry = queues.get(key) ?? queues.get(`${method} *${path.replace(/[0-9a-f]{32}/, ":id")}`);
    if (!entry) return json({ detail: "not mocked" }, 599);
    const handler = Array.isArray(entry) ? (entry.length > 1 ? entry.shift()! : entry[0]!) : entry;
    return handler(init, url);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export const readyz = () => json({ ready: true, checks: { dispatch: { ok: true, detail: "inline execution (development mode, no queue)" }, run_store: { ok: true, detail: "InMemoryRunStore" } } });
