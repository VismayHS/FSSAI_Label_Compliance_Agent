"""Small helpers shared by the agents: untrusted-text blocks and request facts."""
from __future__ import annotations

import re

from fssai_contracts.schemas import LabelCheckRequest

_TAG = re.compile(r"</?\s*label_data[^>]*>", re.IGNORECASE)


def data_block(name: str, value: str, limit: int = 2000) -> str:
    """Wrap untrusted label text so it reads as data. A forged closing tag cannot end the block."""
    safe = _TAG.sub("[removed tag]", value)[:limit]
    return f'<label_data field="{name}">\n{safe}\n</label_data>'


def request_facts(request: LabelCheckRequest) -> dict:
    """Structured facts the agents may see directly. Free text is reduced to presence flags;
    the text itself is only reachable through request_field_lookup, which marks it untrusted."""
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
        "number_of_claims_printed": len(label.claims),
    }
