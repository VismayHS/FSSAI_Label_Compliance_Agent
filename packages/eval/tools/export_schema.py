"""Write docs/data-contract.schema.json: the LabelCheckRequest JSON Schema plus the gate's own constraints (V1.1).

    <venv-python> packages/eval/tools/export_schema.py            # writes the file
    <venv-python> packages/eval/tools/export_schema.py --check    # exit 1 if the committed file is out of date

The shape comes from fssai_contracts.schemas.LabelCheckRequest; ranges, lengths, formats and permitted values
come from fssai_gate.rules, so the published schema and the gate cannot drift apart. Cross-field rules (XF-01 ...)
cannot be expressed in JSON Schema; they are listed under "x-cross-field-rules" and described in
docs/data-contract.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fssai_contracts.schemas import SCHEMA_VERSION, LabelCheckRequest
from fssai_gate import rules

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "docs" / "data-contract.schema.json"


def _prop(schema: dict, loc: str) -> dict:
    section, _, name = loc.rpartition(".")
    defs = {"package": "PackageSpec", "label": "LabelText", "nutrition": "NutritionPanel"}
    props = schema["$defs"][defs[section]]["properties"] if section else schema["properties"]
    p = props[name]
    # Optional fields are anyOf [{type}, {type: null}]: put constraints on the non-null branch.
    return next((b for b in p.get("anyOf", []) if b.get("type") != "null"), p)


def build() -> dict:
    schema = LabelCheckRequest.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://github.com/VismayHS/FSSAI_Label_Compliance_Agent/docs/data-contract.schema.json"
    schema["title"] = "LabelCheckRequest"
    schema["description"] = ("FSSAI Label Compliance Agent: POST /v1/runs request body, data contract v"
                             f"{SCHEMA_VERSION}. Human-readable contract: docs/data-contract.md.")
    schema["additionalProperties"] = False
    for name in ("PackageSpec", "LabelText", "NutritionPanel"):
        schema["$defs"][name]["additionalProperties"] = False

    for loc, (lo, hi, exclusive) in rules.RANGES.items():
        p = _prop(schema, loc)
        p["exclusiveMinimum" if exclusive else "minimum"] = lo
        p["maximum"] = hi
    _prop(schema, "package.net_quantity").update(exclusiveMinimum=0, maximum=max(rules.NET_QUANTITY_MAX.values()),
                                                description="Upper bound depends on the unit: "
                                                + ", ".join(f"{u} <= {v:g}" for u, v in rules.NET_QUANTITY_MAX.items()))
    for loc, (lo, hi) in rules.LENGTHS.items():
        p = _prop(schema, loc)
        p["maxLength"] = hi
        if lo:
            p["minLength"] = lo
            p["pattern"] = r"\S"
    claims = _prop(schema, "label.claims")
    claims.update(maxItems=rules.MAX_CLAIMS)
    claims["items"].update(minLength=1, maxLength=rules.CLAIM_CHARS, pattern=r"\S")
    _prop(schema, "label.fssai_licence_number").update(pattern=r"^\s*(\d\s*){14}$")
    _prop(schema, "package.pack_type").update(enum=list(rules.PACK_TYPES))
    _prop(schema, "schema_version").update(pattern=rf"^{rules.SUPPORTED_MAJOR}\.\d+$")
    _prop(schema, "declared_category").update(
        pattern=rules.SLUG.pattern, minLength=2, maxLength=64,
        examples=rules.corpus_categories(),
        description="Supported: " + ", ".join(rules.corpus_categories()) + ". Any other well-formed id is "
                    "accepted and the run escalates to regulatory-review (F7).")
    other = _prop(schema, "nutrition.other")
    other["propertyNames"] = {"pattern": rules.OTHER_KEY.pattern}
    other["additionalProperties"] = {"type": "number", "minimum": 0}
    other["description"] = "Further nutrients; each key ends in its unit, e.g. dietary_fibre_g, iron_mg."
    schema["x-cross-field-rules"] = dict(rules.XF_RULES)
    return schema


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if the committed schema is out of date")
    args = ap.parse_args(argv)
    text = json.dumps(build(), indent=2, sort_keys=False) + "\n"
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print(f"{OUT.relative_to(ROOT)} is out of date: run packages/eval/tools/export_schema.py", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
