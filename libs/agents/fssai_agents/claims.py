"""Rule-based claim detection: the classifier's fallback and its safety net (M1.2, F3).

It reads only label text (never regulations), so it holds no FSSAI rule content: it recognises that a
phrase is *shaped like* a claim ("source of X", "high in X", "no added sugar", "boosts immunity") and which
nutrient the claim is about. Which condition the claim must meet is the researcher's job, from retrieved text.
"""
from __future__ import annotations

import re

from fssai_contracts.schemas import DetectedClaim

# nutrient slug -> words that name it on a label
NUTRIENTS: dict[str, tuple[str, ...]] = {
    "protein": ("protein", "proteins"),
    "fibre": ("fibre", "fiber", "dietary fibre", "dietary fiber"),
    "sugar": ("sugar", "sugars", "added sugar", "added sugars"),
    "saturated_fat": ("saturated fat", "saturated fats"),
    "trans_fat": ("trans fat", "trans fats", "trans-fat"),
    "cholesterol": ("cholesterol",),
    "fat": ("fat", "fats"),
    "sodium": ("sodium", "salt"),
    "energy": ("energy", "calorie", "calories", "kcal"),
    "vitamin": ("vitamin", "vitamins", "vitamin c", "vitamin d", "vitamin b12", "folate", "folic acid"),
    "mineral": ("iron", "calcium", "zinc", "magnesium", "potassium", "iodine", "minerals"),
}

_LEVEL = (r"source of|good source of|excellent source of|rich in|high in|high|higher in|low in|low|very low in|"
          r"free from|free of|free|reduced|less|lite|light|more|increased|enriched with|fortified with|"
          r"contains|provides|no|zero|without|negligible|added|packed with|loaded with")
_SPLIT = re.compile(r"[.;!\n|•*]+|\s[-–—]\s|,(?=\s*[A-Za-z])")

HEALTH_PHRASES = (
    r"boosts? (?:your )?immunity", r"builds? immunity", r"immunity", r"good for (?:your )?(?:heart|bones|skin|digestion)",
    r"heart[- ]healthy", r"supports? (?:heart|digestion|immunity|gut|bone|brain|weight)", r"improves? (?:digestion|memory|health)",
    r"helps? (?:lower|reduce|control|manage|prevent|fight|burn)", r"(?:lowers?|reduces?) (?:cholesterol|blood sugar|blood pressure|weight)",
    r"prevents? ", r"cures? ", r"treats? ", r"clinically (?:proven|tested)", r"diabetic[- ]friendly", r"weight (?:loss|management)",
    r"detox", r"energy booster", r"boosts? energy", r"promotes? (?:health|growth|digestion|heart)",
)
_HEALTH = re.compile("|".join(HEALTH_PHRASES), re.I)
_NON_ADDITION = re.compile(r"\b(?:no|without|zero|free from|free of|not added|nothing)\b[^.]{0,20}\b(?:added|preservatives?|colou?rs?|"
                           r"flavou?rs?|sugar|maida|artificial)\b", re.I)
_COMPARATIVE = re.compile(r"\b(?:reduced|less|lite|light|more|higher|lower|increased|fewer|enhanced)\b", re.I)


def nutrient_in(text: str) -> str | None:
    """The nutrient a phrase is about, preferring the longest matching word ("saturated fat" over "fat")."""
    lowered = text.lower()
    best: tuple[int, str] | None = None
    for slug, words in NUTRIENTS.items():
        for w in words:
            if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", lowered) and (best is None or len(w) > best[0]):
                best = (len(w), slug)
    return best[1] if best else None


def classify_claim(text: str) -> DetectedClaim:
    """Type and nutrient of one claim phrase that is already known to be a claim."""
    nutrient = nutrient_in(text)
    if _HEALTH.search(text):
        claim_type = "health"
    elif _NON_ADDITION.search(text) and not (nutrient and re.search(r"\b(?:no|zero|free)\b", text, re.I) and nutrient != "sugar"):
        claim_type = "non_addition" if re.search(r"added|preservative|colou?r|flavou?r|artificial|maida", text, re.I) else "nutrient_content"
    elif nutrient and _COMPARATIVE.search(text) and not re.search(r"\b(?:source of|rich in|high in)\b", text, re.I):
        claim_type = "nutrient_comparative"
    elif nutrient:
        claim_type = "nutrient_content"
    else:
        claim_type = "other"
    return DetectedClaim(text=text.strip(), claim_type=claim_type, nutrient=nutrient)


def looks_like_claim(phrase: str) -> bool:
    if _HEALTH.search(phrase):
        return True
    nutrient = nutrient_in(phrase)
    if nutrient and re.search(rf"\b(?:{_LEVEL})\b", phrase, re.I):
        return True
    return bool(_NON_ADDITION.search(phrase))


def detect_in_text(text: str) -> list[DetectedClaim]:
    """Claims hidden in free text (front-of-pack copy, other text): the phrases that are shaped like one."""
    found: list[DetectedClaim] = []
    for raw in _SPLIT.split(text or ""):
        phrase = " ".join(raw.split())
        if 3 <= len(phrase) <= 160 and looks_like_claim(phrase):
            found.append(classify_claim(phrase))
    return found


def detect_all(printed_claims: list[str], *free_text: str) -> list[DetectedClaim]:
    """Every printed claim (always), plus claims found in free text, de-duplicated by wording."""
    out: list[DetectedClaim] = []
    seen: set[str] = set()

    def add(c: DetectedClaim) -> None:
        key = " ".join(c.text.lower().split())
        if key and key not in seen:
            seen.add(key)
            out.append(c)

    for text in printed_claims:
        if text.strip():
            add(classify_claim(text))
    for text in free_text:
        for c in detect_in_text(text):
            if not any(" ".join(c.text.lower().split()) in k or k in " ".join(c.text.lower().split()) for k in seen):
                add(c)
    return out
