import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import App from "./App";
import { completedRun, fullTrace, json, mockApi, readyz, readyz_body, RUN_ID } from "./test/api";

const NOTICE = /not an approval for print/i;

function queued() {
  const run = completedRun();
  return { ...run, state: "queued" as const, result: null };
}

describe("the analyst workspace", () => {
  it("starts empty, explains what a result contains, and shows API readiness", async () => {
    mockApi({ "GET /readyz": readyz });
    render(<App />);
    expect(screen.getByRole("heading", { name: "Check a label before it goes to print" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check the example label" })).toBeInTheDocument();
    expect(screen.getByText("Describe the label.")).toBeInTheDocument();
    expect(screen.getByText("Read the result.")).toBeInTheDocument();
    expect(screen.getByText(/never approves a label/i)).toBeInTheDocument();
    expect(await screen.findByText("Service ready")).toBeInTheDocument();
    const guide = screen.getByLabelText("What the three recommendations mean");
    for (const route of ["clear-for-print", "revise-and-recheck", "regulatory-review"]) {
      expect(within(guide).getByText(route)).toBeInTheDocument();
    }
    expect(screen.queryByText(/Demo mode/)).not.toBeInTheDocument(); // readyz lists no stand-ins here
    expect(screen.getByLabelText("Product name")).toHaveValue("Multigrain flakes");
    expect(screen.getByLabelText("Declared category")).toHaveValue("breakfast-cereals");
  });

  it("submits the form, polls the run and shows route, findings, citations and the notice", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      "GET /readyz": readyz,
      "POST /v1/runs": () => json({ run_id: RUN_ID, status_url: `/v1/runs/${RUN_ID}`, trace_url: "", correlation_id: "c" }, 202),
      [`GET /v1/runs/${RUN_ID}`]: [() => json(queued()), () => json(completedRun())],
    });
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Check label" }));

    const post = calls.find((c) => c.method === "POST")!;
    expect((post.init!.headers as Record<string, string>)["X-Client-Id"]).toMatch(/^web-[0-9a-f]{8}$/);
    const body = JSON.parse(post.init!.body as string);
    expect(body.label.claims).toEqual(["Source of protein"]);
    expect(body.nutrition.protein_g).toBe(8);
    expect(window.location.hash).toBe(`#/runs/${RUN_ID}`);

    expect(await screen.findByText("Queued for a worker")).toBeInTheDocument();
    expect(await screen.findByText("revise-and-recheck", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByText(NOTICE)).toBeInTheDocument();
    expect(screen.getByText("Unmet or undetermined: CLM-PROTEIN-SOURCE")).toBeInTheDocument();

    const protein = screen.getByText("CLM-PROTEIN-SOURCE").closest("li")!;
    expect(within(protein).getByText("Unmet")).toBeInTheDocument();
    expect(within(protein).getByText("FSS-AC-2018")).toBeInTheDocument();
    // Fake regulation text must say so wherever it is shown, threshold included.
    expect(within(protein).getByText(/^\[PLACEHOLDER, NOT REAL REGULATION TEXT\].*at least 10 g protein/)).toBeInTheDocument();

    const strip = screen.getByRole("list", { name: "Agents in this run" });
    expect(within(strip).getAllByRole("listitem")).toHaveLength(6);
    expect(within(strip).getByText(/Verifier/).closest("li")).toHaveAttribute("data-kind", "done");
  });

  it("shows a 422 inline on the fields, with the quarantine id, and starts no run", async () => {
    const user = userEvent.setup();
    mockApi({
      "GET /readyz": readyz,
      "POST /v1/runs": () => json({ errors: [
        { loc: "nutrition.protein_g", message: "Input should be a valid number", code: "float_parsing" },
        { loc: "label.other_text", message: "Too long", code: "range" },
      ], quarantine_id: "q-123", correlation_id: "c" }, 422),
    });
    render(<App />);
    await user.clear(screen.getByLabelText(/Protein/));
    await user.type(screen.getByLabelText(/Protein/), "lots");
    await user.click(screen.getByRole("button", { name: "Check label" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("2 problems. No run was started.");
    expect(alert).toHaveTextContent("q-123");
    expect(alert).toHaveTextContent("label.other_text");
    expect(screen.getByLabelText(/Protein/)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getAllByText("Input should be a valid number").length).toBeGreaterThan(0);
    expect(window.location.hash).toBe("");
  });

  it("counts down a 429 and keeps the button disabled until then", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /readyz": readyz, "POST /v1/runs": () => json({ detail: "", retry_after_s: 30, correlation_id: "c" }, 429) });
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Check label" }));
    expect(await screen.findByText(/Too many checks.*Try again in 30 s/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check label" })).toBeDisabled();
  });

  it("sends JSON mode exactly as typed, so a malformed body reaches the gate", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      "GET /readyz": readyz,
      "POST /v1/runs": () => json({ errors: [{ loc: "body", message: "Request body is not valid JSON.", code: "json_invalid" }], quarantine_id: "q-9", correlation_id: "c" }, 422),
    });
    render(<App />);
    await user.click(screen.getByRole("radio", { name: "JSON" }));
    const area = screen.getByLabelText("LabelCheckRequest as JSON");
    await user.clear(area);
    await user.type(area, "{{not json");
    await user.click(screen.getByRole("button", { name: "Check label" }));
    expect(calls.find((c) => c.method === "POST")!.init!.body).toBe("{not json");
    expect(await screen.findByRole("alert")).toHaveTextContent("Request body is not valid JSON.");
  });

  it("refuses to turn invalid JSON back into the form, and says why", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /readyz": readyz });
    render(<App />);
    await user.click(screen.getByRole("radio", { name: "JSON" }));
    await user.clear(screen.getByLabelText("LabelCheckRequest as JSON"));
    await user.type(screen.getByLabelText("LabelCheckRequest as JSON"), "oops");
    await user.click(screen.getByRole("radio", { name: "Form" }));
    expect(await screen.findByText(/not valid JSON, so it can't be shown as a form/)).toBeInTheDocument();
    expect(screen.getByLabelText("LabelCheckRequest as JSON")).toBeInTheDocument();
  });

  it("shows an incomplete run as incomplete and routed to a person", async () => {
    const run = completedRun();
    run.result!.complete = false;
    run.result!.routing = { route: "regulatory-review", reason: "Run did not complete; no confident answer.",
                            escalation_reason: "ProviderUnavailable: primary: circuit open" };
    mockApi({ "GET /readyz": readyz, [`GET /v1/runs/${RUN_ID}`]: () => json(run) });
    window.location.hash = `#/runs/${RUN_ID}`;
    render(<App />);
    expect(await screen.findByText(/did not complete, so it carries no confident answer/)).toBeInTheDocument();
    expect(screen.getByText("regulatory-review")).toBeInTheDocument();
    expect(screen.getByText("ProviderUnavailable: primary: circuit open")).toBeInTheDocument();
    expect(screen.getByText(/The check did not finish, so a regulatory affairs professional decides/)).toBeInTheDocument();
  });

  it("explains an escalation in plain words and copies a hand-off for the reviewer", async () => {
    const run = completedRun();
    run.result!.routing = { route: "regulatory-review", reason: "Input failed guardrail screening.",
                            escalation_reason: "prompt_injection:label.other_text" };
    run.result!.guardrails = [{ stage: "input", allowed: false, flags: ["prompt_injection:label.other_text"], detail: "" }];
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    mockApi({ "GET /readyz": readyz, [`GET /v1/runs/${RUN_ID}`]: () => json(run) });
    window.location.hash = `#/runs/${RUN_ID}`;
    render(<App />);
    expect(await screen.findByText(/Some label text reads like instructions to the system, so a regulatory/)).toBeInTheDocument();
    expect(screen.getByText("What happens next")).toBeInTheDocument();
    expect(screen.getByText(/did not act on it and checked nothing further/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Copy details for the reviewer" }));
    expect(await screen.findByText("Copied: run id, reason and trace link.")).toBeInTheDocument();
    const text = writeText.mock.calls[0]![0] as string;
    expect(text).toContain(`Run: ${RUN_ID}`);
    expect(text).toContain(`#/runs/${RUN_ID}/trace`);
    expect(text).toContain("System reason: Input failed guardrail screening. (prompt_injection:label.other_text)");
  });

  it("says how to hand off by hand when the browser blocks copying", async () => {
    const run = completedRun();
    run.result!.routing = { route: "regulatory-review", reason: "Could not verify the finding.", escalation_reason: "unverified" };
    Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
                                                    configurable: true });
    mockApi({ "GET /readyz": readyz, [`GET /v1/runs/${RUN_ID}`]: () => json(run) });
    window.location.hash = `#/runs/${RUN_ID}`;
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "Copy details for the reviewer" }));
    expect(await screen.findByText(/Copy is blocked in this browser/)).toBeInTheDocument();
  });

  it("saves the findings as a PDF: every finding, verbatim quotes, the notice, and only while printing", async () => {
    const run = completedRun();
    run.request!.label.product_name = "<img src=x onerror=alert(1)> Flakes";
    const print = vi.spyOn(window, "print").mockImplementation(() => {});
    mockApi({ "GET /readyz": readyz, [`GET /v1/runs/${RUN_ID}`]: () => json(run) });
    window.location.hash = `#/runs/${RUN_ID}`;
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "Save findings as PDF" }));
    expect(print).toHaveBeenCalledOnce();
    const report = document.querySelector(".print-report") as HTMLElement;
    expect(report).not.toBeNull();
    expect(report.parentElement).toBe(document.body);
    const text = report.textContent ?? "";
    expect(text).toContain("Recommendation: revise-and-recheck");
    expect(text).toContain("not an approval for print");
    expect(text).toContain("Findings (2)");
    expect(text.indexOf("Condition for claim")).toBeLessThan(text.indexOf("Allergen declaration"));  // unmet first
    expect(text).toContain("FSS-AC-2018 FAKE-AC-PROTEIN");
    expect(text).toContain("<img src=x onerror=alert(1)> Flakes");  // label text stays text
    expect(report.querySelector("img")).toBeNull();
    window.dispatchEvent(new Event("afterprint"));
    await waitFor(() => expect(document.querySelector(".print-report")).toBeNull());
    print.mockRestore();
  });

  it("follows a run over server-sent events without polling, and polls if the stream fails", async () => {
    class FakeSource {
      static made: FakeSource[] = [];
      listeners: Record<string, ((e: { data: string }) => void)[]> = {};
      onerror: (() => void) | null = null;
      closed = false;
      constructor(readonly url: string) { FakeSource.made.push(this); }
      addEventListener(type: string, fn: (e: { data: string }) => void) { (this.listeners[type] ??= []).push(fn); }
      emit(type: string, data: string) { for (const fn of this.listeners[type] ?? []) fn({ data }); }
      close() { this.closed = true; }
    }
    vi.stubGlobal("EventSource", FakeSource);
    try {
      const { calls } = mockApi({ "GET /readyz": readyz, [`GET /v1/runs/${RUN_ID}`]: () => json(completedRun()) });
      window.location.hash = `#/runs/${RUN_ID}`;
      const { unmount } = render(<App />);
      await waitFor(() => expect(FakeSource.made).toHaveLength(1));
      const live = FakeSource.made[0]!;
      expect(live.url).toBe(`/v1/runs/${RUN_ID}/events`);
      act(() => live.emit("status", JSON.stringify(queued())));
      expect(await screen.findByText("Queued for a worker")).toBeInTheDocument();
      act(() => live.emit("status", JSON.stringify(completedRun())));
      expect(await screen.findByText(/needs attention/)).toBeInTheDocument();
      act(() => live.emit("end", "{}"));
      expect(live.closed).toBe(true);
      expect(calls.filter((c) => c.url.endsWith(`/v1/runs/${RUN_ID}`))).toHaveLength(0);
      unmount();

      // A stream that fails (an old proxy, a restart) falls back to polling GET /v1/runs/{id}.
      render(<App />);
      await waitFor(() => expect(FakeSource.made).toHaveLength(2));
      act(() => FakeSource.made[1]!.onerror?.());
      expect(await screen.findByText(/needs attention/)).toBeInTheDocument();
      expect(FakeSource.made[1]!.closed).toBe(true);
      expect(calls.filter((c) => c.url.endsWith(`/v1/runs/${RUN_ID}`)).length).toBeGreaterThan(0);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("shows no hand-off for a result the label owner can act on", async () => {
    mockApi({ "GET /readyz": readyz, [`GET /v1/runs/${RUN_ID}`]: () => json(completedRun()) });
    window.location.hash = `#/runs/${RUN_ID}`;
    render(<App />);
    await screen.findByText(/needs attention/);
    expect(screen.queryByText("What happens next")).not.toBeInTheDocument();
  });

  it("opens the trace with totals, agents and every step, passages included", async () => {
    const user = userEvent.setup();
    mockApi({
      "GET /readyz": readyz,
      [`GET /v1/runs/${RUN_ID}`]: () => json(completedRun()),
      [`GET /v1/runs/${RUN_ID}/trace`]: () => json(fullTrace()),
    });
    window.location.hash = `#/runs/${RUN_ID}`;
    render(<App />);
    await user.click(await screen.findByRole("tab", { name: /Trace/ }));
    expect(await screen.findByRole("table", { name: "By agent" })).toBeInTheDocument();
    expect(document.querySelectorAll(".steps > li")).toHaveLength(7);
    expect(document.querySelectorAll(".steps .mark[data-kind='done']")).toHaveLength(7);
    expect(screen.getAllByText(/PLACEHOLDER, NOT REAL REGULATION TEXT/).length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: /Jaeger/ })).not.toBeInTheDocument(); // tracing off in the fixture
  });

  it("links the trace to Jaeger when tracing is on", async () => {
    const user = userEvent.setup();
    const url = "http://localhost:16686/search?service=worker";
    mockApi({
      "GET /readyz": readyz,
      [`GET /v1/runs/${RUN_ID}`]: () => json(completedRun()),
      [`GET /v1/runs/${RUN_ID}/trace`]: () => json({ ...fullTrace(), jaeger_url: url }),
    });
    window.location.hash = `#/runs/${RUN_ID}`;
    render(<App />);
    await user.click(await screen.findByRole("tab", { name: /Trace/ }));
    expect(await screen.findByRole("link", { name: /Jaeger/ })).toHaveAttribute("href", url);
  });

  it("supports arrow keys across the result tabs", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /readyz": readyz, [`GET /v1/runs/${RUN_ID}`]: () => json(completedRun()),
              [`GET /v1/runs/${RUN_ID}/trace`]: () => json(fullTrace()) });
    window.location.hash = `#/runs/${RUN_ID}`;
    render(<App />);
    (await screen.findByRole("tab", { name: /Findings/ })).focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: /Trace/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /Trace/ })).toHaveFocus();
  });

  it("fills the form with the open run's request, so it can be fixed and checked again", async () => {
    const run = completedRun();
    run.request!.label.product_name = "Mahua spirit";
    run.request!.nutrition.protein_g = 4.5;
    mockApi({ "GET /readyz": readyz, [`GET /v1/runs/${RUN_ID}`]: () => json(run) });
    window.location.hash = `#/runs/${RUN_ID}`;
    render(<App />);
    await waitFor(() => expect(screen.getByLabelText("Product name")).toHaveValue("Mahua spirit"));
    expect(screen.getByLabelText(/Protein/)).toHaveValue("4.5");
  });

  it("lists findings most severe first", async () => {
    mockApi({ "GET /readyz": readyz, [`GET /v1/runs/${RUN_ID}`]: () => json(completedRun()) });
    window.location.hash = `#/runs/${RUN_ID}`;
    render(<App />);
    await screen.findByText("CLM-PROTEIN-SOURCE");
    const ids = [...document.querySelectorAll(".finding__id")].map((e) => e.textContent);
    expect(ids).toEqual(["CLM-PROTEIN-SOURCE", "LBL-ALLERGEN"]);
  });

  it("filters findings by status with toggle buttons", async () => {
    const user = userEvent.setup();
    mockApi({ "GET /readyz": readyz, [`GET /v1/runs/${RUN_ID}`]: () => json(completedRun()) });
    window.location.hash = `#/runs/${RUN_ID}`;
    render(<App />);
    const met = await screen.findByRole("button", { name: /1 met/ });
    expect(met).toHaveAttribute("aria-pressed", "true");
    await user.click(met);
    expect(met).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByText("LBL-ALLERGEN")).toBeNull();
    expect(screen.getByText("CLM-PROTEIN-SOURCE")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /1 unmet/ }));
    expect(screen.getByText(/Every finding is filtered out/)).toBeInTheDocument();
  });

  it("renders label text as text, never as markup", async () => {
    const run = completedRun();
    run.request!.label.product_name = '<img src=x onerror="alert(1)">Chana';
    mockApi({ "GET /readyz": readyz, [`GET /v1/runs/${RUN_ID}`]: () => json(run) });
    window.location.hash = `#/runs/${RUN_ID}`;
    const { container } = render(<App />);
    expect(await screen.findByText('<img src=x onerror="alert(1)">Chana')).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("explains a failed run and an unknown run id", async () => {
    const failed = { ...completedRun(), state: "failed" as const, result: null, error: "internal error (KeyError)" };
    mockApi({ "GET /readyz": readyz, [`GET /v1/runs/${RUN_ID}`]: () => json(failed) });
    window.location.hash = `#/runs/${RUN_ID}`;
    const { unmount } = render(<App />);
    expect(await screen.findByText(/The run failed: internal error \(KeyError\)/)).toBeInTheDocument();
    unmount();

    mockApi({ "GET /readyz": readyz, [`GET /v1/runs/${RUN_ID}`]: () => json({ detail: "No run with this id." }, 404) });
    window.location.hash = `#/runs/${RUN_ID}`;
    render(<App />);
    expect(await screen.findByText(/No run with this id/)).toBeInTheDocument();
  });

  it("says plainly when the API is unreachable", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    render(<App />);
    expect(await screen.findByText("API unreachable")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Check label" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The service is unreachable");
  });

  it("lists recent runs with route marks and links", async () => {
    mockApi({ "GET /readyz": readyz, "GET /v1/runs": () => json([
      { run_id: RUN_ID, state: "completed", submitted_at: completedRun().submitted_at, updated_at: completedRun().updated_at,
        product_name: "Roasted chana", route: "revise-and-recheck", complete: true },
    ]) });
    window.location.hash = "#/runs";
    render(<App />);
    const link = await screen.findByRole("link", { name: "Roasted chana" });
    expect(link).toHaveAttribute("href", `#/runs/${RUN_ID}`);
    expect(screen.getByRole("link", { name: "Recent runs" })).toHaveAttribute("aria-current", "page");
  });

  it("hides feedback until the API serves the endpoint", async () => {
    mockApi({ "GET /readyz": readyz, [`GET /v1/runs/${RUN_ID}`]: () => json(completedRun()),
              "GET /openapi.json": () => json({ paths: { "/v1/runs": { post: {} } } }) });
    window.location.hash = `#/runs/${RUN_ID}`;
    render(<App />);
    expect(await screen.findByRole("tab", { name: /Findings/ })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("group", { name: "Satisfactory" })).not.toBeInTheDocument());
  });

  it("sends feedback on a finished run, with the reason as plain text", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      "GET /readyz": readyz,
      [`GET /v1/runs/${RUN_ID}`]: () => json(completedRun()),
      "GET /openapi.json": () => json({ paths: { "/v1/runs/{run_id}/feedback": { post: {} } } }),
      [`POST /v1/runs/${RUN_ID}/feedback`]: [() => json({ detail: "reason too short" }, 422), () => json({}, 201)],
    });
    window.location.hash = `#/runs/${RUN_ID}`;
    render(<App />);
    const group = await screen.findByRole("group", { name: "Satisfactory" });
    const send = screen.getByRole("button", { name: "Send feedback" });
    expect(send).toBeDisabled();
    await user.click(within(group).getByRole("button", { name: "No, not satisfactory" }));
    expect(send).toBeDisabled();  // the endpoint requires a reason, so a blank one is never sent
    await user.type(screen.getByLabelText("Why? One sentence is enough"), "   ");
    expect(send).toBeDisabled();
    await user.clear(screen.getByLabelText("Why? One sentence is enough"));
    await user.type(screen.getByLabelText("Why? One sentence is enough"), "  Missed the <b>RDA</b> basis  ");
    await user.click(send);
    expect(await screen.findByRole("alert")).toHaveTextContent("reason too short");
    await user.click(send);
    expect(await screen.findByText(/Feedback recorded/)).toBeInTheDocument();
    const posts = calls.filter((c) => c.method === "POST" && c.url.endsWith("/feedback"));
    expect(posts).toHaveLength(2);
    expect(JSON.parse(String(posts[1]!.init!.body))).toEqual({ satisfactory: false, reason: "Missed the <b>RDA</b> basis" });
    expect(new Headers(posts[1]!.init!.headers).get("X-Client-Id")).toMatch(/^web-/);
  });

  it("says plainly when parts of the check are stand-ins, and names them", async () => {
    const components = {
      classifier: { impl: "fssai_contracts.fakes:FakeClassifier", stand_in: true },
      researcher: { impl: "fssai_contracts.fakes:FakeResearcher", stand_in: true },
      retriever: { impl: "fssai_retrieval.faiss_retriever:FaissRetriever", stand_in: false },
    };
    mockApi({ "GET /readyz": () => json({ ...readyz_body(), components }) });
    render(<App />);
    const notice = await screen.findByRole("note");
    expect(notice).toHaveTextContent("Demo mode");
    expect(notice).toHaveTextContent("The classifier and researcher are placeholders");
    expect(notice).not.toHaveTextContent("regulation search");
  });

  it("explains the result in plain words: what needs attention and what to do", async () => {
    mockApi({ "GET /readyz": readyz, [`GET /v1/runs/${RUN_ID}`]: () => json(completedRun()) });
    window.location.hash = `#/runs/${RUN_ID}`;
    render(<App />);
    expect(await screen.findByText(/1 of 2 checked requirements needs attention: Condition for claim 'Source of protein'\. Fix it on the label, then check again\./))
      .toBeInTheDocument();
    expect(screen.getByText(/One row per requirement the system checked/)).toBeInTheDocument();
    expect(screen.getByText(/Quotes verified/)).toBeInTheDocument();
  });
});
