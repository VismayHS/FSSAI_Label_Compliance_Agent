import { describe, expect, it } from "vitest";

import { stageStates } from "../components/AgentStrip";
import type { RunResult, StepRecord } from "../api/types";
import { completedRun } from "../test/api";
import { escalation, handoffText } from "./escalation";
import { ms, usd } from "./format";
import { hrefFor, parse } from "./useHashRoute";

const step = (agent: string, name: string, error: string | null = null) =>
  ({ agent, name, error, kind: "tool", step_index: 0, started_at: "", latency_ms: 0, input: {}, output: {},
     prompt_name: null, prompt_version: null, prompt_tokens: 0, completion_tokens: 0, cost_usd: 0 }) as StepRecord;

describe("agent strip stages", () => {
  it("marks every stage done for a full run", () => {
    expect(stageStates(completedRun().result!.steps).map((s) => s.kind)).toEqual(["done", "done", "done", "done", "done", "done"]);
  });

  it("shows stages a guardrail block never reached as skipped", () => {
    const states = stageStates([step("guardrails", "screen_input")]);
    expect(states.map((s) => s.kind)).toEqual(["done", "skipped", "skipped", "skipped", "skipped", "skipped"]);
  });

  it("flags failed steps and counts verifier attempts", () => {
    const states = stageStates([step("researcher", "corpus_search", "timeout"), step("verifier", "verify"), step("verifier", "verify")]);
    expect(states[2]).toMatchObject({ kind: "error", detail: "1 failed step" });
    expect(states[3]).toMatchObject({ kind: "done", detail: "2 steps, 2 attempts · 0 ms" });
  });
});

describe("routes", () => {
  it("parses and builds deep links", () => {
    const id = "c5152227a57f404887e7519edf03d102";
    expect(parse(`#/runs/${id}`)).toEqual({ name: "check", runId: id });
    expect(parse("#/runs")).toEqual({ name: "runs" });
    expect(parse("#/runs/not-an-id")).toEqual({ name: "check", runId: null });
    expect(hrefFor({ name: "check", runId: id })).toBe(`#/runs/${id}`);
    expect(parse(`#/runs/${id}/trace`)).toEqual({ name: "check", runId: id, tab: "trace" });
    expect(hrefFor({ name: "check", runId: id, tab: "trace" })).toBe(`#/runs/${id}/trace`);
  });
});

describe("formatting", () => {
  it("formats latency and cost for the trace", () => {
    expect(ms(12.4)).toBe("12 ms");
    expect(ms(1530)).toBe("1.53 s");
    expect(usd(0)).toBe("$0.0000");
    expect(usd(0.00042)).toBe("$0.000420");
    expect(ms(null)).toBe("—");
  });
});

describe("escalation in plain words", () => {
  const escalated = (edit: (r: RunResult) => void) => {
    const result = completedRun().result!;
    result.routing = { route: "regulatory-review", reason: "Could not verify the finding.", escalation_reason: "x" };
    edit(result);
    return result;
  };

  it("says nothing for routes a person does not have to take over", () => {
    expect(escalation(completedRun().result!)).toBeNull();
  });

  it("names the cause from the structured fields, most fundamental first", () => {
    expect(escalation(escalated((r) => { r.complete = false; }))?.kind).toBe("incomplete");
    expect(escalation(escalated((r) => {
      r.guardrails = [{ stage: "input", allowed: false, flags: ["prompt_injection:label.other_text"], detail: "" }];
    }))?.kind).toBe("guardrail");
    expect(escalation(escalated((r) => { r.classification!.in_scope = false; r.classification!.category = "spirits"; }))
      ).toMatchObject({ kind: "out_of_scope", detail: expect.stringContaining('"spirits"') });
    expect(escalation(escalated(() => {}))?.kind).toBe("unverified");
  });

  it("builds a plain-text hand-off with the run id, both reasons and the trace link", () => {
    const status = completedRun();
    const result = escalated((r) => { r.complete = false; });
    const text = handoffText(status, result, "http://localhost:8080/#/runs/abc/trace");
    expect(text).toContain(`Run: ${status.run_id}`);
    expect(text).toContain("Why: The check did not finish");
    expect(text).toContain("System reason: Could not verify the finding. (x)");
    expect(text).toContain("Trace: http://localhost:8080/#/runs/abc/trace");
    expect(text).toContain("Product: Roasted chana");
  });
});
