"""Search the corpus PDFs page by page, with context, to locate passages (N1.1). Quotes come from here,
never from memory.

    <venv-python> corpus/tools/grep_pdf.py "source of protein" "nutritional information" --context 3
    <venv-python> corpus/tools/grep_pdf.py "Schedule" --file FSS-AC-2018_compendium_2021-11-16.pdf

Case-insensitive; whitespace inside a term matches any whitespace, including line breaks, so a phrase
split across lines is still found. Prints file, page, line and ±N lines around each hit.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from pypdf import PdfReader

RAW = Path(__file__).resolve().parents[1] / "raw"


def search(pdf: Path, terms: list[str], context: int) -> list[str]:
    out = []
    patterns = [(t, re.compile(r"\s+".join(map(re.escape, t.split())), re.I)) for t in terms]
    for page_no, page in enumerate(PdfReader(str(pdf)).pages, start=1):
        text = page.extract_text() or ""
        lines = text.splitlines()
        starts, pos = [], 0
        for line in lines:
            starts.append(pos)
            pos += len(line) + 1
        for term, rx in patterns:
            for m in rx.finditer(text):
                n = max(i for i, s in enumerate(starts) if s <= m.start())
                lo, hi = max(0, n - context), min(len(lines), n + context + 1)
                block = "\n".join(f"  {'>' if i == n else ' '} {i + 1:3d}| {lines[i]}" for i in range(lo, hi))
                out.append(f"{pdf.name} p.{page_no} line {n + 1}  [{term}]\n{block}")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("terms", nargs="+")
    p.add_argument("--context", type=int, default=3)
    p.add_argument("--file", default=None, help="one PDF in corpus/raw (default: all)")
    args = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    pdfs = [RAW / args.file] if args.file else sorted(RAW.glob("*.pdf"))
    hits = [h for pdf in pdfs for h in search(pdf, args.terms, args.context)]
    print("\n\n".join(hits) if hits else "no matches")
    print(f"\n{len(hits)} match(es)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
