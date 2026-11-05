"""Make every citation quote a verbatim span of a retrieved passage (A3).

The model often copies a quote with different whitespace or quote marks. If the normalised quote
occurs in the passage, we replace it with the passage's own exact span. A quote shortened with "..."
is kept only if every part occurs in the passage in order; each part is stored as its own exact span.
Anything else is dropped: a paraphrase is never kept as a "quote".
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


def _find(needle: str, hay: str, index: list[int], text: str, start: int = 0) -> tuple[str, int] | None:
    """Find a squashed needle in the squashed passage from `start`; return the original span and where it ends."""
    needle = needle.strip(" .")
    pos = hay.find(needle, start) if len(needle) >= _MIN_QUOTE_CHARS else -1
    if pos < 0:
        return None
    span = text[index[pos]:index[pos + len(needle) - 1] + 1]
    return (span, pos + len(needle)) if span and span in text else None


def exact_span(quote: str, passage: Passage) -> str | None:
    """The passage's own text for this quote, or None if the quote is not in the passage."""
    quote = quote.strip().strip("\"'\u201c\u201d")
    if len(quote) < _MIN_QUOTE_CHARS:
        return None
    if quote in passage.text:
        return quote
    hay, index = _squash(passage.text)
    found = _find(_squash(quote)[0], hay, index, passage.text)
    return found[0] if found else None


# "...", "\u2026", ". . ." and "[...]": how a model marks text it left out of a quote.
_ELLIPSIS = re.compile(r"\s*(?:\[\s*(?:\.\s*){3}\]|\[\s*\u2026\s*\]|(?:\.\s*){3,}|\u2026)\s*")


def exact_spans(quote: str, passage: Passage) -> list[str] | None:
    """Like exact_span, but a quote shortened with an ellipsis is accepted when every part occurs in the
    passage, in order. Each part long enough to stand alone becomes its own verbatim span; short parts are
    only checked. One part that is not in the passage (or is out of order) rejects the whole quote."""
    span = exact_span(quote, passage)
    if span is not None:
        return [span]
    parts = [p.strip().strip("\"'\u201c\u201d") for p in _ELLIPSIS.split(quote.strip())]
    parts = [p for p in parts if p.strip(" .")]
    if len(parts) < 2:
        return None
    hay, index = _squash(passage.text)
    spans, cursor = [], 0
    for part in parts:
        needle = _squash(part)[0].strip(" .")
        if len(needle) >= _MIN_QUOTE_CHARS:
            found = _find(needle, hay, index, passage.text, cursor)
            if found is None:
                return None
            spans.append(found[0])
            cursor = found[1]
        else:  # too short to cite alone, but it must still be there, after the previous part
            pos = hay.find(needle, cursor)
            if pos < 0:
                return None
            cursor = pos + len(needle)
    return spans or None


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
        spans = exact_spans(quote, passage)
        if spans is None:
            dropped.append(f"quote not found verbatim in {pid}")
            continue
        for span in spans:
            if (pid, span) in seen:
                continue
            seen.add((pid, span))
            kept.append(Citation(regulation=passage.regulation, clause_id=passage.clause_id, passage_id=pid,
                                 quote=span))
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
