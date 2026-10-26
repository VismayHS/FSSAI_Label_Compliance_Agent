"""Judges behind the L3 metrics. One interface, three backends, picked with --judge or EVAL_JUDGE:

- reference  offline and deterministic (default). Uses only what can be checked without a model: verbatim citation
             resolution and, for relevance, the scenario's gold supporting clauses. Free, repeatable, CI-safe; it
             under-reports what only reading comprehension can catch, which is why the others exist.
- llm        our own judge prompts (eval/fssai_eval/prompts) through the configured LLMClient (IMPL_LLM).
- trulens    TruLens feedback functions (groundedness_measure_with_cot_reasons, context_relevance_with_cot_reasons)
             on an OpenAI-compatible provider from env (EVAL_JUDGE_BASE_URL/API_KEY/MODEL, else LLM_*).
             pip install -e "eval[trulens]".

Every model call is cached on disk (EVAL_JUDGE_CACHE_DIR, keyed by judge, prompt version and inputs), so re-scoring
a run, or comparing two runs that share passages, costs no free-tier quota.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Protocol

import yaml

from fssai_contracts.context import RunContext, RunLimits
from fssai_contracts.schemas import PromptTemplate

PROMPTS = Path(__file__).parent / "prompts"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, "").split("#", 1)[0].strip() or default


def load_prompt(name: str, version: str | None = None) -> PromptTemplate:
    folder = PROMPTS / name
    versions = sorted((p.stem for p in folder.glob("*.yaml")), key=lambda v: tuple(int(x) for x in v.split(".")))
    chosen = version or versions[-1]
    data = yaml.safe_load((folder / f"{chosen}.yaml").read_text(encoding="utf-8"))
    assert data["system"].lstrip().startswith(f"[prompt:{name}@{chosen}]"), f"{name}@{chosen}: missing tag"
    return PromptTemplate(name=name, version=chosen, system=data["system"].strip(),
                          user_template=data["user_template"].strip())


def parse_json(text: str) -> dict | None:
    text = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    try:
        data = json.loads(fenced.group(1) if fenced else text)
    except ValueError:
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)  # tolerate prose around the object
        try:
            data = json.loads(m.group(0)) if m else None
        except ValueError:
            return None
    return data if isinstance(data, dict) else None


class Judge(Protocol):
    name: str

    def support(self, statement: str, source: str) -> float | None:
        """0..1: how far `source` supports `statement` (groundedness). None = could not judge."""
        ...

    def relevance(self, question: str, passage: str, *, gold: bool | None) -> float | None:
        """0..1: how relevant `passage` is to `question` (context relevance). `gold`: the passage is (True) or is
        not (False) one of the scenario's supporting clauses; None when there is no gold (live runs)."""
        ...

    def status_follows(self, facts: dict, requirement: str, status: str, explanation: str,
                       passages: str) -> bool | None:
        """Does the finding's status follow from its passages + the facts (faithfulness)? None = could not judge."""
        ...


class Cache:
    def __init__(self, root: str | None) -> None:
        self.root = Path(root) if root else None
        self.hits = self.misses = 0

    def _path(self, key: dict) -> Path | None:
        if self.root is None:
            return None
        digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
        return self.root / digest[:2] / f"{digest}.json"

    def get(self, key: dict):
        p = self._path(key)
        if p is not None and p.exists():
            self.hits += 1
            return json.loads(p.read_text(encoding="utf-8"))["value"]
        self.misses += 1
        return None

    def put(self, key: dict, value) -> None:
        p = self._path(key)
        if p is None:
            return
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"key": key, "value": value}), encoding="utf-8")
        except OSError:
            pass  # a read-only or missing cache dir only costs a re-call


def cache_from_env() -> Cache:
    root = _env("EVAL_JUDGE_CACHE_DIR")
    if root and not Path(root).parent.exists():
        root = ""  # the Compose default /data/... does not exist on a laptop: run uncached rather than fail
    return Cache(root or None)


# ---------------------------------------------------------------- reference (offline)

class ReferenceJudge:
    """Deterministic. Support is decided by citation resolution in metrics.py (a statement whose citations resolve
    verbatim to retrieved text scores 1); relevance by the gold supporting clauses; status only where numbers decide."""
    name = "reference"

    def support(self, statement, source):
        return 1.0 if source.strip() else 0.0

    def relevance(self, question, passage, *, gold):
        return None if gold is None else (1.0 if gold else 0.0)

    def status_follows(self, facts, requirement, status, explanation, passages):
        return None


# ---------------------------------------------------------------- llm (our prompts, our LLMClient)

class LLMJudge:
    name = "llm"

    def __init__(self, llm=None, cache: Cache | None = None) -> None:
        if llm is None:
            from fssai_contracts.registry import build
            llm = build("llm")
        self.llm, self.cache = llm, cache or cache_from_env()
        self.prompts = {n: load_prompt(n) for n in ("judge_support", "judge_relevance", "judge_status")}
        self.calls = 0

    def _ask(self, prompt_name: str, **values) -> dict | None:
        prompt = self.prompts[prompt_name]
        key = {"judge": self.name, "prompt": f"{prompt.name}@{prompt.version}", **values}
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        ctx = RunContext.new(limits=RunLimits(max_steps=10, max_tool_calls=0, max_wall_s=120))
        self.calls += 1
        resp = self.llm.complete(prompt.render(**values, input=json.dumps(values)), ctx, agent="eval_judge",
                                 step=prompt_name, prompt=prompt, json_mode=True)
        data = parse_json(resp.text)
        if data is not None:
            self.cache.put(key, data)
        return data

    @staticmethod
    def _score(data: dict | None) -> float | None:
        try:
            return max(0.0, min(3.0, float(data["score"]))) / 3.0
        except (TypeError, KeyError, ValueError):
            return None

    def support(self, statement, source):
        return self._score(self._ask("judge_support", statement=statement, source=source[:6000]))

    def relevance(self, question, passage, *, gold):
        return self._score(self._ask("judge_relevance", question=question, context=passage[:3000]))

    def status_follows(self, facts, requirement, status, explanation, passages):
        data = self._ask("judge_status", facts=json.dumps(facts, sort_keys=True), requirement=requirement,
                         status=status, explanation=explanation[:600], passages=passages[:6000])
        verdict = str((data or {}).get("verdict", "")).strip().lower()
        return {"follows": True, "does_not_follow": False}.get(verdict)


# ---------------------------------------------------------------- trulens

class TruLensJudge(LLMJudge):
    """TruLens feedback functions for groundedness and context relevance (the L3 requirement); faithfulness uses our
    judge_status prompt through the same provider, because TruLens has no claim-level status check."""
    name = "trulens"

    def __init__(self, provider=None, cache: Cache | None = None, llm=None) -> None:
        if provider is None:
            from trulens.providers.openai import OpenAI as TruLensOpenAI  # pip install -e "eval[trulens]"
            base = _env("EVAL_JUDGE_BASE_URL", _env("LLM_BASE_URL"))
            model = _env("EVAL_JUDGE_MODEL", _env("LLM_MODEL"))
            key = _env("EVAL_JUDGE_API_KEY", _env("LLM_API_KEY"))
            if not (base and model):
                raise RuntimeError("--judge trulens needs EVAL_JUDGE_BASE_URL/EVAL_JUDGE_MODEL (or LLM_BASE_URL/LLM_MODEL)")
            provider = TruLensOpenAI(model_engine=model, base_url=base, api_key=key or "none")
        self.provider = provider
        super().__init__(llm=llm, cache=cache)

    def _cached(self, fn: str, **values) -> float | None:
        key = {"judge": "trulens", "fn": fn, **values}
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        self.calls += 1
        try:
            score, _reasons = getattr(self.provider, fn)(**values)
        except Exception:  # noqa: BLE001 - a judge failure leaves the item unscored, it does not stop the eval
            return None
        if score is None:
            return None
        score = max(0.0, min(1.0, float(score)))
        self.cache.put(key, score)
        return score

    def support(self, statement, source):
        return self._cached("groundedness_measure_with_cot_reasons", source=source[:6000], statement=statement)

    def relevance(self, question, passage, *, gold):
        return self._cached("context_relevance_with_cot_reasons", question=question, context=passage[:3000])


def make_judge(name: str | None = None) -> Judge:
    name = (name or _env("EVAL_JUDGE", "reference")).lower()
    if name == "reference":
        return ReferenceJudge()
    if name == "llm":
        return LLMJudge()
    if name == "trulens":
        return TruLensJudge()
    raise ValueError(f"unknown judge '{name}' (reference | llm | trulens)")
