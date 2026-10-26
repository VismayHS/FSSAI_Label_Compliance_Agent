"""Make every citation quote a verbatim span of a retrieved passage (A3).

The model often copies a quote with different whitespace or quote marks. If the normalised quote
occurs in the passage, we replace it with the passage's own exact span. Anything else is dropped:
a paraphrase is never kept as a "quote".
"""
from __future__ import annotations

import re

from fssai_contracts.schemas import Citation, Passage

_MIN_QUOTE_CHARS = 12
_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-"})


def _squash(text: str) -> tuple[str, list[int]]:
    """Lower-case, fold quotes/dashes, collapse whitespace; keep a map back to original indexes."""
    out, index, prev_space = [], [], True
    for i, ch in enumerate(text.translate(_QUOTES)):
        if ch.isspace():
            if not prev_space:
                out.append(" ")
                index.append(i)
            prev_space = True
        else:
            out.append(ch.lower())
            index.append(i)
            prev_space = False
    return "".join(out).rstrip(), index


def exact_span(quote: str, passage: Passage) -> str | None:
    """The passage's own text for this quote, or None if the quote is not in the passage."""
    quote = quote.strip().strip("\"'\u201c\u201d")
    if len(quote) < _MIN_QUOTE_CHARS:
        return None
    if quote in passage.text:
        return quote
    hay, index = _squash(passage.text)
    needle, _ = _squash(quote)
    needle = needle.strip(" .")
    pos = hay.find(needle) if len(needle) >= _MIN_QUOTE_CHARS else -1
    if pos < 0:
        return None
    start = index[pos]
    end = index[pos + len(needle) - 1] + 1
    span = passage.text[start:end]
    return span if span and span in passage.text else None


def ground_citations(raw: list[dict], passages: dict[str, Passage]) -> tuple[list[Citation], list[str]]:
    """Turn the model's citation dicts into Citations that resolve; return notes about what was dropped."""
    kept, dropped = [], []
    seen: set[tuple[str, str]] = set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        pid, quote = str(item.get("passage_id", "")).strip(), str(item.get("quote", ""))
        passage = passages.get(pid)
        if passage is None:
            dropped.append(f"citation to unretrieved passage '{pid}'")
            continue
        span = exact_span(quote, passage)
        if span is None:
            dropped.append(f"quote not found verbatim in {pid}")
            continue
        if (pid, span) in seen:
            continue
        seen.add((pid, span))
        kept.append(Citation(regulation=passage.regulation, clause_id=passage.clause_id, passage_id=pid, quote=span))
    return kept, dropped


_CROSS_REF = re.compile(r"\b(?:Schedule\s*[-–]?\s*[IVX]+|regulation\s+\d+(?:\(\w+\))*|clause\s+\d+(?:\(\w+\))*)", re.IGNORECASE)


def cross_references(passages: list[Passage]) -> list[str]:
    """Clause or schedule names mentioned inside passages: candidates for a follow-up lookup."""
    found: list[str] = []
    for p in passages:
        for m in _CROSS_REF.finditer(p.text):
            ref = re.sub(r"\s+", " ", m.group(0)).strip()
            if ref.lower() not in {f.lower() for f in found}:
                found.append(ref)
    return found
