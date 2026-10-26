"""Write data/corpus/manifest.json from data/corpus/raw/*.pdf and data/corpus/sources.yaml, and print a table (N0.2).

    <venv-python> data/corpus/tools/manifest.py

Per file: title, regulation, version, sha256, page count, text layer (extractable text on >= 90 % of
pages), source URL and where the bytes were retrieved from. Idempotent: an unchanged corpus leaves the
file untouched. Same as `python -m fssai_ingest manifest`; the logic lives in fssai_ingest.corpus.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fssai_ingest.__main__ import main

if __name__ == "__main__":
    corpus = Path(__file__).resolve().parents[1]
    sys.exit(main(["manifest", "--corpus", str(corpus / "raw"), "--out", str(corpus / "manifest.json")]))
