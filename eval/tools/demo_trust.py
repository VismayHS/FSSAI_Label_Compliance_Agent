"""Rehearse demo items 4, 5 and 6 (contexts/Vihaan.md V4.1). Prints the evidence for each, step by step.

    <venv-python> eval/tools/demo_trust.py --api http://localhost:8000      # against the running stack (#4, #5, #6)
    <venv-python> eval/tools/demo_trust.py --in-process                     # #6 without a stack or an LLM

#4  a malformed request -> 422 with every field error, a quarantine record, and no run row or queue job
#5  an out-of-corpus product, and a claim with no condition in the corpus -> regulatory-review with a reason
#6  a researcher answer whose citation is not verbatim -> the verifier retries with a hint -> fixed or escalated,
    all visible in the trace. Against the stack it prints the verifier's steps of a run; --in-process makes it
    deterministic with a researcher whose first attempt paraphrases its quote.
Exit code 1 if any expected evidence is missing. Uses only the standard library against the API.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLIENT = "demo-vihaan"
FAILED: list[str] = []


def say(text: str = "") -> None:
    print(text, flush=True)


def check(ok: bool, what: str) -> None:
    say(f"   {'OK ' if ok else 'MISSING'}  {what}")
    if not ok:
        FAILED.append(what)


def call(api: str, method: str, path: str, body=None, headers=None) -> tuple[int, dict | str]:
    data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
    req = urllib.request.Request(api.rstrip("/") + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", "X-Client-Id": CLIENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read().decode(), e.code
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


def scenario(sid: str) -> dict:
    for line in (ROOT / "eval" / "scenarios.jsonl").read_text(encoding="utf-8").splitlines():
        s = json.loads(line)
        if s["scenario_id"] == sid:
            return s["request"]
    raise KeyError(sid)


def wait(api: str, run_id: str, timeout_s: float = 180) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        _, status = call(api, "GET", f"/v1/runs/{run_id}")
        if isinstance(status, dict) and status.get("state") in ("completed", "failed"):
            return status
        time.sleep(1)
    return {"state": "timeout"}


def rejected_counter(api: str) -> float | None:
    _, text = call(api, "GET", "/metrics")
    if not isinstance(text, str):
        return None
    for line in text.splitlines():
        if line.startswith('fssai_runs_submitted_total{outcome="rejected"}'):
            return float(line.rsplit(" ", 1)[1])
    return 0.0  # Prometheus omits a labelled counter until its first increment


# ---------------------------------------------------------------- #4

def demo_4(api: str) -> None:
    say("\n#4  Malformed request: rejected at the gate, quarantined, no agent run")
    _, before = call(api, "GET", "/v1/runs?limit=100")
    n_before = len(before) if isinstance(before, list) else None
    rej_before = rejected_counter(api)
    bad = scenario("fibre-source-pass")
    bad["nutrition"].update(added_sugars_g=20, protein_g="lots")
    bad["label"]["fssai_licence_number"] = "123"
    bad["nutrition"]["protien_g"] = 12
    status, body = call(api, "POST", "/v1/runs", bad, {"X-Correlation-Id": "demo-4"})
    say(f"   POST /v1/runs -> {status}")
    for e in body.get("errors", []) if isinstance(body, dict) else []:
        say(f"      {e['code']:14s} {e['loc']:32s} {e['message']}")
    check(status == 422, "422 with field-level errors")
    qid = body.get("quarantine_id") if isinstance(body, dict) else None
    check(bool(qid), f"quarantine id returned ({qid})")
    if qid:
        _, rec = call(api, "GET", f"/v1/quarantine/{qid}")
        if isinstance(rec, dict):
            say(f"   GET /v1/quarantine/{qid} -> {rec.get('error_count')} errors, client {rec.get('client_id')}, "
                f"evidence: {rec.get('evidence', {}).get('note')}")
            check(rec.get("payload") == bad, "quarantine holds the raw payload exactly as sent")
            check(rec.get("evidence", {}).get("run_created") is False, "no run carries this request")
    _, after = call(api, "GET", "/v1/runs?limit=100")
    if n_before is not None and isinstance(after, list):
        check(len(after) == n_before, f"runs before {n_before}, after {len(after)}: no run row was created")
    rej_after = rejected_counter(api)
    if rej_before is not None and rej_after is not None:
        check(rej_after == rej_before + 1, "fssai_runs_submitted_total{outcome=\"rejected\"} went up by one, "
                                           "\"accepted\" (the only path that enqueues) did not")


# ---------------------------------------------------------------- #5

def demo_5(api: str) -> None:
    say("\n#5  Unanswerable cases: escalation, not fabrication")
    for sid in ("out-of-scope-supplement", "claim-without-condition", "s41-protein-clearly-above"):
        status, accepted = call(api, "POST", "/v1/runs", scenario(sid))
        if status != 202:
            check(False, f"{sid}: accepted for a run (got {status})")
            continue
        run = wait(api, accepted["run_id"])
        routing = (run.get("result") or {}).get("routing", {})
        say(f"   {sid}: {routing.get('route')}")
        say(f"      reason: {str(routing.get('reason'))[:200]}")
        findings = (run.get("result") or {}).get("findings", [])
        if any("[PLACEHOLDER" in c["quote"] for f in findings if f["requirement_id"].startswith("CLM") for c in f["citations"]):
            say("      (skipped: this stack runs the contracts' fake retriever, whose PLACEHOLDER condition is a gram "
                "threshold, not the real RDA-based row; switch on IMPL_RETRIEVER for this case)")
            continue
        check(routing.get("route") == "regulatory-review" and bool(routing.get("escalation_reason")),
              f"{sid}: regulatory-review with an escalation reason")
        decisive = [f for f in findings if f["status"] in ("met", "unmet") and f["requirement_id"].startswith("CLM")]
        check(not decisive, f"{sid}: no claim was decided without its condition in the text")


# ---------------------------------------------------------------- #6

def print_verifier_steps(steps: list[dict]) -> int:
    attempts = 0
    for s in steps:
        if s["agent"] == "verifier" and s["kind"] == "verification":
            attempts += 1
            out = s["output"]
            say(f"   [{s['step_index']:2d}] verifier attempt {s['input'].get('attempt')}: {out['action']}")
            for f in out.get("findings", []):
                if not f["supported"]:
                    say(f"        {f['requirement_id']}: {'; '.join(f['retry'] + f['escalate'])[:220]}")
            if out.get("retry_hint"):
                say(f"        retry hint -> {out['retry_hint'][:220]}")
            if out.get("escalation_reason"):
                say(f"        escalation -> {out['escalation_reason'][:220]}")
        elif s["agent"] == "researcher" and s["kind"] == "tool":
            say(f"   [{s['step_index']:2d}] researcher {s['name']} {json.dumps(s['input'])[:120]}")
    return attempts


def demo_6_api(api: str) -> None:
    say("\n#6  Self-verification in a real run's trace (the verifier's steps)")
    status, accepted = call(api, "POST", "/v1/runs", scenario("small-pack-with-claim"))
    if status != 202:
        check(False, f"run accepted (got {status})")
        return
    wait(api, accepted["run_id"])
    _, trace = call(api, "GET", f"/v1/runs/{accepted['run_id']}/trace")
    attempts = print_verifier_steps(trace.get("steps", []) if isinstance(trace, dict) else [])
    check(attempts >= 1, "the verifier's checks are in the trace")
    say("   (whether this run needed a retry depends on the model; --in-process shows a guaranteed one)")


def demo_6_in_process() -> None:
    say("\n#6  Self-verification catches an unsupported answer (in process, deterministic)")
    from fssai_contracts.context import RunContext
    from fssai_contracts.conformance import sample_request
    from fssai_contracts.fakes import (FAKE_PASSAGES, FakeClassifier, FakeGuardrails, FakeLLM, FakePromptStore,
                                       FakeRetriever)
    from fssai_contracts.pipeline import ReferencePipeline
    from fssai_contracts.schemas import Citation, Finding, FindingStatus, ResearchDossier
    from fssai_verification.router import RuleRouter
    from fssai_verification.verifier import AgentVerifier

    allergen = next(p for p in FAKE_PASSAGES if p.passage_id == "fake-ld-allergen")

    class SloppyResearcher:
        """First attempt paraphrases its quote; given the verifier's hint, the second quotes verbatim."""

        def research(self, request, classification, ctx, *, retry_hint=None, previous=None):
            ctx.check_budget(tool_call=True)
            ctx.record(agent="researcher", kind="tool", name="corpus_search", input={"query": retry_hint or "allergen"},
                       output={"passages": [allergen.model_dump(mode="json")]})
            quote = ("allergens must be listed separately" if previous is None
                     else "Ingredients known to cause allergies shall be declared separately on the label.")
            return ResearchDossier(attempt=previous.attempt + 1 if previous else 1, passages=[allergen],
                                   queries=[retry_hint or "allergen"], findings=[Finding(
                                       requirement_id="LBL-ALLERGEN", requirement="Allergen declaration",
                                       status=FindingStatus.MET, explanation="Allergen statement present.",
                                       citations=[Citation(regulation=allergen.regulation, clause_id=allergen.clause_id,
                                                           passage_id=allergen.passage_id, quote=quote)])])

    import os
    os.environ.setdefault("CORPUS_CATEGORIES", "demo-category")
    pipeline = ReferencePipeline(FakeGuardrails(), FakeClassifier(), SloppyResearcher(),
                                 AgentVerifier(FakeRetriever(), FakeLLM(), FakePromptStore()), RuleRouter())
    result = pipeline.run(sample_request(claims=(), category="demo-category"), RunContext.new())
    attempts = print_verifier_steps([s.model_dump(mode="json") for s in result.steps])
    say(f"   route: {result.routing.route.value}: {result.routing.reason[:160]}")
    check(attempts == 2, "attempt 1 retried with a hint, attempt 2 verified")
    check(result.verdict.action.value == "accept", "the corrected answer was accepted only after re-search")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Rehearse demo items 4, 5 and 6.")
    ap.add_argument("--api", help="base URL of the running API, e.g. http://localhost:8000")
    ap.add_argument("--in-process", action="store_true", help="demo #6 without a stack or an LLM")
    args = ap.parse_args(argv)
    if not args.api and not args.in_process:
        ap.error("give --api URL and/or --in-process")
    if args.api:
        demo_4(args.api)
        demo_5(args.api)
        demo_6_api(args.api)
    if args.in_process:
        demo_6_in_process()
    say("\nall evidence present" if not FAILED else f"\nMISSING: {len(FAILED)} item(s)")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
