"""A valid breakfast-cereal request as a raw dict, and a way to change one field of it."""
from __future__ import annotations

import copy


def valid() -> dict:
    # energy: 4*10 + 4*72 + 9*6 = 382 kcal, consistent with the declared 380 (XF-08)
    return {
        "schema_version": "1.0",
        "declared_category": "breakfast-cereals",
        "package": {"net_quantity": 500, "net_quantity_unit": "g", "principal_display_panel_cm2": 180,
                    "total_surface_area_cm2": 900, "pack_type": "single"},
        "label": {"product_name": "Multigrain flakes", "claims": ["Source of fibre"],
                  "ingredients": "Wheat, oats, rice, sugar, salt", "allergen_statement": "Contains: wheat, oats",
                  "veg_status": "veg", "fssai_licence_number": "10012345678901"},
        "nutrition": {"basis": "per_100g", "serving_size": 30, "serving_unit": "g", "energy_kcal": 380,
                      "protein_g": 10, "carbohydrate_g": 72, "total_sugars_g": 9, "added_sugars_g": 6,
                      "total_fat_g": 6, "saturated_fat_g": 1.2, "trans_fat_g": 0, "sodium_mg": 300,
                      "other": {"dietary_fibre_g": 8}},
    }


def with_(path: str, value, base: dict | None = None) -> dict:
    """valid() with one dotted path set (value=DELETE removes it)."""
    raw = copy.deepcopy(base or valid())
    *parents, last = path.split(".")
    cur = raw
    for p in parents:
        cur = cur[p]
    if value is DELETE:
        cur.pop(last, None)
    else:
        cur[last] = value
    return raw


DELETE = object()
