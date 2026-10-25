"""Grounding: a citation is only kept when its quote is a verbatim span of a retrieved passage (A3).

The research LLM copies quotes imperfectly (whitespace, quote marks, ellipses). `locate_quote` maps what it
wrote back to the exact text of the passage, so a near-miss becomes a verbatim quote and an invention is dropped.
"""
from __future__ import annotations

import difflib
import re

from fssai_contracts.schemas import Citation, Finding, FindingStatus, Passage

MAX_QUOTE_CHARS = 400
_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-"})
_WORD = re.compile(r"\S+")
_NUMBERS = re.compile(r"\d+(?:\.\d+)?")


def _squash(s: str) -> str:
    return " ".join(s.translate(_QUOTES).split()).lower()


def locate_quote(quote: str, text: str) -> str | None:
    """The exact span of `text` that `quote` stands for, or None if it cannot be matched with confidence."""
    quote = (quote or "").strip().strip("\"'\u201c\u201d\u2018\u2019").strip()
    quote = re.sub(r"^(?:\.\.\.|\u2026)\s*|\s*(?:\.\.\.|\u2026)$", "", quote).strip()
    if len(quote) < 8:
        return None
    if quote in text:
        return quote[:MAX_QUOTE_CHARS]
    target = _squash(quote)
    if not target:
        return None
    matches = list(_WORD.finditer(text))
    squashed = [_squash(m.group()) for m in matches]
    n = len(target.split())
    # whitespace / quote-mark differences: slide a word window over the passage
    for size in (n, n - 1, n + 1):
        if size < 1:
            continue
        for i in range(0, len(matches) - size + 1):
            if " ".join(squashed[i:i + size]) == target:
                return _span(text, matches, i, size)
    # a very close copy (a dropped or changed word): accept only a near-identical window, never an invention
    best_i, best_ratio = None, 0.0
    step = max(1, n // 8)
    for i in range(0, max(1, len(matches) - n + 1), step):
        cand = " ".join(squashed[i:i + n])
        ratio = difflib.SequenceMatcher(None, target, cand, autojunk=False).ratio()
        if ratio > best_ratio:
            best_i, best_ratio = i, ratio
    if best_i is not None and best_ratio >= 0.95:
        window = " ".join(squashed[best_i:best_i + n])
        # a changed number is a different claim, not a typo: never "repair" it into the real text
        if _NUMBERS.findall(target) == _NUMBERS.findall(window):
            return _span(text, matches, best_i, n)
    return None


def _span(text: str, matches: list, start: int, size: int) -> str | None:
    window = matches[start:start + size]
    if not window:
        return None
    span = text[window[0].start():window[-1].end()]
    return span[:MAX_QUOTE_CHARS] if span.strip() else None


def ground_findings(raw_findings: list[dict], passages: list[Passage]) -> tuple[list[Finding], list[str]]:
    """Turn the model's findings into Findings whose every citation resolves to retrieved text.

    Returns (findings, notes). A finding that loses all its citations is downgraded to cannot_determine, because
    "met"/"unmet" without a grounded citation is an unverified answer (A3).
    """
    by_id = {p.passage_id: p for p in passages}
    notes: list[str] = []
    findings: list[Finding] = []
    seen: set[str] = set()
    for raw in raw_findings:
        if not isinstance(raw, dict):
            continue
        rid = re.sub(r"[^A-Z0-9-]+", "-", str(raw.get("requirement_id", "")).upper()).strip("-")
        if not rid or rid in seen:
            continue
        seen.add(rid)
        try:
            status = FindingStatus(str(raw.get("status", "")).strip().lower())
        except ValueError:
            status = FindingStatus.CANNOT_DETERMINE
            notes.append(f"{rid}: unknown status '{raw.get('status')}', treated as cannot_determine")
        citations: list[Citation] = []
        for c in raw.get("citations") or []:
            if not isinstance(c, dict):
                continue
            quote, pid = str(c.get("quote", "")), str(c.get("passage_id", ""))
            passage = by_id.get(pid)
            span = locate_quote(quote, passage.text) if passage else None
            if span is None:  # wrong passage id: find the passage the quote really came from
                for other in passages:
                    span = locate_quote(quote, other.text)
                    if span:
                        passage = other
                        break
            if span and passage:
                cite = Citation(regulation=passage.regulation, clause_id=passage.clause_id,
                                passage_id=passage.passage_id, quote=span)
                if cite not in citations:
                    citations.append(cite)
            else:
                notes.append(f"{rid}: dropped a citation that is not in the retrieved text")
        explanation = str(raw.get("explanation", "")).strip()[:1500]
        if not citations and status != FindingStatus.CANNOT_DETERMINE:
            notes.append(f"{rid}: no citation could be grounded; downgraded from {status.value} to cannot_determine")
            explanation = f"[no grounded citation] {explanation}".strip()
            status = FindingStatus.CANNOT_DETERMINE
        findings.append(Finding(requirement_id=rid, requirement=str(raw.get("requirement", rid)).strip()[:300] or rid,
                                status=status, explanation=explanation, citations=citations))
    return findings, notes
