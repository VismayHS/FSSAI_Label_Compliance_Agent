"""Fake implementations of every interface, so nobody waits on anybody.

They are deliberately simple and deterministic. The regulation "text" below is
PLACEHOLDER content, not real FSSAI text, and the protein threshold is made up.
Real clause text and values come from the corpus (Nishkal) and eval set (Vihaan).
"""
from __future__ import annotations

import json
import os
import time
import uuid

from pydantic import ValidationError

from .context import RunContext
from .interfaces import ProviderUnavailable
from .schemas import (
    Citation, Classification, DetectedClaim, FieldError, Finding, FindingCheck, FindingStatus,
    GateDecision, GuardrailReport, LabelCheckRequest, LLMResponse, Passage,
    PromptTemplate, Regulation, ResearchDossier, Route, Routing, RunResult, RunStatus, Verdict,
    VerifyAction,
)

FAKE_PROTEIN_THRESHOLD_G = 10.0  # PLACEHOLDER, not the real FSSAI condition

FAKE_PASSAGES = [
    Passage(
        passage_id="fake-ld-nutrition", regulation=Regulation.LABELLING_2020, clause_id="FAKE-LD-NUTRITION",
        heading_path=["[PLACEHOLDER]", "Nutritional information"], doc_version="fake",
        text="[PLACEHOLDER, NOT REAL REGULATION TEXT] Nutritional information shall be declared "
             "per 100 g or 100 ml, including energy, protein, carbohydrate, total sugars and total fat.",
    ),
    Passage(
        passage_id="fake-ld-allergen", regulation=Regulation.LABELLING_2020, clause_id="FAKE-LD-ALLERGEN",
        heading_path=["[PLACEHOLDER]", "Allergen declaration"], doc_version="fake",
        text="[PLACEHOLDER, NOT REAL REGULATION TEXT] Ingredients known to cause allergies shall be "
             "declared separately on the label.",
    ),
    Passage(
        passage_id="fake-ac-protein", regulation=Regulation.CLAIMS_2018, clause_id="FAKE-AC-PROTEIN",
        heading_path=["[PLACEHOLDER]", "Nutrition claims", "Protein"], doc_version="fake",
        text="[PLACEHOLDER, NOT REAL REGULATION TEXT] A claim that a food is a source of protein may be "
             f"made only where the food contains at least {FAKE_PROTEIN_THRESHOLD_G:g} g protein per 100 g.",
    ),
]

_INJECTION_MARKERS = ("ignore previous instructions", "ignore all previous", "you are now", "system prompt")


def _free_text_fields(request: LabelCheckRequest) -> dict[str, str]:
    label = request.label
    fields = {
        "label.front_of_pack_text": label.front_of_pack_text,
        "label.ingredients": label.ingredients,
        "label.allergen_statement": label.allergen_statement or "",
        "label.other_text": label.other_text or "",
    }
    fields.update({f"label.claims[{i}]": c for i, c in enumerate(label.claims)})
    return fields


class FakeRequestGate:
    """Shape validation only. Real ranges, categories and cross-field rules: libs/gate."""

    def __init__(self) -> None:
        self.quarantine: dict[str, dict] = {}

    def check(self, raw: dict, client_id: str) -> GateDecision:
        try:
            return GateDecision(accepted=True, request=LabelCheckRequest.model_validate(raw))
        except ValidationError as exc:
            errors = [FieldError(loc=".".join(str(p) for p in e["loc"]), message=e["msg"], code=e["type"])
                      for e in exc.errors()]
            qid = uuid.uuid4().hex
            self.quarantine[qid] = {"raw": raw, "client_id": client_id,
                                    "errors": [e.model_dump() for e in errors]}
            return GateDecision(accepted=False, errors=errors, quarantine_id=qid)


class FakeRetriever:
    """Keyword-overlap search over FAKE_PASSAGES."""

    def search(self, query, ctx, *, k=5, regulation=None):
        words = set(query.lower().split())
        pool = [p for p in FAKE_PASSAGES if regulation is None or p.regulation == regulation]
        scored = [(len(words & set(p.text.lower().split())), p) for p in pool]
        scored.sort(key=lambda t: t[0], reverse=True)
        return [p.model_copy(update={"score": float(s)}) for s, p in scored[:k] if s > 0]

    def get_clause(self, regulation, clause_id, ctx):
        return next((p for p in FAKE_PASSAGES
                     if p.regulation == regulation and p.clause_id == clause_id), None)


class FakeLLM:
    """Returns a fixed JSON answer after FAKE_LLM_DELAY_S. Set FAKE_LLM_FAIL=1 to simulate an outage."""

    def complete(self, messages, ctx, *, agent, step, prompt=None, json_mode=False):
        if os.environ.get("FAKE_LLM_FAIL") == "1":
            ctx.record(agent=agent, kind="llm", name=step, error="fake provider down")
            raise ProviderUnavailable("fake provider down")
        delay = float(os.environ.get("FAKE_LLM_DELAY_S", "0") or 0)
        time.sleep(delay)
        resp = LLMResponse(text=json.dumps({"answer": "fake"}), model_alias="fake",
                           prompt_tokens=100, completion_tokens=20, latency_ms=delay * 1000)
        ctx.record(agent=agent, kind="llm", name=step, latency_ms=resp.latency_ms,
                   prompt_name=prompt.name if prompt else None,
                   prompt_version=prompt.version if prompt else None,
                   prompt_tokens=resp.prompt_tokens, completion_tokens=resp.completion_tokens)
        return resp


class FakePromptStore:
    def get(self, name, version=None):
        return PromptTemplate(name=name, version=version or "fake-v0",
                              system="You are a placeholder prompt.", user_template="{input}")


class FakeGuardrails:
    """Naive marker matching. Real injection/toxicity/output filtering: libs/guardrails."""

    def screen_input(self, request, ctx):
        flags = [f"prompt_injection:{name}" for name, text in _free_text_fields(request).items()
                 if any(m in text.lower() for m in _INJECTION_MARKERS)]
        report = GuardrailReport(stage="input", allowed=not flags, flags=flags)
        ctx.record(agent="guardrails", kind="guardrail", name="screen_input", output=report.model_dump())
        return report

    def filter_output(self, result, ctx):
        report = GuardrailReport(stage="output", allowed=True)
        ctx.record(agent="guardrails", kind="guardrail", name="filter_output", output=report.model_dump())
        return result.model_copy(update={"guardrails": [*result.guardrails, report]})


class FakeClassifier:
    """Trusts the declared category. In scope iff it is listed in CORPUS_CATEGORIES."""

    def classify(self, request, ctx):
        allowed = {c.strip() for c in os.environ.get("CORPUS_CATEGORIES", "demo-category").split(",")}
        claims = [DetectedClaim(text=c, claim_type="nutrient_content" if "protein" in c.lower() else "other",
                                nutrient="protein" if "protein" in c.lower() else None)
                  for c in request.label.claims]
        result = Classification(category=request.declared_category,
                                in_scope=request.declared_category in allowed, claims=claims)
        ctx.record(agent="classifier", kind="classification", name="classify", output=result.model_dump())
        return result


class FakeResearcher:
    """Single pass, no LLM: checks the allergen line and any protein claim against FAKE_PASSAGES."""

    def __init__(self, retriever=None) -> None:
        self.retriever = retriever or FakeRetriever()

    @classmethod
    def from_registry(cls):
        from .registry import build
        return cls(retriever=build("retriever"))

    def _search(self, query, ctx, dossier, **kw):
        ctx.check_budget(tool_call=True)
        hits = self.retriever.search(query, ctx, **kw)
        # Tool steps carry the full passages so a run can be reconstructed from its trace (D5).
        ctx.record(agent="researcher", kind="tool", name="corpus_search",
                   input={"query": query, **kw}, output={"passages": [p.model_dump() for p in hits]})
        dossier.queries.append(query)
        dossier.passages.extend(p for p in hits if p.passage_id not in {x.passage_id for x in dossier.passages})
        return hits

    def research(self, request, classification, ctx, *, retry_hint=None, previous=None):
        dossier = ResearchDossier(attempt=(previous.attempt + 1) if previous else 1)
        hits = self._search("allergies declared separately", ctx, dossier)
        if hits:
            p = hits[0]
            status = FindingStatus.MET if request.label.allergen_statement else FindingStatus.UNMET
            dossier.findings.append(Finding(
                requirement_id="LBL-ALLERGEN", requirement="Allergen declaration", status=status,
                explanation="Allergen statement present." if status == FindingStatus.MET
                else "No allergen statement on the label.",
                citations=[Citation(regulation=p.regulation, clause_id=p.clause_id,
                                    passage_id=p.passage_id, quote=p.text)]))  # verbatim, PLACEHOLDER marker included
        for claim in classification.claims:
            if claim.nutrient != "protein":
                continue
            hits = self._search("source of protein claim", ctx, dossier, regulation=Regulation.CLAIMS_2018)
            if not hits:
                dossier.escalation_signals.append(f"no claim condition found for '{claim.text}'")
                continue
            p = hits[0]
            ok = request.nutrition.protein_g >= FAKE_PROTEIN_THRESHOLD_G
            dossier.findings.append(Finding(
                requirement_id="CLM-PROTEIN-SOURCE", requirement=f"Condition for claim '{claim.text}'",
                status=FindingStatus.MET if ok else FindingStatus.UNMET,
                explanation=f"Declared protein {request.nutrition.protein_g} g vs condition "
                            f"{FAKE_PROTEIN_THRESHOLD_G:g} g per 100 g.",
                citations=[Citation(regulation=p.regulation, clause_id=p.clause_id,
                                    passage_id=p.passage_id, quote=p.text)]))  # verbatim, PLACEHOLDER marker included
        return dossier


class FakeVerifier:
    """Deterministic citation resolution only: every quote must appear in a retrieved passage."""

    def verify(self, request, dossier, ctx):
        by_id = {p.passage_id: p for p in dossier.passages}
        checks = []
        for f in dossier.findings:
            unresolved = [c.passage_id for c in f.citations
                          if c.passage_id not in by_id or c.quote not in by_id[c.passage_id].text]
            supported = bool(f.citations) and not unresolved
            checks.append(FindingCheck(requirement_id=f.requirement_id, supported=supported,
                                       unresolved_citations=unresolved,
                                       reason="" if supported else "citation does not resolve to retrieved text"))
        if dossier.escalation_signals:
            verdict = Verdict(action=VerifyAction.ESCALATE, checks=checks,
                              escalation_reason="; ".join(dossier.escalation_signals))
        elif all(c.supported for c in checks):
            verdict = Verdict(action=VerifyAction.ACCEPT, checks=checks)
        else:
            bad = [c.requirement_id for c in checks if not c.supported]
            verdict = Verdict(action=VerifyAction.RETRY, checks=checks,
                              retry_hint=f"re-search with clause-level queries for: {', '.join(bad)}")
        ctx.record(agent="verifier", kind="verification", name="verify", output=verdict.model_dump())
        return verdict


class FakeRouter:
    def route(self, request, classification, dossier, verdict, ctx):
        if verdict.action != VerifyAction.ACCEPT:
            routing = Routing(route=Route.REGULATORY_REVIEW, reason="Could not verify the finding.",
                              escalation_reason=verdict.escalation_reason or "verification did not pass")
        elif any(f.status in (FindingStatus.UNMET, FindingStatus.CANNOT_DETERMINE) for f in dossier.findings):
            unmet = [f.requirement_id for f in dossier.findings if f.status != FindingStatus.MET]
            routing = Routing(route=Route.REVISE_AND_RECHECK, reason=f"Unmet or undetermined: {', '.join(unmet)}")
        else:
            routing = Routing(route=Route.CLEAR_FOR_PRINT, reason="All checked requirements met, citations verified.")
        ctx.record(agent="router", kind="routing", name="route", output=routing.model_dump())
        return routing


class InMemoryRunStore:
    def __init__(self) -> None:
        self._runs: dict[str, RunStatus] = {}

    def save(self, status):
        self._runs[status.run_id] = status

    def get(self, run_id):
        return self._runs.get(run_id)

    def recent(self, limit=50):
        return sorted(self._runs.values(), key=lambda s: s.updated_at, reverse=True)[:limit]


def fake_result(run_id: str = "fake") -> RunResult:
    """A canned result, handy for frontend and API work before the pipeline exists."""
    return RunResult(run_id=run_id, correlation_id=run_id, complete=True,
                     routing=Routing(route=Route.REVISE_AND_RECHECK, reason="fake result"))
