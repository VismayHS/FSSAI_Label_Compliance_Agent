"""Text helpers: walk every string in a request, and fold text so simple obfuscation does not hide an attack."""
from __future__ import annotations

import re
import unicodedata

from fssai_contracts.schemas import LabelCheckRequest

# zero-width, bidi controls and the BOM: invisible characters that can hide or reorder text
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u200e\u200f\u2060\u2061\u2062\u2063\u2064\ufeff\u00ad"
                               "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"))
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i"})
_SPACED = re.compile(r"(?<![^\W_])(?:[^\W_] ){3,}[^\W_](?![^\W_])")


def request_strings(request: LabelCheckRequest) -> dict[str, str]:
    """Every string value in the request, keyed by dotted path (claims as label.claims[0]).
    Every one is untrusted: not only the obvious free-text fields (L4)."""
    out: dict[str, str] = {}

    def walk(prefix: str, node: object) -> None:
        if isinstance(node, str):
            if node:
                out[prefix] = node
        elif isinstance(node, dict):
            for key, value in node.items():
                if prefix == "" and key == "schema_version":
                    continue
                walk(f"{prefix}.{key}" if prefix else str(key), value)
                if isinstance(key, str) and prefix.endswith(".other") and key:
                    out.setdefault(f"{prefix}.{key}#name", key)  # a dict key is text too
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(f"{prefix}[{i}]", item)

    walk("", request.model_dump(mode="json"))
    return out


def fold(text: str, *, leet: bool = False) -> str:
    """Lower-case NFKC text with invisible characters removed, spaced-out letters joined and whitespace
    collapsed. leet=True also maps common digit/symbol substitutions (1gn0re -> ignore)."""
    text = unicodedata.normalize("NFKC", text).translate(_INVISIBLE).lower()
    text = _SPACED.sub(lambda m: m.group(0).replace(" ", ""), text)
    if leet:
        text = text.translate(_LEET)
    return re.sub(r"\s+", " ", text).strip()
