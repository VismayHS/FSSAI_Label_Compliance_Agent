import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import App from "./App";
import { completedRun, fullTrace, json, mockApi, readyz, RUN_ID } from "./test/api";

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
    expect(screen.getByRole("button", { name: "Check the §4.1 example" })).toBeInTheDocument();
    expect(screen.getByText(/never approves a label/i)).toBeInTheDocument();
    expect(await screen.findByText(/API ready · inline execution/)).toBeInTheDocument();
    expect(screen.getByLabelText("Product name")).toHaveValue("Roasted chana");
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
    expect(within(protein).getByText("at least 10 g protein")).toBeInTheDocument();

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
});
