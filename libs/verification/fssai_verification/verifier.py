"""AgentVerifier: the second agent; checks every finding against retrieved text (contexts/Vihaan.md V2.1; A2, A3).

Its own prompt (prompts/verifier_support/<version>.yaml), its own tools (resolve_citation, clause_lookup) and its
own state (the per-finding results below). For each finding, in order:

  1. citations resolve   deterministic: each quote is verbatim text of a passage in dossier.passages
                         (whitespace and quote marks normalised). This alone can fail a finding.
  2. numbers             deterministic: for a nutrient claim, re-read the condition from the *cited passage* and
                         compare it with the request's declared value ourselves, independently of the researcher.
  3. support             one LLM call per attempt (NLI-style): does each cited passage, with the request facts,
                         entail the finding's status? Skipped for findings that already failed 1 or 2.
  4. action              accept   every finding supported
                         retry    something a different search could fix, with a specific hint
                         escalate escalation signals, a missing reference value, a borderline or ambiguous
                                  comparison, or the last attempt failed

Rules (interface: fssai_contracts.interfaces.Verifier; checked by conformance.check_verifier):
- a citation is supported only if its passage was retrieved in this run and its quote is verbatim text of it;
- one FindingCheck per finding; one "verification" step per call; a "tool" step (with the full passage) for each
  clause_lookup; the LLM client records its own "llm" step.

resolve_citation reads only the dossier, so its calls are listed in the verification step rather than recorded
as tool steps: they would spend the run's tool-call budget (A1) on something that touches no corpus.

Env: VERIFIER_SUPPORT_CHECK (llm | off), VERIFIER_TOLERANCE_PCT, VERIFIER_MAX_LOOKUPS,
     PROMPT_VERIFIER_SUPPORT_VERSION (pin; empty = newest).
Switch on: IMPL_VERIFIER=fssai_verification.verifier:AgentVerifier
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import (
    Finding, FindingCheck, FindingStatus, LabelCheckRequest, Passage, PromptTemplate, Regulation,
    ResearchDossier, Verdict, VerifyAction,
)

from .checks import NumericResult, claim_for, numeric_check, resolve_citation

AGENT = "verifier"
PROMPT_NAME = "verifier_support"
PROMPTS_DIR = Path(__file__).parent / "prompts"
_ESCALATE_NUMERIC = {"needs_reference", "borderline", "bases_disagree", "missing_value"}
_TAIL_STEPS = 4  # llm + verification + router + output filter still have to fit after a lookup


def _env(name: str, default: str) -> str:
    return os.environ.get(name, "").split("#", 1)[0].strip() or default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def load_prompt(version: str | None = None) -> PromptTemplate:
    """The verifier's own versioned prompt, same file format and [prompt:] tag rule as fssai_prompts."""
    folder = PROMPTS_DIR / PROMPT_NAME
    versions = sorted((p.stem for p in folder.glob("*.yaml")),
                      key=lambda v: tuple(int(x) if x.isdigit() else 0 for x in v.split(".")))
    chosen = version or _env("PROMPT_VERIFIER_SUPPORT_VERSION", "") or versions[-1]
    data = yaml.safe_load((folder / f"{chosen}.yaml").read_text(encoding="utf-8"))
    if not data["system"].lstrip().startswith(f"[prompt:{PROMPT_NAME}@{chosen}]"):
        raise ValueError(f"{PROMPT_NAME}@{chosen}: system prompt must start with its tag")
    return PromptTemplate(name=PROMPT_NAME, version=chosen, system=data["system"].strip(),
                          user_template=data["user_template"].strip())


def _json(text: str) -> dict | None:
    text = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    try:
        data = json.loads(fenced.group(1) if fenced else text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _data(value: str, limit: int = 600) -> str:
    """Untrusted text (label wording, or a finding written from it) goes in as data; a forged tag cannot close it."""
    safe = re.sub(r"</?\s*label_data[^>]*>", "[removed tag]", value, flags=re.I)[:limit]
    return f"<label_data>{safe}</label_data>"


def request_facts(request: LabelCheckRequest) -> dict:
    """Structured facts for the judge. Free text is reduced to presence flags, except the claims (as data)."""
    label = request.label
    return {
        "declared_category": request.declared_category,
        "package": request.package.model_dump(mode="json", exclude_none=True),
        "nutrition_panel": request.nutrition.model_dump(mode="json", exclude_none=True),
        "veg_status": label.veg_status,
        "has_allergen_statement": bool(label.allergen_statement),
        "has_ingredient_list": bool(label.ingredients.strip()),
        "has_fssai_licence_number": bool(label.fssai_licence_number),
        "has_manufacturer_name_address": bool(label.manufacturer_name_address),
        "has_date_marking": bool(label.date_marking),
        "has_batch_or_lot": bool(label.batch_or_lot),
        "claims_printed": [_data(c, 200) for c in label.claims],
    }


@dataclass
class FindingState:
    """The verifier's working state for one finding."""
    finding: Finding
    citations: list[dict] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    numeric: NumericResult | None = None
    support: str = "not_run"          # not_run | supported | unsupported | contradicted | abstained | skipped
    support_reason: str = ""
    retry: list[str] = field(default_factory=list)      # hints a re-search could act on
    escalate: list[str] = field(default_factory=list)   # reasons a re-search cannot fix

    @property
    def ok(self) -> bool:
        return not self.retry and not self.escalate

    def check(self) -> FindingCheck:
        return FindingCheck(requirement_id=self.finding.requirement_id, supported=self.ok,
                            unresolved_citations=self.unresolved,
                            reason="; ".join(self.escalate + self.retry) or "supported")

    def trace(self) -> dict:
        return {"requirement_id": self.finding.requirement_id, "status": self.finding.status.value,
                "supported": self.ok, "citations": self.citations,
                "numeric": None if self.numeric is None or not self.numeric.applicable else {
                    "outcome": self.numeric.outcome, "detail": self.numeric.detail,
                    "expected": self.numeric.expected.value if self.numeric.expected else None,
                    **self.numeric.evidence},
                "support": self.support, "support_reason": self.support_reason,
                "retry": self.retry, "escalate": self.escalate}


class AgentVerifier:
    def __init__(self, retriever, llm, prompts) -> None:
        self.retriever = retriever
        self.llm = llm
        self.prompts = prompts  # kept for the seam's signature; the support prompt is the verifier's own file
        self.support_mode = _env("VERIFIER_SUPPORT_CHECK", "llm").lower()
        self.tolerance_pct = _env_float("VERIFIER_TOLERANCE_PCT", 20.0)  # FSS-LD-2020 5(3)(d)
        self.max_lookups = int(_env_float("VERIFIER_MAX_LOOKUPS", 2))

    @classmethod
    def from_registry(cls) -> AgentVerifier:
        from fssai_contracts.registry import build
        return cls(retriever=build("retriever"), llm=build("llm"), prompts=build("prompts"))

    # ---------------------------------------------------------------- the seam

    def verify(self, request: LabelCheckRequest, dossier: ResearchDossier, ctx: RunContext) -> Verdict:
        ctx.check_budget()
        t0 = time.monotonic()
        passages = {p.passage_id: p for p in dossier.passages}
        states = [self._deterministic(f, request, passages) for f in dossier.findings]
        lookups = self._lookups(states, passages, ctx)
        escalating = bool(dossier.escalation_signals) or any(s.escalate for s in states)
        prompt = None if escalating else self._support(states, request, passages, ctx)  # no LLM step for a foregone escalation
        verdict = self._decide(states, dossier, ctx)
        ctx.record(agent=AGENT, kind="verification", name="verify", latency_ms=(time.monotonic() - t0) * 1000,
                   input={"attempt": dossier.attempt, "findings": len(dossier.findings),
                          "passages": len(dossier.passages), "escalation_signals": dossier.escalation_signals},
                   output={**verdict.model_dump(mode="json"), "findings": [s.trace() for s in states],
                           "tool_calls": [{"tool": "resolve_citation", "passage_id": c["passage_id"],
                                           "resolved": c["resolved"]} for s in states for c in s.citations] + lookups},
                   prompt_name=prompt.name if prompt else None, prompt_version=prompt.version if prompt else None)
        ctx.event("verified", action=verdict.action.value, attempt=dossier.attempt,
                  unsupported=sum(not s.ok for s in states))
        return verdict

    # ---------------------------------------------------------------- checks 1 and 2

    def _deterministic(self, f: Finding, request: LabelCheckRequest, passages: dict[str, Passage]) -> FindingState:
        s = FindingState(finding=f)
        decisive = f.status in (FindingStatus.MET, FindingStatus.UNMET)
        if decisive and not f.citations:
            s.retry.append(f"{f.requirement_id}: '{f.status.value}' has no citation; find the provision that sets "
                           f"this requirement and quote it verbatim")
        for c in f.citations:
            r = resolve_citation(c, passages)
            s.citations.append({"passage_id": c.passage_id, "clause_id": c.clause_id, "regulation": c.regulation.value,
                                "resolved": r.resolved, "problem": r.problem})
            if r.resolved:
                continue
            s.unresolved.append(c.passage_id)
            if r.problem == "not_verbatim":
                elsewhere = next((p.passage_id for p in passages.values() if c.quote.strip() and c.quote in p.text), None)
                s.retry.append(f"{f.requirement_id}: the quote is not verbatim text of {c.passage_id}"
                               + (f" (it is in {elsewhere}; cite that passage)" if elsewhere
                                  else f"; copy the words exactly from {c.regulation.value} {c.clause_id}"))
            elif r.problem == "empty_quote":
                s.retry.append(f"{f.requirement_id}: empty quote for {c.passage_id}; quote the clause verbatim")
            else:  # not_retrieved: refined by clause_lookup below
                s.retry.append(f"{f.requirement_id}: {c.passage_id} was never retrieved in this run; "
                               f"clause_lookup {c.regulation.value} {c.clause_id} and quote it verbatim")

        claim = claim_for(f, request.label.claims)
        if claim:
            cited = [passages[c["passage_id"]] for c in s.citations if c["resolved"]]
            s.numeric = numeric_check(f, claim, request, cited, self.tolerance_pct)
            n = s.numeric
            if n.outcome == "mismatch":
                s.retry.append(f"{f.requirement_id}: {n.detail}; re-derive the status from the condition in "
                               f"{', '.join(p.clause_id for p in cited)} and nutrition values exactly as declared")
            elif n.outcome in _ESCALATE_NUMERIC:
                s.escalate.append(f"{f.requirement_id}: {n.detail}")
        return s

    def _lookups(self, states: list[FindingState], passages: dict[str, Passage], ctx: RunContext) -> list[dict]:
        """The clause_lookup tool: for a citation to a passage that was never retrieved, does the clause exist?
        Its answer only sharpens the retry hint; it never makes a finding supported (A3)."""
        done: list[dict] = []
        for s in states:
            for c in s.finding.citations:
                if c.passage_id in passages or len(done) >= self.max_lookups:
                    continue
                if len(ctx.steps) + 1 + _TAIL_STEPS > ctx.limits.max_steps or \
                        ctx.tool_calls >= ctx.limits.max_tool_calls or ctx.remaining_s() < 2:
                    return done  # shortcut: no budget for a lookup; the generic hint stays
                ctx.check_budget(tool_call=True)
                t0 = time.monotonic()
                hit = self.retriever.get_clause(c.regulation, c.clause_id, ctx)
                ctx.record(agent=AGENT, kind="tool", name="clause_lookup", latency_ms=(time.monotonic() - t0) * 1000,
                           input={"regulation": c.regulation.value, "clause_id": c.clause_id},
                           output={"passages": [hit.model_dump(mode="json")] if hit else []})
                done.append({"tool": "clause_lookup", "regulation": c.regulation.value, "clause_id": c.clause_id,
                             "found": hit is not None})
                old = next((h for h in s.retry if c.passage_id in h and "never retrieved" in h), None)
                if old is None:
                    continue
                s.retry.remove(old)
                if hit is None:
                    s.retry.append(f"{s.finding.requirement_id}: {c.regulation.value} has no clause '{c.clause_id}'; "
                                   f"search {c.regulation.value} for {s.finding.requirement} and cite what is retrieved")
                else:
                    s.retry.append(f"{s.finding.requirement_id}: clause_lookup {c.regulation.value} {c.clause_id} "
                                   f"(it exists as {hit.passage_id} but was not retrieved in this run) and quote it verbatim")
        return done

    # ---------------------------------------------------------------- check 3

    def _support(self, states: list[FindingState], request: LabelCheckRequest, passages: dict[str, Passage],
                 ctx: RunContext) -> PromptTemplate | None:
        todo = [s for s in states if s.ok and any(c["resolved"] for c in s.citations)]
        if not todo:
            return None
        if self.support_mode == "off":
            for s in todo:
                s.support = "skipped"
            return None
        if len(ctx.steps) + _TAIL_STEPS > ctx.limits.max_steps:
            for s in todo:
                s.support = "skipped"
                s.escalate.append(f"{s.finding.requirement_id}: no run budget left to check that the passage "
                                  "supports the finding")
            return None
        prompt = load_prompt()
        blocks = []
        for s in todo:
            f = s.finding
            cited = "\n".join(f"    [{c.passage_id}] {c.regulation.value} {c.clause_id}: "
                              f"{passages[c.passage_id].text[:1500]}"
                              for c in f.citations if c.passage_id in passages)
            blocks.append(f"- requirement_id: {f.requirement_id}\n  requirement: {_data(f.requirement, 300)}\n"
                          f"  status: {f.status.value}\n  explanation: {_data(f.explanation)}\n  cited passages:\n{cited}")
        messages = prompt.render(facts=json.dumps(request_facts(request)), findings="\n".join(blocks),
                                 input="\n".join(blocks))  # `input` keeps placeholder prompt stores working
        ctx.check_budget()
        resp = self.llm.complete(messages, ctx, agent=AGENT, step="support_check", prompt=prompt, json_mode=True)
        data = _json(resp.text) or {}
        labels = {str(c.get("requirement_id", "")).strip(): c for c in data.get("checks", []) if isinstance(c, dict)}
        for s in todo:
            got = labels.get(s.finding.requirement_id)
            label = str(got.get("label", "")).strip().lower() if got else ""
            if label not in ("supported", "unsupported", "contradicted"):
                # shortcut: an unparseable or missing judgement abstains and the deterministic checks stand;
                # set VERIFIER_SUPPORT_CHECK=off to make that explicit, or tighten this once a judge is calibrated.
                s.support = "abstained"
                continue
            s.support, s.support_reason = label, str(got.get("reason", ""))[:300]
            if label != "supported":
                s.retry.append(f"{s.finding.requirement_id}: the cited text does not support '{s.finding.status.value}'"
                               f" ({s.support_reason or label}); search for the provision that decides "
                               f"{s.finding.requirement}")
        return prompt

    # ---------------------------------------------------------------- check 4

    def _decide(self, states: list[FindingState], dossier: ResearchDossier, ctx: RunContext) -> Verdict:
        checks = [s.check() for s in states]
        escalations = [e for s in states for e in s.escalate]
        retries = [r for s in states for r in s.retry]
        if dossier.escalation_signals or escalations:
            return Verdict(action=VerifyAction.ESCALATE, checks=checks,
                           escalation_reason="; ".join([*dossier.escalation_signals, *escalations]))
        if not dossier.findings:
            retries = ["no findings were produced: search FSS-LD-2020 for the mandatory label declarations and "
                       "FSS-AC-2018 for the condition of each printed claim"]
        if not retries:
            return Verdict(action=VerifyAction.ACCEPT, checks=checks)
        if dossier.attempt >= ctx.limits.max_research_attempts:
            return Verdict(action=VerifyAction.ESCALATE, checks=checks,
                           escalation_reason=f"still unsupported after {dossier.attempt} research attempts: "
                                             + "; ".join(retries))
        return Verdict(action=VerifyAction.RETRY, checks=checks, retry_hint=self._hint(retries, dossier))

    @staticmethod
    def _hint(retries: list[str], dossier: ResearchDossier) -> str:
        """Specific problems first (the researcher searches with the hint's opening words), then a strategy that
        changes with each attempt, so a retry is never the same search again."""
        claims_reg = any(c.regulation == Regulation.CLAIMS_2018 for f in dossier.findings for c in f.citations)
        strategy = {1: "Strategy: look up the named clauses directly with clause_lookup and quote them verbatim.",
                    2: "Strategy: search the other regulation as well"
                       + ("" if claims_reg else " (FSS-AC-2018 for claim conditions)")
                       + ", with short queries naming the nutrient and the claim word."}
        hint = "; ".join(dict.fromkeys(retries))
        return f"{hint[:700]} {strategy.get(dossier.attempt, strategy[2])}"
