"""LLMClassifier: product category and claims (docs/contexts/Namith.md M1.2).

- in_scope is False for any category outside CORPUS_CATEGORIES (F7: escalate, never guess);
- every printed claim becomes a DetectedClaim with claim_type and nutrient;
- label text is untrusted: it only appears inside <label_data> blocks of the user message;
- the LLM answers in JSON; on bad JSON we retry once with a repair message, then fall back to rules.

Switch on: IMPL_CLASSIFIER=fssai_agents.classifier:LLMClassifier
"""
from __future__ import annotations

import json
import os
import re

from pydantic import BaseModel, ValidationError

from fssai_contracts.context import RunContext
from fssai_contracts.interfaces import ProviderUnavailable
from fssai_contracts.schemas import Classification, DetectedClaim, LabelCheckRequest, LLMMessage

AGENT = "classifier"

# ---------------------------------------------------------------- rule-based detector (fallback)

_NUTRIENTS = {
    "protein": "protein", "fibre": "fibre", "fiber": "fibre", "sugar": "sugar", "sugars": "sugar",
    "fat": "fat", "fats": "fat", "sodium": "sodium", "salt": "sodium", "calorie": "energy",
    "calories": "energy", "energy": "energy", "cholesterol": "cholesterol", "vitamin": "vitamin",
    "vitamins": "vitamin", "calcium": "mineral", "iron": "mineral", "zinc": "mineral",
}
_NUTRIENT_RE = "|".join(sorted(_NUTRIENTS, key=len, reverse=True))
_NUTRIENT_CLAIM = re.compile(
    rf"\b(?:(?:good |rich |excellent )?source of|high in|high|rich in|low in|low|reduced|less|no added|"
    rf"zero|free from|free|light|lite|fortified with|with added)\s+(?:in\s+|of\s+)?(?:\w+\s+){{0,2}}?(?:{_NUTRIENT_RE})\b"
    rf"|\b(?:{_NUTRIENT_RE})\s+free\b|\bsugar[- ]free\b|\bfat[- ]free\b|\bno added sugar\b",
    re.IGNORECASE)
_HEALTH_CLAIM = re.compile(
    r"\b(?:boosts?|builds?|improves?|supports?|strengthens?|promotes?|helps?|aids?|good for|"
    r"reduces? (?:the )?risk|lowers? cholesterol|heart[- ]healthy|immunity|digestion|weight loss|"
    r"diabetic[- ]friendly|clinically proven)\b[^.\n!;]{0,60}",
    re.IGNORECASE)
_OTHER_CLAIM = re.compile(r"\b(?:100% natural|all natural|natural|organic|no preservatives?|"
                          r"no artificial [a-z ]+|gluten[- ]free|vegan|non[- ]gmo|trans[- ]fat free)\b", re.IGNORECASE)


def _nutrient_in(text: str) -> str | None:
    for word in re.findall(r"[a-z]+", text.lower()):
        if word in _NUTRIENTS:
            return _NUTRIENTS[word]
    return None


def _classify_claim(text: str) -> DetectedClaim:
    nutrient = _nutrient_in(text)
    if _NUTRIENT_CLAIM.search(text):
        return DetectedClaim(text=text, claim_type="nutrient_content", nutrient=nutrient)
    if _HEALTH_CLAIM.search(text):
        return DetectedClaim(text=text, claim_type="health", nutrient=nutrient)
    return DetectedClaim(text=text, claim_type="other", nutrient=nutrient)


def detect_claims_by_rules(request: LabelCheckRequest) -> list[DetectedClaim]:
    """Declared claims always count (as printed); marketing copy is scanned for more."""
    found: list[DetectedClaim] = [_classify_claim(c) for c in request.label.claims if c.strip()]
    seen = {_norm(c.text) for c in found}
    scan = " . ".join(t for t in (request.label.front_of_pack_text, request.label.other_text or "") if t)
    for pattern, kind in ((_NUTRIENT_CLAIM, "nutrient_content"), (_HEALTH_CLAIM, "health"), (_OTHER_CLAIM, "other")):
        for m in pattern.finditer(scan):
            text = m.group(0).strip(" ,.-")
            if _norm(text) in seen or any(_norm(text) in s for s in seen):
                continue
            seen.add(_norm(text))
            found.append(DetectedClaim(text=text, claim_type=kind, nutrient=_nutrient_in(text)))
    return found


# ---------------------------------------------------------------- helpers

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _allowed_categories() -> set[str]:
    raw = os.environ.get("CORPUS_CATEGORIES", "demo-category")
    return {_slug(c) for c in raw.split(",") if c.strip()}


def _label_text(request: LabelCheckRequest) -> str:
    label = request.label
    parts = [label.product_name, label.brand_name or "", label.front_of_pack_text, " ".join(label.claims),
             label.ingredients, label.allergen_statement or "", label.other_text or ""]
    return _norm(" ".join(parts))


def _label_block(request: LabelCheckRequest) -> str:
    """All label text goes in delimited data blocks; a forged closing tag cannot escape the block."""
    label = request.label
    fields = {
        "product_name": label.product_name, "brand_name": label.brand_name or "",
        "front_of_pack_text": label.front_of_pack_text,
        "claims": "\n".join(f"- {c}" for c in label.claims),
        "ingredients": label.ingredients, "other_text": label.other_text or "",
    }
    blocks = []
    for name, value in fields.items():
        safe = re.sub(r"</?\s*label_data[^>]*>", "[removed tag]", value, flags=re.IGNORECASE)
        blocks.append(f'<label_data field="{name}">\n{safe}\n</label_data>')
    return "\n".join(blocks)


class _LLMClaim(BaseModel):
    text: str
    claim_type: str = "other"
    nutrient: str | None = None


class _LLMAnswer(BaseModel):
    category: str | None = None
    claims: list[_LLMClaim] = []
    rationale: str = ""


def _parse(text: str) -> _LLMAnswer:
    text = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    return _LLMAnswer.model_validate(json.loads(fenced.group(1) if fenced else text))


# ---------------------------------------------------------------- classifier

class LLMClassifier:
    def __init__(self, llm, prompts) -> None:
        self.llm = llm
        self.prompts = prompts

    @classmethod
    def from_registry(cls) -> LLMClassifier:
        from fssai_contracts.registry import build
        return cls(llm=build("llm"), prompts=build("prompts"))

    def classify(self, request: LabelCheckRequest, ctx: RunContext) -> Classification:
        method, answer, degraded = "llm", None, False
        try:
            answer = self._ask_llm(request, ctx)
        except ProviderUnavailable:
            degraded = True
        if answer is None:
            method = "rules"
        result = self._build(request, answer, method, degraded)
        ctx.record(agent=AGENT, kind="classification", name="classify",
                   input={"declared_category": request.declared_category, "claims_on_label": len(request.label.claims)},
                   output={**result.model_dump(), "method": method})
        return result

    # ---- LLM path

    def _ask_llm(self, request: LabelCheckRequest, ctx: RunContext) -> _LLMAnswer | None:
        prompt = self.prompts.get("classifier")
        block = _label_block(request)
        messages = prompt.render(
            declared_category=request.declared_category,
            allowed_categories=", ".join(sorted(_allowed_categories())),
            label_block=block,
            input=block)  # `input` keeps the registry's placeholder prompt (FakePromptStore) working
        ctx.check_budget()
        resp = self.llm.complete(messages, ctx, agent=AGENT, step="classify", prompt=prompt, json_mode=True)
        try:
            return _parse(resp.text)
        except (ValueError, ValidationError):
            pass
        # one repair attempt, then give up on the LLM and let the rules answer
        repair = [*messages, LLMMessage(role="assistant", content=resp.text[:2000]),
                  LLMMessage(role="user", content="That was not valid JSON in the required shape. "
                             "Reply with only the JSON object described in the instructions.")]
        ctx.check_budget()
        resp = self.llm.complete(repair, ctx, agent=AGENT, step="classify_repair", prompt=prompt, json_mode=True)
        try:
            return _parse(resp.text)
        except (ValueError, ValidationError):
            return None

    # ---- combine

    def _build(self, request: LabelCheckRequest, answer: _LLMAnswer | None, method: str, degraded: bool) -> Classification:
        allowed = _allowed_categories()
        declared = _slug(request.declared_category)
        notes = []
        in_scope = declared in allowed
        if not in_scope:
            notes.append(f"declared category '{request.declared_category}' is outside the corpus")
        if answer and answer.category:
            llm_cat = _slug(answer.category)
            if llm_cat != declared and llm_cat not in allowed and in_scope:
                in_scope = False
                notes.append(f"label text reads as '{answer.category}', not the declared category (needs a human)")
        claims = detect_claims_by_rules(request)
        if answer:
            text = _label_text(request)
            have = {_norm(c.text) for c in claims}
            for c in answer.claims:
                key = _norm(c.text)
                if not key or key in have or key not in text:  # drop claims the label never printed
                    continue
                have.add(key)
                claims.append(DetectedClaim(text=c.text.strip(), claim_type=c.claim_type or "other",
                                            nutrient=(c.nutrient or None) if c.nutrient != "null" else None))
            # prefer the LLM's richer typing for claims both found
            typed = {_norm(c.text): c for c in answer.claims}
            claims = [DetectedClaim(text=c.text, claim_type=typed[_norm(c.text)].claim_type or c.claim_type,
                                    nutrient=(typed[_norm(c.text)].nutrient if typed[_norm(c.text)].nutrient not in (None, "null") else c.nutrient))
                      if _norm(c.text) in typed else c for c in claims]
        if method == "rules":
            notes.append("rule-based fallback" + (" (provider unavailable)" if degraded else " (LLM output unusable)"))
        rationale = "; ".join(notes) or (answer.rationale if answer else "") or "category and claims confirmed"
        return Classification(category=request.declared_category, in_scope=in_scope, claims=claims, rationale=rationale)
