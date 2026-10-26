"""Claim-trigger hints (data/corpus/claim_triggers.yaml): claim wording -> Claims-regulation clauses.

A query fires a hint when it contains a claim word ("source", "high", "provides", ...) and a nutrient
word ("protein"). The hint returns clause ids, most specific first; the retriever fuses them into the
ranking like a third retriever, so a hint can lift a clause but never invent one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

SCHEDULE_I_ROW = "Schedule I, item {item}"


@dataclass(frozen=True)
class ClauseRef:
    regulation: str
    clause_id: str


class ClaimHints:
    def __init__(self, data: dict) -> None:
        words = sorted(data.get("claim_words", []), key=len, reverse=True)
        self.claim_re = re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.I) if words else None
        self.always = [ClauseRef(c["regulation"], c["clause_id"]) for c in data.get("always", [])]
        self.nutrients: list[tuple[re.Pattern, ClauseRef, int]] = []
        for spec in (data.get("nutrients") or {}).values():
            pats = sorted(spec.get("patterns", []), key=len, reverse=True)
            if pats:
                rx = re.compile(r"\b(" + "|".join(re.escape(p) for p in pats) + r")\b", re.I)
                ref = ClauseRef("FSS-AC-2018", SCHEDULE_I_ROW.format(item=spec["item"]))
                self.nutrients.append((rx, ref, len(pats[0])))
        self.nutrients.sort(key=lambda t: -t[2])  # "saturated fat" is tried before "fat"

    @classmethod
    def load(cls, path: Path) -> ClaimHints | None:
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else None

    def refs(self) -> list[ClauseRef]:
        return [*self.always, *(ref for _, ref, _ in self.nutrients)]

    def match(self, query: str) -> list[ClauseRef]:
        if not self.claim_re or not self.claim_re.search(query):
            return []
        hits: list[ClauseRef] = []
        spans: list[tuple[int, int]] = []  # a shorter phrase inside a longer match ("fat" in "trans fat") is skipped
        for rx, ref, _ in self.nutrients:
            for m in rx.finditer(query):
                if not any(s <= m.start() < e or s < m.end() <= e for s, e in spans):
                    spans.append((m.start(), m.end()))
                    if ref not in hits:
                        hits.append(ref)
        return [*hits, *self.always] if hits else []
