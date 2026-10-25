"""LLMClassifier: product category and claims (contexts/Namith.md M1.2, F3).

Interface: fssai_contracts.interfaces.Classifier; checked by conformance.check_classifier.

- Category: the declared category, cross-checked against the label text by the LLM. A label that does not
  look like its declared category is out of scope (F7: escalate, never guess), as is any category outside
  CORPUS_CATEGORIES.
- Claims: every printed claim, plus claims hidden in front-of-pack or other text. The LLM proposes them; the
  rule-based detector (claims.py) is both the fallback when the LLM fails and a safety net that adds what the
  LLM missed. A claim the LLM returns must be grounded in label text, so an injected "claim" is dropped.
- All label text reaches the model inside <label_data> delimiters and the prompt says it is data.

Switch on: IMPL_CLASSIFIER=fssai_agents.classifier:LLMClassifier
"""
from __future__ import annotations

import json
import os
import re

from pydantic import BaseModel, ValidationError, field_validator

from fssai_contracts.context import BudgetExceeded, RunContext
from fssai_contracts.interfaces import ProviderUnavailable
from fssai_contracts.schemas import Classification, DetectedClaim, LabelCheckRequest

from . import claims as rules

CLAIM_TYPES = {"nutrient_content", "nutrient_comparative", "health", "non_addition", "other"}
NUTRIENTS = set(rules.NUTRIENTS) | {"other"}
_CLEAN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MAX_FIELD = 2000


class _LLMClaim(BaseModel):
    text: str
    claim_type: str = "other"
    nutrient: str | None = None

    @field_validator("claim_type")
    @classmethod
    def _type(cls, v: str) -> str:
        v = (v or "other").strip().lower().replace(" ", "_")
        return v if v in CLAIM_TYPES else "other"

    @field_validator("nutrient")
    @classmethod
    def _nutrient(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = str(v).strip().lower().replace(" ", "_")
        return None if v in ("", "null", "none") else (v if v in NUTRIENTS else "other")


class _LLMOutput(BaseModel):
    category_matches_label: bool = True
    category: str = ""
    suspicious_text: bool = False
    claims: list[_LLMClaim] = []
    rationale: str = ""


def corpus_categories() -> list[str]:
    raw = os.environ.get("CORPUS_CATEGORIES", "demo-category")
    return [c.strip() for c in raw.split(",") if c.strip()]


def _data(text: str | None) -> str:
    """Label text as the model sees it: control characters out, delimiters neutralised, length bounded."""
    text = _CLEAN.sub(" ", text or "")
    text = re.sub(r"</?\s*label_data\s*>", "[delimiter removed]", text, flags=re.I)
    return text[:MAX_FIELD]


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9% ]+", " ", text.lower()).split())


def _json_object(text: str) -> dict:
    """The first JSON object in a model reply, tolerating code fences and chatter around it."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("reply is JSON but not an object")
    return value


class LLMClassifier:
    def __init__(self, llm, prompts) -> None:
        self.llm = llm
        self.prompts = prompts

    @classmethod
    def from_registry(cls) -> LLMClassifier:
        from fssai_contracts.registry import build
        return cls(llm=build("llm"), prompts=build("prompts"))

    # ------------------------------------------------------------------ public

    def classify(self, request: LabelCheckRequest, ctx: RunContext) -> Classification:
        ctx.check_budget()
        covered = corpus_categories()
        label = request.label
        free_text = [label.front_of_pack_text, label.other_text or "", label.product_name]
        fallback_claims = rules.detect_all(label.claims, *free_text)

        source = "llm"
        output: _LLMOutput | None = None
        try:
            output = self._ask(request, covered, ctx)
        except (ProviderUnavailable, BudgetExceeded):
            raise  # a run-level problem: the pipeline decides what happens (A5)
        except Exception as exc:  # noqa: BLE001 - any unusable LLM answer falls back to rules
            source = "rules"
            ctx.event("classifier_fallback", reason=f"{type(exc).__name__}: {exc}")

        claims = self._merge_claims(output, fallback_claims, request)
        category, in_scope, rationale = self._decide_category(request, output, covered)
        result = Classification(category=category, in_scope=in_scope, claims=claims, rationale=rationale)
        ctx.record(agent="classifier", kind="classification", name="classify", output={
            **result.model_dump(), "source": source,
            "suspicious_text": bool(output and output.suspicious_text)})
        return result

    # ------------------------------------------------------------------ LLM call

    def _ask(self, request: LabelCheckRequest, covered: list[str], ctx: RunContext) -> _LLMOutput:
        label = request.label
        prompt = self.prompts.get("classifier")
        messages = prompt.render(
            declared_category=_data(request.declared_category), covered_categories=", ".join(covered),
            product_name=_data(label.product_name), brand_name=_data(label.brand_name),
            claims=json.dumps([_data(c) for c in label.claims]), front_of_pack_text=_data(label.front_of_pack_text),
            ingredients=_data(label.ingredients), other_text=_data(label.other_text))
        ctx.check_budget()
        reply = self.llm.complete(messages, ctx, agent="classifier", step="classify", prompt=prompt, json_mode=True)
        try:
            return _LLMOutput.model_validate(_json_object(reply.text))
        except (ValueError, ValidationError) as exc:
            problem = f"{type(exc).__name__}: {str(exc)[:200]}"
        # One repair attempt, then the caller falls back to rules.
        repair = self.prompts.get("classifier_repair")
        ctx.check_budget()
        fixed = self.llm.complete(repair.render(problem=problem, reply=reply.text[:3000]), ctx,
                                  agent="classifier", step="classify_repair", prompt=repair, json_mode=True)
        return _LLMOutput.model_validate(_json_object(fixed.text))

    # ------------------------------------------------------------------ merging and decisions

    def _merge_claims(self, output: _LLMOutput | None, found: list[DetectedClaim],
                      request: LabelCheckRequest) -> list[DetectedClaim]:
        """Rule-found claims first (every printed claim is in there), then LLM claims grounded in label text."""
        label = request.label
        haystack = _norm(" ".join([label.product_name, label.front_of_pack_text, label.other_text or "",
                                   *label.claims]))
        merged = list(found)
        seen = [_norm(c.text) for c in merged]
        for c in (output.claims if output else []):
            n = _norm(c.text)
            if not n or n not in haystack:
                continue  # not on the label: hallucinated or injected, never a claim
            if any(n == s or n in s or s in n for s in seen):
                # The rules found it too; the LLM may know the type better, so refine the entry.
                for i, existing in enumerate(merged):
                    e = _norm(existing.text)
                    if (n == e or n in e or e in n) and existing.claim_type == "other" and c.claim_type != "other":
                        merged[i] = existing.model_copy(update={"claim_type": c.claim_type,
                                                                "nutrient": existing.nutrient or c.nutrient})
                continue
            seen.append(n)
            merged.append(DetectedClaim(text=c.text.strip(), claim_type=c.claim_type, nutrient=c.nutrient))
        return merged

    def _decide_category(self, request: LabelCheckRequest, output: _LLMOutput | None,
                         covered: list[str]) -> tuple[str, bool, str]:
        declared = request.declared_category.strip()
        declared_ok = declared in covered
        if not declared_ok:
            return declared, False, f"Declared category '{declared}' is outside the corpus ({', '.join(covered)})."
        if output is not None and not output.category_matches_label:
            actual = (output.category or "").strip().lower() or "unknown"
            return (actual if actual not in covered else declared), False, (
                f"Label text does not look like '{declared}'; it looks like '{actual}'. "
                f"{output.rationale}".strip())
        return declared, True, (output.rationale if output else "Declared category used; rule-based claim detection.")
