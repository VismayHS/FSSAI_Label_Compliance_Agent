"""LangGraphResearcher: the research agent, a LangGraph subgraph (docs/contexts/Namith.md M2.1).

Graph:  plan -> sweep -> act <-> run_tool -> coverage -> draft -> finalize

- plan      deterministic: seed suggested searches from the claims and package (no LLM step).
- sweep     deterministic: one search for every claim condition and every labelling requirement that
            applies to this label (REQUIREMENT_TOPICS), so the model cannot skip a requirement by
            finishing early. Costs one tool step each, no LLM step; capped by what the budget allows.
- act       the LLM reflects ("does anything I have read modify, condition or exempt something?") and
            chooses the next tool, or finish. Retrieval is a tool the model chooses, not a fixed stage.
- run_tool  executes the validated call (budget check first, "tool" step with the full passages).
- coverage  safety net: a detected claim whose condition was never searched for in the Claims
            regulation gets one such search, even if the model chose to finish early.
- draft     the LLM writes findings from retrieved passages only; every quote is made verbatim or dropped.
            A finding is kept only for a requirement that was actually searched (see _only_researched).
- finalize  assembles the ResearchDossier.

Rules (interface: fssai_contracts.interfaces.Researcher; conformance.check_researcher):
- ctx.check_budget() before every LLM call and ctx.check_budget(tool_call=True) before every tool call;
  BudgetExceeded and ProviderUnavailable propagate so the pipeline can return an incomplete run (A5);
- every Citation.quote is a verbatim span of a passage in dossier.passages (A3);
- a retry (retry_hint, previous) is attempt previous.attempt + 1 and changes strategy: calls already
  made are not repeated, and the strategy text rotates;
- conflicts, possible exemptions and missing conditions go in escalation_signals, never into guesses.

Switch on: IMPL_RESEARCHER=fssai_agents.researcher:LangGraphResearcher
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import (
    Classification, DetectedClaim, Finding, FindingStatus, LabelCheckRequest, Passage, Regulation,
    ResearchDossier,
)

from . import tools
from .common import data_block, request_facts
from .grounding import cross_references, ground_citations

AGENT = "researcher"
LD, AC = Regulation.LABELLING_2020.value, Regulation.CLAIMS_2018.value
SMALL_PACK_LOOKUP_CM2 = 200  # below this surface area we go and look for an exemption (to look, not to conclude)

STRATEGIES = {
    1: "First pass: find the labelling provisions that apply, then the condition behind each claim.",
    2: "Second pass: the first pass did not satisfy the verifier. Prefer clause_lookup on clauses and "
       "schedules named in passages, and search the other regulation.",
    3: "Last pass: use short queries that name the exact terms from the retry hint; avoid broad searches.",
}


class State(TypedDict, total=False):
    ctx: RunContext
    request: LabelCheckRequest
    claims: list[DetectedClaim]
    retry_hint: str
    attempt: int
    passages: dict[str, Passage]
    queries: list[str]
    calls: list[str]
    history: list[str]
    suggested: list[dict]
    notes: list[str]
    signals: list[str]
    iteration: int
    max_iter: int
    action: dict | None
    findings: list[Finding]


# ---------------------------------------------------------------- helpers

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _sig(tool: str, args: dict) -> str:
    return tool + ":" + json.dumps(args, sort_keys=True)


def _json(text: str) -> dict | None:
    text = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    try:
        data = json.loads(fenced.group(1) if fenced else text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


_QUERY_LINE = re.compile(r"^(?P<q>.*?)(?: \[(?P<reg>FSS-[A-Z]+-\d{4})\])?$", re.DOTALL)


def _calls_from_queries(queries: list[str]) -> list[str]:
    """Rebuild the signatures of calls a previous attempt made from the queries its dossier lists."""
    calls = []
    for line in queries:
        m = _QUERY_LINE.match(line)
        if not m:
            continue
        q, reg = m.group("q"), m.group("reg")
        if q.startswith("clause_lookup ") and reg:
            calls.append(_sig("clause_lookup", {"regulation": reg, "clause_id": q[len("clause_lookup "):]}))
        else:
            calls.append(_sig("corpus_search", {"query": q, "regulation": reg}))
    return calls


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + " ..."


def _format_passages(passages: dict[str, Passage], limit: int) -> str:
    if not passages:
        return "(none yet)"
    return "\n".join(f"[{p.passage_id}] {p.regulation.value} clause {p.clause_id}: {_clip(p.text, limit)}"
                     for p in passages.values())


def _per_passage_chars(n: int, total: int, high: int, low: int) -> int:
    """Characters shown per passage so that n passages together stay near `total` (a free-tier token limit
    applies to the whole prompt). A quote is a span of what is shown, so it is still verbatim in the passage."""
    return max(low, min(high, total // max(1, n)))


def _claim_words(claim: DetectedClaim) -> str:
    return " ".join(w for w in re.findall(r"[a-z]+", claim.text.lower())
                    if w in {"source", "high", "rich", "low", "free", "reduced", "light", "lite", "zero",
                             "contains", "provides", "increased", "more", "higher", "no", "without"})


def _claim_query(claim: DetectedClaim) -> str:
    nutrient = claim.nutrient or ""
    words = _claim_words(claim)
    base = f"{nutrient} {words}".strip() or claim.text
    return f"{base} claim conditions"


# Labelling requirements the researcher may report on, grouped into a few broad searches so a full run
# stays inside the step and tool-call limits (the verifier needs tool calls and steps of its own).
# A finding for an LBL-* id is kept only if the search that covers it ran in this run, so "no passage was
# provided" findings for requirements nobody searched for cannot appear. Order = priority when budget is short.
REQUIREMENT_GROUPS: list[dict] = [
    {"ids": ["LBL-NUTRITION"], "query": "nutritional information per 100 g declaration"},
    {"ids": ["LBL-ALLERGEN", "LBL-VEG-MARK"], "query": "allergen declaration and vegetarian non-vegetarian logo on the label"},
    {"ids": ["LBL-INGREDIENTS", "LBL-NET-QUANTITY"], "query": "list of ingredients and net quantity declaration"},
    {"ids": ["LBL-DATE-MARKING", "LBL-BATCH"], "query": "date marking best before and batch number"},
    {"ids": ["LBL-FSSAI-LICENCE", "LBL-MANUFACTURER"], "query": "FSSAI logo licence number and name and address of manufacturer"},
    {"ids": ["LBL-SMALL-PACK"], "query": "exemption small package surface area",
     "when": lambda req: req.package.total_surface_area_cm2 is not None
     and req.package.total_surface_area_cm2 <= SMALL_PACK_LOOKUP_CM2},
]


def required_topics(request: LabelCheckRequest) -> list[dict]:
    """The labelling searches that apply to this request: {"ids": [requirement ids covered], "tool", "args"}."""
    return [{"ids": list(g["ids"]), "tool": "corpus_search", "args": {"query": g["query"], "regulation": LD}}
            for g in REQUIREMENT_GROUPS if "when" not in g or g["when"](request)]


def _env_k() -> int:
    return _env_int("RESEARCHER_SWEEP_K", 5)


def suggest_actions(request: LabelCheckRequest, claims: list[DetectedClaim], attempt: int, hint: str) -> list[dict]:
    """Deterministic hints for the first steps. The model may follow, reorder or ignore them."""
    out: list[dict] = []
    if attempt > 1 and hint:
        out.append({"tool": "corpus_search", "args": {"query": _clip(hint, 200), "regulation": None}})
    for c in claims:
        out.append({"tool": "corpus_search", "args": {"query": _claim_query(c), "regulation": AC}})
    out += [{"tool": t["tool"], "args": t["args"]} for t in required_topics(request)]
    return out


# ---------------------------------------------------------------- the researcher

class LangGraphResearcher:
    def __init__(self, retriever, llm, prompts) -> None:
        self.retriever = retriever
        self.llm = llm
        self.prompts = prompts
        self.graph = self._build()

    @classmethod
    def from_registry(cls) -> LangGraphResearcher:
        from fssai_contracts.registry import build
        return cls(retriever=build("retriever"), llm=build("llm"), prompts=build("prompts"))

    # ---- public seam

    def research(self, request: LabelCheckRequest, classification: Classification, ctx: RunContext, *,
                 retry_hint: str | None = None, previous: ResearchDossier | None = None) -> ResearchDossier:
        attempt = (previous.attempt + 1) if previous else 1
        passages = {p.passage_id: p for p in previous.passages} if previous else {}
        seed_calls = [] if not previous else [f"previous attempt query: {q}" for q in previous.queries]
        state: State = {
            "ctx": ctx, "request": request, "claims": list(classification.claims), "retry_hint": retry_hint or "",
            "attempt": attempt, "passages": passages, "queries": list(previous.queries) if previous else [],
            "calls": _calls_from_queries(previous.queries) if previous else [], "history": seed_calls, "suggested": [], "notes": [], "signals": [], "iteration": 0,
            "max_iter": self._iteration_cap(ctx, attempt), "action": None, "findings": [],
        }
        out = self.graph.invoke(state, config={"recursion_limit": 10 + 4 * (state["max_iter"] + len(classification.claims))})
        return ResearchDossier(findings=out["findings"], passages=list(out["passages"].values()),
                               queries=out["queries"], escalation_signals=out["signals"], attempt=attempt)

    # ---- graph

    def _build(self):
        g = StateGraph(State)
        g.add_node("plan", self._plan)
        g.add_node("sweep", self._sweep)
        g.add_node("act", self._act)
        g.add_node("run_tool", self._run_tool)
        g.add_node("coverage", self._coverage)
        g.add_node("draft", self._draft)
        g.set_entry_point("plan")
        g.add_edge("plan", "sweep")
        g.add_edge("sweep", "act")
        g.add_conditional_edges("act", lambda s: "coverage" if s["action"] is None else "run_tool",
                                {"coverage": "coverage", "run_tool": "run_tool"})
        g.add_edge("run_tool", "act")
        g.add_edge("coverage", "draft")
        g.add_edge("draft", END)
        return g.compile()

    # ---- budget

    def _iteration_cap(self, ctx: RunContext, attempt: int) -> int:
        """How many act/tool rounds fit in what is left of the step budget (each round is two steps)."""
        reserve = self._reserve(ctx, attempt)  # verifier, router, output filter, and the attempts that could follow
        left = ctx.limits.max_steps - len(ctx.steps) - reserve - 2  # minus the draft call and a coverage search
        cap = _env_int("RESEARCHER_MAX_ITERATIONS", 5)
        if attempt > 1:
            cap = min(cap, 3)  # retries are narrower
        return max(1, min(cap, left // 2))

    # ---- nodes

    def _plan(self, state: State) -> State:
        suggested = suggest_actions(state["request"], state["claims"], state["attempt"], state["retry_hint"])
        return {"suggested": suggested}

    @staticmethod
    def _reserve(ctx: RunContext, attempt: int) -> int:
        """Steps to hold back: the tail (verifier, router, output filter; RESEARCHER_STEP_RESERVE) plus what each
        research attempt that could still follow needs (a draft call and a verification: RESEARCHER_RETRY_STEPS)."""
        later = max(0, ctx.limits.max_research_attempts - attempt)
        return _env_int("RESEARCHER_STEP_RESERVE", 5) + later * _env_int("RESEARCHER_RETRY_STEPS", 3)

    def _sweep_allowance(self, ctx: RunContext, attempt: int = 1) -> int:
        """How many sweep searches fit, always leaving room for one act round (two steps, one tool call),
        the coverage safety net, the draft call and the steps later agents need."""
        reserve = self._reserve(ctx, attempt)
        tool_reserve = _env_int("RESEARCHER_TOOL_RESERVE", 3)  # the verifier's clause_lookups count as tool calls
        tool_left = ctx.limits.max_tool_calls - ctx.tool_calls - tool_reserve
        steps_left = ctx.limits.max_steps - len(ctx.steps) - reserve - 2  # minus the draft call and a coverage search
        return max(0, min(tool_left - 1, steps_left - 2))

    def _sweep(self, state: State) -> State:
        """One search per claim condition and per applicable labelling requirement, no LLM step.
        Retrieval coverage is decided here, in code; the model only adds the follow-up searches."""
        if os.environ.get("RESEARCHER_SWEEP", "1") == "0":
            return {}
        cur = dict(state)
        update: State = {}
        todo = [{"tool": "corpus_search", "args": {"query": _claim_query(c), "regulation": AC}} for c in state["claims"]]
        todo += [{"tool": t["tool"], "args": t["args"]} for t in required_topics(state["request"])]
        budget = self._sweep_allowance(state["ctx"], state["attempt"])
        for item in todo:
            args = tools.validate(item["tool"], item["args"], state["request"])
            if _sig(item["tool"], args) in cur["calls"]:
                continue  # an earlier attempt already ran it
            if budget <= 0:
                break
            budget -= 1
            step = self._call(cur, item["tool"], args, k=_env_k())
            cur = {**cur, **step}
            update.update(step)
        # the act loop gets whatever budget the sweep left
        update["max_iter"] = self._iteration_cap(state["ctx"], state["attempt"])
        return update

    def _act(self, state: State) -> State:
        ctx = state["ctx"]
        if state["iteration"] >= state["max_iter"]:
            return {"action": None}
        prompt = self.prompts.get("researcher")
        facts = request_facts(state["request"])
        claims = "\n".join(f"- {c.text}" for c in state["claims"]) or "(no claims)"
        opened = " ".join(state["history"]).lower()
        open_refs = [r for r in cross_references(list(state["passages"].values())) if r.lower() not in opened]
        pending = [s for s in state["suggested"] if _sig(s["tool"], s["args"]) not in state["calls"]]
        messages = prompt.render(
            facts=json.dumps(facts), claims_block=data_block("claims", claims),
            strategy=STRATEGIES.get(min(state["attempt"], 3), STRATEGIES[3]),
            retry_hint=state["retry_hint"] or "(none, first attempt)",
            retrieved=_format_passages(state["passages"], _per_passage_chars(
                len(state["passages"]), _env_int("RESEARCHER_ACT_CHARS", 9000), 500, 200)),
            history="\n".join(state["history"]) or "(none)",
            open_refs=", ".join(open_refs[:8]) or "(none)",
            suggested="\n".join(f"- {s['tool']} {json.dumps(s['args'])}" for s in pending[:4]) or "(none)",
            iterations_left=state["max_iter"] - state["iteration"],
            input=claims)  # `input` keeps the registry's placeholder prompt (FakePromptStore) working
        ctx.check_budget()
        resp = self.llm.complete(messages, ctx, agent=AGENT, step="act", prompt=prompt, json_mode=True)
        data = _json(resp.text) or {}
        notes = list(state["notes"])
        if isinstance(data.get("reflection"), str) and data["reflection"].strip():
            notes.append(_clip(data["reflection"].strip(), 300))
        action = self._choose(data.get("action"), state, pending)
        return {"action": action, "notes": notes, "iteration": state["iteration"] + 1}

    def _choose(self, raw: Any, state: State, pending: list[dict]) -> dict | None:
        """The model's action if it is valid and new; else the next suggestion; else finish (None)."""
        if isinstance(raw, dict):
            tool = str(raw.get("tool", ""))
            if tool == "finish":
                return None
            try:
                args = tools.validate(tool, raw.get("args", {}), state["request"])
            except tools.ToolArgError:
                args = None
            if args is not None and _sig(tool, args) not in state["calls"]:
                return {"tool": tool, "args": args}
        # invalid, repeated or unparseable: fall back to a suggestion the run has not tried
        for s in pending:
            try:
                args = tools.validate(s["tool"], s["args"], state["request"])
            except tools.ToolArgError:
                continue
            if _sig(s["tool"], args) not in state["calls"]:
                return {"tool": s["tool"], "args": args}
        return None

    def _run_tool(self, state: State) -> State:
        return self._call(state, state["action"]["tool"], state["action"]["args"])

    def _call(self, state: State, tool: str, args: dict, k: int | None = None) -> State:
        ctx = state["ctx"]
        result = tools.execute(tool, args, retriever=self.retriever, request=state["request"], ctx=ctx, k=k)
        passages = dict(state["passages"])
        new = [p for p in result.passages if p.passage_id not in passages]
        for p in result.passages:
            passages.setdefault(p.passage_id, p)
        queries = list(state["queries"])
        if tool == "corpus_search":
            queries.append(args["query"] + (f" [{args['regulation']}]" if args.get("regulation") else ""))
        elif tool == "clause_lookup":
            queries.append(f"clause_lookup {args['clause_id']} [{args['regulation']}]")
        line = result.summary() + (f" ({len(new)} new)" if new else "")
        return {"passages": passages, "queries": queries, "calls": [*state["calls"], _sig(tool, args)],
                "history": [*state["history"], line]}

    def _coverage(self, state: State) -> State:
        """Every detected claim needs a search that reached the Claims regulation for its condition."""
        update: State = {}
        cur = dict(state)
        for claim in state["claims"]:
            if self._claim_covered(claim, cur["passages"]):
                continue
            args = {"query": _claim_query(claim), "regulation": AC}
            if _sig("corpus_search", args) in cur["calls"]:
                continue
            step = self._call(cur, "corpus_search", args)
            cur = {**cur, **step}
            update.update(step)
        return update

    @staticmethod
    def _claim_covered(claim: DetectedClaim, passages: dict[str, Passage]) -> bool:
        ac = [p for p in passages.values() if p.regulation == Regulation.CLAIMS_2018]
        if claim.nutrient:
            return any(claim.nutrient.lower() in p.text.lower() for p in ac)
        return bool(ac)

    def _draft(self, state: State) -> State:
        ctx = state["ctx"]
        passages = state["passages"]
        signals = list(state["signals"])
        findings: list[Finding] = []
        if not passages:
            signals.append("no provisions were retrieved; no finding can be grounded")
            return {"findings": [], "signals": signals}
        prompt = self.prompts.get("researcher_draft")
        claims = "\n".join(f"- {c.text}" for c in state["claims"]) or "(no claims)"
        researched, skipped = self._researched_topics(state)
        messages = prompt.render(
            facts=json.dumps(request_facts(state["request"])), claims_block=data_block("claims", claims),
            retry_hint=state["retry_hint"] or "(none, first attempt)",
            retrieved=_format_passages(passages, _per_passage_chars(
                len(passages), _env_int("RESEARCHER_DRAFT_CHARS", 18000), 2000, 450)),
            researched=", ".join(researched) or "(none)",
            not_researched=", ".join(skipped) or "(none)",
            input=claims)
        ctx.check_budget()
        resp = self.llm.complete(messages, ctx, agent=AGENT, step="draft", prompt=prompt, json_mode=True)
        data = _json(resp.text)
        if not data or not isinstance(data.get("findings"), list):
            signals.append("findings could not be drafted from the retrieved passages")
            return {"findings": [], "signals": signals}
        findings, notes = self._ground(data["findings"], passages)
        findings, scope_signals, scope_log = self._only_researched(findings, researched, skipped, bool(state["claims"]))
        for line in [*scope_log, *getattr(self, "_last_log", [])]:
            ctx.event("researcher_note", detail=line)
        signals += [str(s)[:300] for s in data.get("escalation_signals", []) if isinstance(s, (str, int))]
        signals += notes + scope_signals
        for claim in state["claims"]:
            if not self._claim_covered(claim, passages):
                signals.append(f"no condition found in the corpus for claim '{claim.text}'")
        findings, rda_notes = self._reference_guard(findings, passages)
        signals += rda_notes
        return {"findings": findings, "signals": list(dict.fromkeys(signals))}

    # ---- which requirements this run actually searched for

    @staticmethod
    def _researched_topics(state: State) -> tuple[list[str], list[str]]:
        """(requirement ids searched, requirement ids not searched) for this request, by the calls the run made."""
        done = set(state["calls"])
        researched, skipped = [], []
        for t in required_topics(state["request"]):
            sig = _sig(t["tool"], tools.validate(t["tool"], t["args"], state["request"]))
            (researched if sig in done else skipped).extend(t["ids"])
        return researched, skipped

    @staticmethod
    def _only_researched(findings: list[Finding], researched: list[str], skipped: list[str],
                         has_claims: bool) -> tuple[list[Finding], list[str], list[str]]:
        """Keep a finding only for a requirement the run searched for: an LBL-* id that a search covered, a
        CLM-* id when the label has claims, or any finding that cites a passage retrieved in this run (for
        example one the model found with its own follow-up search). Returns (kept, signals, log). Only gaps that stop a label being
        cleared are escalation signals (a requirement never searched, or searched but never written up);
        a dropped invented finding is only logged, because the router sends every signal to review."""
        kept, signals, log = [], [], []
        for f in findings:
            grounded = bool(f.citations)  # a verbatim quote from a passage this run retrieved: it was searched for
            if f.requirement_id in researched or (has_claims and f.requirement_id.startswith("CLM-")) or grounded:
                kept.append(f)
            else:
                log.append(f"{f.requirement_id}: dropped, no search was run for this requirement")
        for rid in skipped:
            signals.append(f"{rid}: not researched in this run (step or tool budget); a person must check it")
        covered = {f.requirement_id for f in kept}
        for rid in researched:
            if rid not in covered:
                signals.append(f"{rid}: searched, but no finding was drafted for it; a person must check it")
        return kept, signals, log

    # ---- grounding the draft

    def _ground(self, raw_findings: list, passages: dict[str, Passage]) -> tuple[list[Finding], list[str]]:
        findings: list[Finding] = []
        notes: list[str] = []
        log: list[str] = []
        seen: set[str] = set()
        for item in raw_findings:
            if not isinstance(item, dict):
                continue
            rid = re.sub(r"[^A-Z0-9]+", "-", str(item.get("requirement_id", "")).upper()).strip("-")
            if not rid or rid in seen:
                continue
            seen.add(rid)
            try:
                status = FindingStatus(str(item.get("status", "")).strip().lower())
            except ValueError:
                status = FindingStatus.CANNOT_DETERMINE
            citations, dropped = ground_citations(item.get("citations", []), passages)
            explanation = str(item.get("explanation", ""))[:600]
            if status in (FindingStatus.MET, FindingStatus.UNMET) and not citations:
                status = FindingStatus.CANNOT_DETERMINE
                notes.append(f"{rid}: no verbatim citation survived grounding, so it cannot be determined")
                explanation = (explanation + " (No supporting passage could be cited.)").strip()
            elif dropped:  # the finding still has a verbatim citation; the verifier judges it, no escalation
                log.append(f"{rid}: dropped {len(dropped)} citation(s) that did not resolve")
            findings.append(Finding(requirement_id=rid, requirement=str(item.get("requirement", rid))[:300] or rid,
                                    status=status, explanation=explanation, citations=citations))
        self._last_log = log
        return findings, notes

    def _reference_guard(self, findings: list[Finding], passages: dict[str, Passage]) -> tuple[list[Finding], list[str]]:
        """A condition stated as a share of a reference intake cannot be compared without the reference
        value, and neither regulation supplies it (open question in docs/eval1/section-4.1-passages.md).
        Until the team adds a cited external reference, such a finding is cannot_determine.
        Turn off with RESEARCHER_RDA_GUARD=0."""
        if os.environ.get("RESEARCHER_RDA_GUARD", "1") == "0":
            return findings, []
        pattern = re.compile(r"%\s*of\s*(?:the\s*)?RDA", re.IGNORECASE)
        out, notes = [], []
        for f in findings:
            needs_rda = f.status in (FindingStatus.MET, FindingStatus.UNMET) and any(
                pattern.search(passages[c.passage_id].text) for c in f.citations if c.passage_id in passages)
            if needs_rda:
                out.append(f.model_copy(update={
                    "status": FindingStatus.CANNOT_DETERMINE,
                    "explanation": (f.explanation + " The condition is a share of the RDA, and the RDA value is not "
                                    "in the retrieved text; a person must supply the reference value.").strip()}))
                notes.append(f"{f.requirement_id}: condition is a % of RDA and the RDA value is not in the corpus")
            else:
                out.append(f)
        return out, notes
