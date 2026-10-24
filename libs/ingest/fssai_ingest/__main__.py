"""python -m fssai_ingest build --corpus corpus/raw --out <INDEX_DIR> [--reembed changed] (contexts/Nishkal.md N2.1).

Day-0 skeleton: the options are the agreed interface (the indexer container runs this command);
the pipeline behind them is N2.1: parse -> clause-aware chunk (decision 002) -> embed locally
(EMBEDDING_MODEL) -> FAISS, idempotent by stable chunk ids, writing index_manifest.json for freshness.
"""
from __future__ import annotations

import argparse
import os
import sys


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fssai_ingest", description="Build the regulation index (D2).")
    sub = p.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="parse, chunk, embed and index; re-running with no changes does nothing")
    build.add_argument("--corpus", default="corpus/raw", help="folder of regulation PDFs")
    build.add_argument("--out", default=os.environ.get("INDEX_DIR", "/data/index"), help="index folder")
    build.add_argument("--reembed", choices=("none", "changed", "all"), default="none",
                       help="changed = only chunks whose text or embedding model changed")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    print(f"fssai_ingest {args.command}: not built yet (contexts/Nishkal.md N2.1)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
