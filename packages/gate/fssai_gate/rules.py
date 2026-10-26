"""The data contract's validation rules (docs/data-contract.md; F2, D1). Pure functions, no I/O.

    validate(raw) -> (LabelCheckRequest | None, [FieldError, ...])

Order: unknown fields and schema/type (pydantic) -> version -> ranges, lengths and formats -> category ->
cross-field rules (XF-01 ...). Every stage that can run does, so a caller gets *all* their errors at once.
Cross-field rules need typed values, so they run only when the schema stage passed.

The gate checks that a request is well formed. It never decides compliance: a label *missing* an allergen
statement or a licence number is a valid request that the agents then find unmet. Every number below is a
sanity bound on the request, justified in docs/data-contract.md, not a regulatory threshold; the two values
taken from the regulations (the energy conversion factors and the ±20 % tolerance) are quoted there.
"""
from __future__ import annotations

import math
import os
import re
from collections.abc import Callable

from pydantic import BaseModel, ValidationError

from fssai_contracts.schemas import (
    LabelCheckRequest, LabelText, NutritionPanel, PackageSpec, FieldError,
)

SUPPORTED_MAJOR = "1"
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
OTHER_KEY = re.compile(r"^[a-z][a-z0-9_]{0,47}_(g|mg|mcg|kcal)$")
LICENCE = re.compile(r"^\d{14}$")
PACK_TYPES = ("single", "multipack", "institutional", "non-retail")

# FSS-LD-2020 5(3)(e)(i): "(A) Carbohydrates 4 kcal/g ... (D) Protein 4 kcal/g (E) Fat 9 kcal/g"
ENERGY_FACTORS = {"protein_g": 4.0, "carbohydrate_g": 4.0, "total_fat_g": 9.0}
# FSS-LD-2020 5(3)(d): declared nutrients have "the tolerance of ± 20 percent of the value ... declared"
ENERGY_TOLERANCE = 0.20
ENERGY_FLOOR_KCAL = 10.0       # rounding on small declared values (see data-contract.md, XF-08)
MASS_ROUNDING_G = 1.0          # per-100 g panels are rounded per nutrient (XF-07)

# loc -> (min, max, min_exclusive). Per-100 g/ml nutrient masses cannot exceed 100 g.
RANGES: dict[str, tuple[float, float, bool]] = {
    "package.principal_display_panel_cm2": (0, 10_000, True),
    "package.total_surface_area_cm2": (0, 50_000, True),
    "nutrition.serving_size": (0, 1_000, True),
    "nutrition.energy_kcal": (0, 900, False),
    "nutrition.protein_g": (0, 100, False),
    "nutrition.carbohydrate_g": (0, 100, False),
    "nutrition.total_sugars_g": (0, 100, False),
    "nutrition.added_sugars_g": (0, 100, False),
    "nutrition.total_fat_g": (0, 100, False),
    "nutrition.saturated_fat_g": (0, 100, False),
    "nutrition.trans_fat_g": (0, 100, False),
    "nutrition.sodium_mg": (0, 40_000, False),
}
NET_QUANTITY_MAX = {"g": 100_000, "ml": 100_000, "kg": 100, "l": 100}
OTHER_MAX = {"g": 100, "mg": 100_000, "mcg": 100_000_000, "kcal": 900}

# loc -> (min chars, max chars). min 1 = required and not blank.
LENGTHS: dict[str, tuple[int, int]] = {
    "client_reference": (0, 128),
    "label.product_name": (1, 200),
    "label.brand_name": (0, 200),
    "label.front_of_pack_text": (0, 4_000),
    "label.ingredients": (0, 4_000),
    "label.allergen_statement": (0, 1_000),
    "label.manufacturer_name_address": (0, 1_000),
    "label.date_marking": (0, 200),
    "label.batch_or_lot": (0, 100),
    "label.other_text": (0, 4_000),
}
MAX_CLAIMS, CLAIM_CHARS = 20, 200

# Claim wording -> the nutrition field it needs declared (XF-10). English words only.
CLAIM_FIELDS: list[tuple[str, str]] = [
    (r"\badded sugars?\b", "nutrition.added_sugars_g"),
    (r"\bsaturated fat", "nutrition.saturated_fat_g"),
    (r"\btrans[ -]?fat", "nutrition.trans_fat_g"),
    (r"\b(sodium|salt)\b", "nutrition.sodium_mg"),
    (r"\bfib(re|er)\b", "nutrition.other.dietary_fibre_g"),
    (r"\bcholesterol\b", "nutrition.other.cholesterol_mg"),
]
MICRONUTRIENTS = ("calcium", "iron", "zinc", "iodine", "magnesium", "potassium", "vitamin")


def corpus_categories() -> list[str]:
    raw = os.environ.get("CORPUS_CATEGORIES", "").split("#", 1)[0]
    return [c.strip() for c in raw.split(",") if c.strip()] or ["breakfast-cereals"]


def _err(loc: str, message: str, code: str) -> FieldError:
    return FieldError(loc=loc, message=message, code=code)


def _get(raw: dict, loc: str):
    cur = raw
    for part in loc.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _num(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


# ---------------------------------------------------------------- stage 1: unknown fields + schema/type

_SECTIONS: dict[str, type[BaseModel]] = {"package": PackageSpec, "label": LabelText, "nutrition": NutritionPanel}


def unknown_fields(raw: dict) -> list[FieldError]:
    """A misspelt field ("protien_g") would otherwise be dropped silently and the label checked without it."""
    errors = [_err(str(k) or "body", f"Unknown field '{k}'.", "unknown_field")
              for k in raw if k not in LabelCheckRequest.model_fields]
    for section, model in _SECTIONS.items():
        value = raw.get(section)
        if isinstance(value, dict):
            errors += [_err(f"{section}.{k}", f"Unknown field '{k}' in {section}.", "unknown_field")
                       for k in value if k not in model.model_fields]
    return errors


_PYDANTIC_CODES = {"missing": "missing", "literal_error": "enum", "enum": "enum"}


def schema_errors(raw: dict) -> tuple[LabelCheckRequest | None, list[FieldError]]:
    """Strict: a number field takes a JSON number (an integer is fine), never "12"; the published schema says number."""
    try:
        return LabelCheckRequest.model_validate(raw, strict=True), []
    except ValidationError as exc:
        return None, [_err(".".join(str(p) for p in e["loc"]) or "body", e["msg"], _PYDANTIC_CODES.get(e["type"], "type"))
                      for e in exc.errors()]


# ---------------------------------------------------------------- stage 2: version, ranges, lengths, formats

def version_errors(raw: dict) -> list[FieldError]:
    v = raw.get("schema_version", "1.0")
    if isinstance(v, str) and v.split(".", 1)[0] == SUPPORTED_MAJOR and re.fullmatch(r"\d+\.\d+", v):
        return []
    return [_err("schema_version", f"Unsupported schema_version {v!r}; this service accepts {SUPPORTED_MAJOR}.x.",
                 "version")]


def _non_finite(value, loc: str) -> list[FieldError]:
    """json.loads accepts NaN and Infinity; every comparison with NaN is false, so no bound below would catch it."""
    if isinstance(value, float) and not math.isfinite(value):
        return [_err(loc, f"Must be a finite number (got {value}).", "range")]
    if isinstance(value, dict):
        return [e for k, v in value.items() for e in _non_finite(v, f"{loc}.{k}" if loc else str(k))]
    if isinstance(value, list):
        return [e for i, v in enumerate(value) for e in _non_finite(v, f"{loc}.{i}")]
    return []


def range_errors(raw: dict) -> list[FieldError]:
    """Checked on the raw values, so they are reported even when another field has a type error."""
    errors = _non_finite(raw, "")
    for loc, (lo, hi, exclusive) in RANGES.items():
        v = _num(_get(raw, loc))
        if v is None:
            continue
        if (v <= lo if exclusive else v < lo) or v > hi:
            low = f"greater than {lo:g}" if exclusive else f"at least {lo:g}"
            errors.append(_err(loc, f"Must be {low} and at most {hi:g} (got {v:g}).", "range"))
    q, unit = _num(_get(raw, "package.net_quantity")), _get(raw, "package.net_quantity_unit")
    if q is not None and (q <= 0 or (unit in NET_QUANTITY_MAX and q > NET_QUANTITY_MAX[unit])):
        hi = NET_QUANTITY_MAX.get(unit, 100_000)
        errors.append(_err("package.net_quantity", f"Must be greater than 0 and at most {hi:g} {unit or 'g'} "
                           f"(got {q:g}).", "range"))
    other = _get(raw, "nutrition.other")
    if isinstance(other, dict):
        for key, value in other.items():
            m = OTHER_KEY.match(str(key))
            if not m:
                errors.append(_err(f"nutrition.other.{key}", "Keys of nutrition.other are snake_case and end in their "
                                   "unit: _g, _mg, _mcg or _kcal (e.g. dietary_fibre_g).", "format"))
                continue
            v = _num(value)
            if v is not None and not 0 <= v <= OTHER_MAX[m.group(1)]:
                errors.append(_err(f"nutrition.other.{key}", f"Must be between 0 and {OTHER_MAX[m.group(1)]:g} "
                                   f"(got {v:g}).", "range"))
    return errors


def length_errors(raw: dict) -> list[FieldError]:
    errors = []
    for loc, (lo, hi) in LENGTHS.items():
        v = _get(raw, loc)
        if not isinstance(v, str):
            continue
        if lo and not v.strip():
            errors.append(_err(loc, "Must not be blank.", "length"))
        elif len(v) > hi:
            errors.append(_err(loc, f"At most {hi} characters (got {len(v)}).", "length"))
    claims = _get(raw, "label.claims")
    if isinstance(claims, list):
        if len(claims) > MAX_CLAIMS:
            errors.append(_err("label.claims", f"At most {MAX_CLAIMS} claims (got {len(claims)}).", "length"))
        for i, c in enumerate(claims):
            if isinstance(c, str) and (not c.strip() or len(c) > CLAIM_CHARS):
                errors.append(_err(f"label.claims.{i}", f"Each claim is 1-{CLAIM_CHARS} non-blank characters.", "length"))
    return errors


def format_errors(raw: dict) -> list[FieldError]:
    errors = []
    lic = _get(raw, "label.fssai_licence_number")
    if isinstance(lic, str) and lic.strip() and not LICENCE.match(re.sub(r"\s+", "", lic)):
        errors.append(_err("label.fssai_licence_number", "An FSSAI licence number is 14 digits (spaces allowed); "
                           "leave it out if the label has none.", "format"))
    pack = _get(raw, "package.pack_type")
    if isinstance(pack, str) and pack not in PACK_TYPES:
        errors.append(_err("package.pack_type", f"One of: {', '.join(PACK_TYPES)}.", "enum"))
    return errors


# ---------------------------------------------------------------- stage 3: category

def category_errors(raw: dict) -> list[FieldError]:
    """A well-formed category is accepted even if the corpus does not cover it: that run escalates to
    regulatory-review (F7), which is the defined handling for unsupported categories, not a reject."""
    c = raw.get("declared_category")
    if isinstance(c, str) and not (2 <= len(c) <= 64 and SLUG.match(c)):
        return [_err("declared_category", "A category id is 2-64 characters of lower-case letters, digits and "
                     f"hyphens (supported: {', '.join(corpus_categories())}; any other id is checked and escalated "
                     "as out of scope).", "category")]
    return []


# ---------------------------------------------------------------- stage 4: cross-field rules (XF-01 ...)

CrossFieldRule = Callable[[LabelCheckRequest], list[FieldError]]


def xf01_basis_unit(r: LabelCheckRequest) -> list[FieldError]:
    if r.nutrition.basis == "per_100ml" and r.package.net_quantity_unit not in ("ml", "l"):
        return [_err("nutrition.basis", "A per_100ml panel needs a net quantity in ml or l "
                     f"(net_quantity_unit is '{r.package.net_quantity_unit}').", "XF-01")]
    return []


def xf02_serving_pair(r: LabelCheckRequest) -> list[FieldError]:
    n = r.nutrition
    if (n.serving_size is None) != (n.serving_unit is None):
        missing = "serving_unit" if n.serving_unit is None else "serving_size"
        return [_err(f"nutrition.{missing}", "serving_size and serving_unit are given together or not at all.", "XF-02")]
    return []


def xf03_serving_unit_basis(r: LabelCheckRequest) -> list[FieldError]:
    n = r.nutrition
    want = "g" if n.basis == "per_100g" else "ml"
    if n.serving_unit is not None and n.serving_unit != want:
        return [_err("nutrition.serving_unit", f"A {n.basis} panel gives servings in {want}.", "XF-03")]
    return []


def xf04_added_le_total_sugars(r: LabelCheckRequest) -> list[FieldError]:
    n = r.nutrition
    if n.added_sugars_g is not None and n.added_sugars_g > n.total_sugars_g:
        return [_err("nutrition.added_sugars_g", f"Added sugars ({n.added_sugars_g:g} g) cannot exceed total sugars "
                     f"({n.total_sugars_g:g} g).", "XF-04")]
    return []


def xf05_sugars_le_carbohydrate(r: LabelCheckRequest) -> list[FieldError]:
    n = r.nutrition
    if n.total_sugars_g > n.carbohydrate_g:
        return [_err("nutrition.total_sugars_g", f"Total sugars ({n.total_sugars_g:g} g) cannot exceed carbohydrate "
                     f"({n.carbohydrate_g:g} g).", "XF-05")]
    return []


def xf06_fat_parts_le_total(r: LabelCheckRequest) -> list[FieldError]:
    n = r.nutrition
    parts = (n.saturated_fat_g or 0) + (n.trans_fat_g or 0)
    if parts > n.total_fat_g:
        return [_err("nutrition.saturated_fat_g" if n.saturated_fat_g else "nutrition.trans_fat_g",
                     f"Saturated + trans fat ({parts:g} g) cannot exceed total fat ({n.total_fat_g:g} g).", "XF-06")]
    return []


def xf07_mass_balance(r: LabelCheckRequest) -> list[FieldError]:
    n = r.nutrition
    if n.basis != "per_100g":
        return []
    total = n.protein_g + n.carbohydrate_g + n.total_fat_g
    if total > 100 + MASS_ROUNDING_G:
        return [_err("nutrition", f"Protein + carbohydrate + fat is {total:g} g per 100 g, which is more than the "
                     "100 g it is declared for.", "XF-07")]
    return []


def xf08_energy_consistent(r: LabelCheckRequest) -> list[FieldError]:
    n = r.nutrition
    computed = sum(getattr(n, f) * k for f, k in ENERGY_FACTORS.items())
    allowed = max(computed * ENERGY_TOLERANCE, ENERGY_FLOOR_KCAL)
    if abs(n.energy_kcal - computed) > allowed:
        return [_err("nutrition.energy_kcal", f"Declared energy {n.energy_kcal:g} kcal is not consistent with "
                     f"4/4/9 kcal per g of protein/carbohydrate/fat ({computed:g} kcal, ±{allowed:g} allowed).", "XF-08")]
    return []


def xf09_panel_le_surface(r: LabelCheckRequest) -> list[FieldError]:
    p = r.package
    if p.total_surface_area_cm2 is not None and p.principal_display_panel_cm2 > p.total_surface_area_cm2:
        return [_err("package.principal_display_panel_cm2", "The principal display panel cannot be larger than the "
                     f"package's total surface area ({p.total_surface_area_cm2:g} cm²).", "XF-09")]
    return []


def xf10_claimed_nutrient_declared(r: LabelCheckRequest) -> list[FieldError]:
    errors, n = [], r.nutrition
    for i, claim in enumerate(r.label.claims):
        low = claim.lower()
        for pattern, loc in CLAIM_FIELDS:
            if not re.search(pattern, low):
                continue
            field = loc.removeprefix("nutrition.")
            value = n.other.get(field.split(".", 1)[1]) if field.startswith("other.") else getattr(n, field)
            if value is None:
                errors.append(_err(loc, f"The claim '{claim}' needs {loc} declared on the panel.", "XF-10"))
            break  # one nutrient per claim: "low saturated fat" is not also a "fat" claim
        for word in MICRONUTRIENTS:
            if re.search(rf"\b{word}", low) and not any(word in k for k in n.other):
                errors.append(_err(f"label.claims.{i}", f"The claim '{claim}' needs its {word} content declared in "
                                   f"nutrition.other (e.g. {word}_mg).", "XF-10"))
    return errors


XF_RULES = {
    "XF-01": "A per_100ml nutrition panel needs a net quantity in ml or l.",
    "XF-02": "serving_size and serving_unit are given together or not at all.",
    "XF-03": "serving_unit is g for a per_100g panel and ml for a per_100ml panel.",
    "XF-04": "added_sugars_g <= total_sugars_g.",
    "XF-05": "total_sugars_g <= carbohydrate_g.",
    "XF-06": "saturated_fat_g + trans_fat_g <= total_fat_g.",
    "XF-07": "On a per_100g panel, protein_g + carbohydrate_g + total_fat_g <= 100 g (+1 g rounding).",
    "XF-08": "energy_kcal is within ±20 % (at least ±10 kcal) of 4·protein + 4·carbohydrate + 9·fat.",
    "XF-09": "principal_display_panel_cm2 <= total_surface_area_cm2 when both are given.",
    "XF-10": "A claim about a nutrient that is optional on the panel needs that nutrient declared.",
}

CROSS_FIELD_RULES: list[CrossFieldRule] = [
    xf01_basis_unit, xf02_serving_pair, xf03_serving_unit_basis, xf04_added_le_total_sugars,
    xf05_sugars_le_carbohydrate, xf06_fat_parts_le_total, xf07_mass_balance, xf08_energy_consistent,
    xf09_panel_le_surface, xf10_claimed_nutrient_declared,
]


# ---------------------------------------------------------------- all of it

def validate(raw) -> tuple[LabelCheckRequest | None, list[FieldError]]:
    if not isinstance(raw, dict):
        return None, [_err("body", "The request body must be a JSON object.", "type")]
    if set(raw) <= {"_unparseable_body", "_non_object_body"} and raw:
        return None, [_err("body", "The request body must be a JSON object.", "json_invalid")]
    request, errors = schema_errors(raw)
    errors = unknown_fields(raw) + errors + version_errors(raw) + range_errors(raw) + length_errors(raw) \
        + format_errors(raw) + category_errors(raw)
    if request is not None:
        for rule in CROSS_FIELD_RULES:
            errors += rule(request)
    # one error per (loc, code): pydantic and our own checks can both see the same problem
    seen, unique = set(), []
    for e in errors:
        if (e.loc, e.code) not in seen:
            seen.add((e.loc, e.code))
            unique.append(e)
    return (request if not unique else None), unique
