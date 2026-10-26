"""The L3 metrics, computed per response and aggregated per run of the eval set.

Unit of judgement: a **statement** is one finding (its requirement, status and explanation). The exact definitions
(also in DEFINITIONS below, written into every results file, and in docs/report/verification-and-evaluation.md):

- groundedness       per statement: 0 if any citation fails to resolve verbatim to a passage retrieved in this run
                     (or a met/unmet statement has no citation); else the judge's support score of the statement
                     against the cited passages (0..1). Per response: mean over its statements. Reported: mean over
                     responses that make at least one statement.
- context relevance  per retrieved passage (every passage any tool returned in the run): the judge's relevance of the
                     passage to the scenario question (0..1). Per response: mean over its passages.
- faithfulness       per *decisive* statement (met or unmet): 1 if its status follows from its cited passages plus the
                     request's declared values, else 0. Claim conditions with numbers are re-derived deterministically
                     (fssai_verification.checks); others by the judge (llm/trulens only). Reported: share over judged
                     decisive statements, with coverage.
- hallucination      per response: true if at least one statement is unsupported (groundedness < 0.5) or not
                     faithful (faithfulness 0). Reported: share of responses that make statements (glossary: count per
                     response, not as an average).
Plus, against the scenario's expected values: route accuracy, finding accuracy, escalation recall, unsafe-clear rate.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from statistics import mean

from fssai_contracts.schemas import (
    EvalScenario, Finding, FindingStatus, LabelCheckRequest, Passage, Route, RunResult,
)
from fssai_verification.checks import claim_for, numeric_check, resolve_citation

from .judges import Judge

DEFINITIONS = {
    "statement": "one finding: its requirement, status and explanation",
    "groundedness": "per statement: 0 if a citation does not resolve verbatim to text retrieved in this run (or a "
                    "met/unmet statement cites nothing), else the judge's support score of the statement against "
                    "its cited passages (0-1); per response the mean over statements; reported as the mean over "
                    "responses with at least one statement",
    "context_relevance": "per retrieved passage, the judge's relevance to the scenario question (0-1); per response "
                         "the mean over passages; reported as the mean over responses that retrieved anything",
    "faithfulness": "per met/unmet statement: 1 if the status follows from its cited passages plus the request's "
                    "declared values (numeric claim conditions re-derived deterministically, others judged), else 0; "
                    "reported as the share over judged statements",
    "hallucination_rate": "share of responses (that make statements) with at least one statement that is "
                          "unsupported (groundedness < 0.5) or not faithful",
    "route_accuracy": "share of scenarios routed to the expected route",
    "finding_accuracy": "share of expected (requirement, status) pairs found with that status",
    "escalation_recall": "share of scenarios expected at regulatory-review that were routed there",
    "unsafe_clear_rate": "share of scenarios routed clear-for-print that were not expected to clear",
}
UNSUPPORTED_BELOW = 0.5
TOOL_PASSAGES = "passages"

# ---------------------------------------------------------------- requirement ids

_SYNONYMS = {"LICENSE": "LICENCE", "FIBER": "FIBRE", "VEGETARIAN": "VEG", "NONVEG": "VEG", "LOGO": "MARK",
             "SYMBOL": "MARK", "NUTRITIONAL": "NUTRITION", "SUGAR": "SUGARS", "INGREDIENT": "INGREDIENTS",
             "ALLERGENS": "ALLERGEN", "DATE": "DATE", "EXPIRY": "DATE", "MARKING": "DATE"}
_DROP = {"INFORMATION", "DECLARATION", "INFO", "STATEMENT", "LIST", "OF", "THE", "PANEL", "FSSAI"}


def id_tokens(rid: str) -> set[str]:
    toks = [t for t in re.split(r"[^A-Z0-9]+", rid.upper()) if t]
    return {_SYNONYMS.get(t, t) for t in toks if t not in _DROP}


def match_finding(expected_id: str, findings: list[Finding]) -> Finding | None:
    """Exact id, else the best same-prefix id sharing at least half its tokens (LBL-VEG-MARK ~ LBL-VEG-LOGO)."""
    exact = next((f for f in findings if f.requirement_id == expected_id), None)
    if exact:
        return exact
    want = id_tokens(expected_id)
    prefix = expected_id.split("-", 1)[0].upper()
    best, best_score = None, 0.0
    for f in findings:
        if f.requirement_id.split("-", 1)[0].upper() != prefix:
            continue
        got = id_tokens(f.requirement_id)
        score = len(want & got) / len(want | got)
        if score > best_score:
            best, best_score = f, score
    return best if best_score >= 0.5 else None


# ---------------------------------------------------------------- inputs from a run

def retrieved_passages(result: RunResult) -> dict[str, Passage]:
    """Everything any tool returned in this run (the D5 trace), by passage id."""
    out: dict[str, Passage] = {}
    for s in result.steps:
        if s.kind != "tool":
            continue
        for p in s.output.get(TOOL_PASSAGES, []) or []:
            if isinstance(p, dict) and "passage_id" in p:
                try:
                    out.setdefault(p["passage_id"], Passage.model_validate(p))
                except Exception:  # noqa: BLE001 - a malformed trace entry is not retrieved text
                    continue
    return out


def question_for(request: LabelCheckRequest) -> str:
    claims = ", ".join(f"'{c}'" for c in request.label.claims) or "none"
    return (f"A pre-packaged {request.declared_category.replace('-', ' ')} label carries the claims {claims}. Which "
            "FSSAI labelling requirements apply to it, and what conditions must each claim meet?")


def _base_clause(passage_id: str) -> str:
    return re.split(r"[~+#]", passage_id.split(":", 1)[-1], maxsplit=1)[0]


def is_gold(p: Passage, scenario: EvalScenario | None) -> bool | None:
    if scenario is None or not scenario.supporting:
        return None
    for sp in scenario.supporting:
        if sp.regulation != p.regulation:
            continue
        clause = _base_clause(p.passage_id)
        if p.clause_id == sp.clause_id or clause == sp.clause_id or clause.startswith(sp.clause_id + "("):
            return True
    return False


def facts_for(request: LabelCheckRequest) -> dict:
    label = request.label
    return {"category": request.declared_category, "package": request.package.model_dump(mode="json", exclude_none=True),
            "nutrition": request.nutrition.model_dump(mode="json", exclude_none=True), "claims": label.claims,
            "veg_status": label.veg_status, "has_allergen_statement": bool(label.allergen_statement),
            "has_ingredients": bool(label.ingredients.strip()), "has_licence": bool(label.fssai_licence_number),
            "has_date_marking": bool(label.date_marking), "has_batch": bool(label.batch_or_lot),
            "has_manufacturer": bool(label.manufacturer_name_address)}


# ---------------------------------------------------------------- per response

@dataclass
class StatementScore:
    requirement_id: str
    status: str
    citations_resolve: bool
    groundedness: float | None
    faithful: bool | None = None
    faithful_by: str = ""
    unsupported: bool = False


@dataclass
class ResponseScore:
    scenario_id: str
    route: str | None
    expected_route: str | None
    complete: bool | None
    statements: list[StatementScore] = field(default_factory=list)
    groundedness: float | None = None
    context_relevance: float | None = None
    passages_retrieved: int = 0
    faithfulness: float | None = None
    hallucinated: bool | None = None
    citation_resolution: float | None = None
    expected_findings: dict[str, dict] = field(default_factory=dict)
    error: str | None = None
    provider_failed: bool = False   # the LLM provider gave out (rate limit, outage): not scored, rerun with --resume
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    llm_calls: int = 0
    tool_calls: int = 0
    tags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


DECISIVE = (FindingStatus.MET, FindingStatus.UNMET)


def score_response(result: RunResult, request: LabelCheckRequest, judge: Judge,
                   scenario: EvalScenario | None = None, *, relevance_cap: int = 12) -> ResponseScore:
    retrieved = retrieved_passages(result)
    row = ResponseScore(scenario_id=scenario.scenario_id if scenario else result.run_id,
                        route=result.routing.route.value, complete=result.complete,
                        expected_route=scenario.expected_route.value if scenario else None,
                        passages_retrieved=len(retrieved), cost_usd=result.totals.cost_usd,
                        latency_ms=result.totals.latency_ms, llm_calls=result.totals.llm_calls,
                        tool_calls=result.totals.tool_calls, tags=list(scenario.tags) if scenario else [])
    facts = facts_for(request)
    n_cites = n_ok = 0
    for f in result.findings:
        decisive = f.status in DECISIVE
        if not f.citations and not decisive:
            continue  # "cannot determine" / "not applicable" with nothing cited asserts no support
        results = [resolve_citation(c, retrieved) for c in f.citations]
        n_cites += len(results)
        n_ok += sum(r.resolved for r in results)
        resolves = bool(results) and all(r.resolved for r in results)
        cited = [retrieved[c.passage_id] for c, r in zip(f.citations, results) if r.resolved]
        g = 0.0
        if resolves:
            g = judge.support(f"{f.requirement}: {f.status.value}. {f.explanation}",
                              "\n\n".join(f"[{p.regulation.value} {p.clause_id}] {p.text}" for p in cited))
        st = StatementScore(f.requirement_id, f.status.value, resolves, g)
        if decisive:
            claim = claim_for(f, request.label.claims)
            numeric = numeric_check(f, claim, request, cited, 0.0) if claim and resolves else None
            if not resolves:
                st.faithful, st.faithful_by = False, "citation"
            elif numeric is not None and numeric.applicable:
                st.faithful, st.faithful_by = numeric.outcome == "consistent", f"numeric:{numeric.outcome}"
            else:
                verdict = judge.status_follows(facts, f.requirement, f.status.value, f.explanation,
                                               "\n\n".join(f"[{p.passage_id}] {p.text}" for p in cited))
                if verdict is not None:
                    st.faithful, st.faithful_by = verdict, judge.name
        st.unsupported = (st.groundedness is not None and st.groundedness < UNSUPPORTED_BELOW) or st.faithful is False
        row.statements.append(st)

    gs = [s.groundedness for s in row.statements if s.groundedness is not None]
    row.groundedness = round(mean(gs), 4) if gs else None
    fs = [s.faithful for s in row.statements if s.faithful is not None]
    row.faithfulness = round(sum(fs) / len(fs), 4) if fs else None
    row.hallucinated = any(s.unsupported for s in row.statements) if row.statements else None
    row.citation_resolution = round(n_ok / n_cites, 4) if n_cites else None

    if retrieved:
        question = question_for(request)
        # cap judged passages per response (most relevant first by the retriever's own order) to bound judge cost
        rel = [judge.relevance(question, p.text, gold=is_gold(p, scenario)) for p in list(retrieved.values())[:relevance_cap]]
        rel = [r for r in rel if r is not None]
        row.context_relevance = round(mean(rel), 4) if rel else None

    if scenario is not None:
        for rid, status in scenario.expected_findings.items():
            got = match_finding(rid, result.findings)
            row.expected_findings[rid] = {"expected": status.value, "got": got.status.value if got else None,
                                          "matched_id": got.requirement_id if got else None,
                                          "correct": bool(got and got.status == status)}
    return row


# ---------------------------------------------------------------- aggregate

def _share(xs: list[bool]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def _avg(xs: list[float]) -> float | None:
    return round(mean(xs), 4) if xs else None


def aggregate(rows: list[ResponseScore]) -> dict:
    # A run the provider cut short says nothing about the system's quality: it is counted, never scored.
    ok = [r for r in rows if r.error is None and not r.provider_failed]
    stmts = [s for r in ok for s in r.statements]
    expected = [v for r in ok for v in r.expected_findings.values()]
    with_statements = [r for r in ok if r.hallucinated is not None]
    by_tag: dict[str, list[bool]] = {}
    for r in ok:
        for t in r.tags:
            by_tag.setdefault(t, []).append(r.route == r.expected_route)
    cleared = [r for r in ok if r.route == Route.CLEAR_FOR_PRINT.value]
    return {
        "scenarios": len(ok), "errors": sum(r.error is not None for r in rows),
        "provider_failures": sum(r.provider_failed for r in rows),
        "groundedness": _avg([r.groundedness for r in ok if r.groundedness is not None]),
        "context_relevance": _avg([r.context_relevance for r in ok if r.context_relevance is not None]),
        "faithfulness": _share([s.faithful for s in stmts if s.faithful is not None]),
        "faithfulness_coverage": f"{sum(s.faithful is not None for s in stmts)}/"
                                 f"{sum(s.status in ('met', 'unmet') for s in stmts)} decisive statements judged",
        "hallucination_rate": _share([r.hallucinated for r in with_statements]),
        "responses_with_statements": len(with_statements),
        "citation_resolution": _avg([r.citation_resolution for r in ok if r.citation_resolution is not None]),
        "route_accuracy": _share([r.route == r.expected_route for r in ok if r.expected_route]),
        "finding_accuracy": _share([e["correct"] for e in expected]),
        "findings_missing": sum(e["got"] is None for e in expected),
        "escalation_recall": _share([r.route == Route.REGULATORY_REVIEW.value for r in ok
                                     if r.expected_route == Route.REGULATORY_REVIEW.value]),
        "unsafe_clear_rate": _share([r.expected_route != Route.CLEAR_FOR_PRINT.value for r in cleared]) if cleared else 0.0,
        "incomplete_runs": sum(r.complete is False for r in ok),
        "route_accuracy_by_tag": {t: _share(v) for t, v in sorted(by_tag.items())},
        "mean_cost_usd": _avg([r.cost_usd for r in ok]), "mean_latency_ms": _avg([r.latency_ms for r in ok]),
        "mean_llm_calls": _avg([r.llm_calls for r in ok]), "mean_tool_calls": _avg([r.tool_calls for r in ok]),
    }
