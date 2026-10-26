"""The verifier's deterministic checks, one function each so they are testable without an LLM (V2.1).

- resolve_citation: is the quote verbatim text of a passage retrieved in this run? (A3; this alone can fail a finding)
- read_condition / numeric_check: re-read a claim's numeric condition from the *cited passage* and compare it with
  the request's own declared value, independently of the researcher.

Nothing here knows a regulation threshold. Every number comes from the cited passage text at run time; the only
tables below are English words (claim words, nutrient names) and the request field each nutrient is declared in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from fssai_contracts.schemas import Citation, Finding, FindingStatus, LabelCheckRequest, Passage, Regulation

# ---------------------------------------------------------------- 1. citations resolve

_FOLD = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
                       " ": " "})


def normalise(text: str) -> str:
    """Fold curly quotes and dashes, collapse whitespace. Case is kept: a quote must be the passage's words."""
    return re.sub(r"\s+", " ", text.translate(_FOLD)).strip()


@dataclass
class CitationResult:
    passage_id: str
    resolved: bool
    problem: str = ""          # "", "empty_quote", "not_retrieved", "not_verbatim"


def resolve_citation(citation: Citation, passages: dict[str, Passage]) -> CitationResult:
    """The resolve_citation tool. Supported only if the passage was retrieved in this run and the quote is a
    substring of its text after whitespace/quote normalisation. Paraphrases never resolve."""
    if not citation.quote.strip():
        return CitationResult(citation.passage_id, False, "empty_quote")
    passage = passages.get(citation.passage_id)
    if passage is None:
        return CitationResult(citation.passage_id, False, "not_retrieved")
    if citation.quote in passage.text or normalise(citation.quote) in normalise(passage.text):
        return CitationResult(citation.passage_id, True)
    return CitationResult(citation.passage_id, False, "not_verbatim")


# ---------------------------------------------------------------- 2. numbers: re-read the condition

# Claim words -> the kind of condition they take. Only words whose meaning Schedule I states itself
# ("Rich / High", "High Or Rich") or that are the Schedule I column headings; anything else is not checked here.
CLAIM_KINDS = {"source": "source", "provides": "source", "contains": "source",
               "high": "high", "rich": "high", "low": "low", "free": "free", "zero": "free", "without": "free"}
_MINIMUM_KINDS = {"source", "high"}

# Nutrient words -> (request field, unit the field is declared in). `other.<key>` reads NutritionPanel.other.
NUTRIENTS: list[tuple[tuple[str, ...], str, str]] = [
    (("saturated fat", "saturated fatty"), "saturated_fat_g", "g"),
    (("trans fat", "trans-fat"), "trans_fat_g", "g"),
    (("dietary fibre", "dietary fiber", "fibre", "fiber"), "other.dietary_fibre_g", "g"),
    (("protein",), "protein_g", "g"),
    (("sugar",), "total_sugars_g", "g"),
    (("sodium", "salt"), "sodium_mg", "mg"),
    (("cholesterol",), "other.cholesterol_mg", "mg"),
    (("energy", "calorie", "kcal"), "energy_kcal", "kcal"),
    (("fat",), "total_fat_g", "g"),
]

_TO_G = {"g": 1.0, "mg": 0.001}
_BASIS = re.compile(r"(?:per|or)\s*100\s*(g|ml|kcal)\b", re.I)
_QUANTITY = re.compile(r"(\d+(?:\.\d+)?)\s*(%|mg|g|kcal)(?![a-z])", re.I)
_HEADWORDS = re.compile(r"\b(source|rich\s*/\s*high|high\s+or\s+rich|high|rich|very low|low|free)\b", re.I)


@dataclass
class Condition:
    kind: str                                  # source | high | low | free
    thresholds: dict[str, tuple[float, str]]   # basis ("100 g", "100 ml", "100 kcal") -> (value, unit)
    relative: bool = False                     # "% of RDA": needs a reference value that is not in the text
    strict: bool = False                       # "less than" rather than "not more than" / "at least"
    text: str = ""


@dataclass
class NumericResult:
    applicable: bool
    outcome: str = ""            # "" | "consistent" | "mismatch" | "needs_reference" | "borderline" | "bases_disagree" | "missing_value"
    expected: FindingStatus | None = None
    detail: str = ""
    evidence: dict = field(default_factory=dict)


def claim_kind(text: str) -> str | None:
    low = text.lower()
    if re.search(r"\badded\b", low):
        return None  # non-addition claims ("no added sugar") are FSS-AC-2018 6(1) conditions, not Schedule I numbers
    if re.search(r"\bvery\s+low\b", low):
        return "very low"
    for word in re.findall(r"[a-z]+", low):
        if word in CLAIM_KINDS:
            return CLAIM_KINDS[word]
    return None


def nutrient_of(text: str) -> tuple[str, str, str] | None:
    """(nutrient word, request field, unit) for the first nutrient named in text; specific names win over 'fat'."""
    low = text.lower()
    for words, fld, unit in NUTRIENTS:
        for w in words:
            if re.search(rf"\b{re.escape(w)}", low):
                return w, fld, unit
    return None


def declared_value(request: LabelCheckRequest, fld: str) -> float | None:
    n = request.nutrition
    if fld.startswith("other."):
        return n.other.get(fld.split(".", 1)[1])
    return getattr(n, fld, None)


def _segment(text: str, kind: str) -> str | None:
    """The part of a Schedule-I-style row that belongs to one claim word: from that headword to the next."""
    heads = list(_HEADWORDS.finditer(text))
    for i, m in enumerate(heads):
        word = re.sub(r"\s+", " ", m.group(1).lower())
        if "rich" in word or word == "high":
            k = "high"
        elif word == "very low":
            k = "very low"
        else:
            k = word
        if k == kind:
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            return text[m.end():end]
    return None


def read_condition(passage_text: str, kind: str) -> Condition | None:
    """Parse the condition for one claim kind out of the passage text. None if the passage states none."""
    seg = _segment(passage_text, kind)
    if seg is None:
        return None
    relative = bool(re.search(r"%\s*of\s*(?:the\s*)?RDA", seg, re.I))
    strict = bool(re.search(r"\bless than\b", seg, re.I))
    # Mask "per 100 g" / "or 100 ml" so the 100 is not read as a quantity, then give each quantity the bases
    # named between it and the next quantity ("0.5 g of fat per 100 g for solids or 100 ml for liquids").
    bases = [(m.start(), m.group(1).lower()) for m in _BASIS.finditer(seg)]
    masked = _BASIS.sub(lambda m: " " * len(m.group(0)), seg)
    quantities = [(m.start(), float(m.group(1)), m.group(2).lower()) for m in _QUANTITY.finditer(masked)]
    thresholds: dict[str, tuple[float, str]] = {}
    for i, (pos, value, unit) in enumerate(quantities):
        nxt = quantities[i + 1][0] if i + 1 < len(quantities) else len(seg)
        for bpos, basis in bases:
            if pos < bpos < nxt:
                thresholds.setdefault(f"100 {basis}", (value, unit))
    if not thresholds and not relative:
        return None
    return Condition(kind=kind, thresholds=thresholds, relative=relative, strict=strict, text=seg.strip())


def _met(declared: float, threshold: float, kind: str, strict: bool) -> bool:
    if kind in _MINIMUM_KINDS:
        return declared >= threshold
    return declared < threshold if strict else declared <= threshold


def numeric_check(finding: Finding, claim_text: str, request: LabelCheckRequest, cited: list[Passage],
                  tolerance_pct: float) -> NumericResult:
    """Re-derive a claim finding's status from the cited condition and the declared value.

    Applies only to met/unmet findings about a nutrient claim whose cited passage states a condition for that
    claim word. `tolerance_pct` is the tolerance FSS-LD-2020 5(3)(d) allows on a *declared* value ("± 20 percent
    of the value for that nutrient declared on the label"): when declared x (1 ± tolerance) spans the threshold,
    the product may sit on either side of the line, so we escalate instead of deciding. 0 turns this off."""
    if finding.status not in (FindingStatus.MET, FindingStatus.UNMET):
        return NumericResult(False)
    kind = claim_kind(claim_text)
    nutrient = nutrient_of(claim_text)
    if kind is None or nutrient is None:
        return NumericResult(False)
    # Claim conditions are in the Claims regulation; a labelling passage that happens to read "free ... per 100 g"
    # is not one.
    condition = next((c for p in cited if p.regulation == Regulation.CLAIMS_2018
                      and (c := read_condition(p.text, kind))), None)
    if condition is None:
        return NumericResult(False)
    word, fld, unit = nutrient
    evidence = {"claim": claim_text, "kind": kind, "field": fld, "condition": condition.text[:300]}
    if condition.relative and not condition.thresholds:
        return NumericResult(True, "needs_reference", None,
                             f"the condition for '{claim_text}' is a share of the RDA, and the RDA value is not in "
                             "the cited text; a person must supply the reference value", evidence)
    value = declared_value(request, fld)
    if value is None:
        return NumericResult(True, "missing_value", None, f"'{claim_text}' is claimed but {fld} is not declared",
                             evidence)

    panel = "100 g" if request.nutrition.basis == "per_100g" else "100 ml"
    outcomes: dict[str, bool] = {}
    spans: list[bool] = []
    tol = max(tolerance_pct, 0.0) / 100.0
    for basis, (threshold, t_unit) in condition.thresholds.items():
        if unit == t_unit:
            declared = value
        elif unit in _TO_G and t_unit in _TO_G:          # g <-> mg
            declared = value * _TO_G[unit] / _TO_G[t_unit]
        else:                                             # "%" of a reference, or kcal against a mass
            continue
        if basis == "100 kcal" and unit != "kcal" and request.nutrition.energy_kcal > 0:
            declared = declared * 100.0 / request.nutrition.energy_kcal   # the panel's per-100 value -> per 100 kcal
        elif basis != panel:
            continue
        outcomes[basis] = _met(declared, threshold, kind, condition.strict)
        spans.append(tol > 0 and declared * (1 - tol) <= threshold <= declared * (1 + tol))
        evidence.setdefault("comparisons", []).append(
            {"basis": basis, "declared": round(declared, 4), "threshold": threshold, "unit": t_unit,
             "met": outcomes[basis]})
    if not outcomes:
        if condition.relative:
            return NumericResult(True, "needs_reference", None,
                                 f"the condition for '{claim_text}' on this basis is a share of the RDA, which is not "
                                 "in the cited text", evidence)
        return NumericResult(False)
    if len(set(outcomes.values())) > 1:
        per_basis = ", ".join(f"per {b}: " + ("met" if ok else "not met") for b, ok in outcomes.items())
        return NumericResult(True, "bases_disagree", None,
                             f"'{claim_text}' meets the condition on one basis and not another ({per_basis}); "
                             "which basis governs is for a person to decide", evidence)
    expected = FindingStatus.MET if next(iter(outcomes.values())) else FindingStatus.UNMET
    if any(spans):
        return NumericResult(True, "borderline", expected,
                             f"the declared {word} ± {tolerance_pct:g}% (the tolerance on declared values, FSS-LD-2020 "
                             f"5(3)(d)) spans the condition for '{claim_text}'; a person must decide", evidence)
    if expected != finding.status:
        return NumericResult(True, "mismatch", expected,
                             f"the cited condition and the declared value give '{expected.value}', but the finding "
                             f"says '{finding.status.value}'", evidence)
    return NumericResult(True, "consistent", expected, "", evidence)


def claim_for(finding: Finding, claims: list[str]) -> str | None:
    """Which printed claim a finding is about: a claim quoted in it, else one sharing its nutrient word."""
    hay = f"{finding.requirement_id} {finding.requirement} {finding.explanation}".lower()
    for c in claims:
        if c.lower() in hay:
            return c
    nutrient = nutrient_of(f"{finding.requirement_id.replace('-', ' ')} {finding.requirement}")
    if nutrient:
        for c in claims:
            if nutrient_of(c) and nutrient_of(c)[1] == nutrient[1]:
                return c
    return None
