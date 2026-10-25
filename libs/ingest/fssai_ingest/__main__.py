"""python -m fssai_ingest build --corpus corpus/raw --out <INDEX_DIR> [--reembed none|changed|all]  (N2.1)

    build      parse -> clause-aware chunk (decision 002) -> embed locally (EMBEDDING_MODEL) -> FAISS.
               Idempotent: re-running with no changes rewrites nothing. Prints a JSON report.
               Exit 3: stored chunks changed text or model and --reembed none was given.
    manifest   write corpus/manifest.json (provenance, sha256, pages, text layer) and print a table (N0.2).
    chunks     print the chunks the build would index, for inspecting the chunker.

The `build` options are the agreed interface: the indexer container runs this command.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fssai_ingest", description="Build the regulation index (D2).")
    sub = p.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="parse, chunk, embed and index; re-running with no changes does nothing")
    build.add_argument("--corpus", default="corpus/raw", help="folder of regulation PDFs")
    build.add_argument("--out", default=os.environ.get("INDEX_DIR", "/data/index"), help="index folder")
    build.add_argument("--reembed", choices=("none", "changed", "all"), default="none",
                       help="changed = only chunks whose text or embedding model changed")

    man = sub.add_parser("manifest", help="write corpus/manifest.json from corpus/raw and corpus/sources.yaml")
    man.add_argument("--corpus", default="corpus/raw")
    man.add_argument("--out", default=None, help="default: <corpus>/../manifest.json")

    chunks = sub.add_parser("chunks", help="print the chunks of every PDF (inspection)")
    chunks.add_argument("--corpus", default="corpus/raw")
    chunks.add_argument("--text", action="store_true", help="print each chunk's full text too")
    chunks.add_argument("--superseded", action="store_true", help="include superseded text")
    return p


def _build(args) -> int:
    from .build import ReembedRequired, build_index

    try:
        report = build_index(Path(args.corpus), Path(args.out), reembed=args.reembed)
    except ReembedRequired as exc:
        print(f"fssai_ingest build: {exc}", file=sys.stderr)
        return 3
    print(json.dumps(report.summary(), indent=2))
    return 0


def _manifest(args) -> int:
    from .corpus import manifest, scan

    corpus = Path(args.corpus)
    docs = scan(corpus)
    out = Path(args.out) if args.out else corpus.parent / "manifest.json"
    data = manifest(docs)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if not out.exists() or out.read_text(encoding="utf-8") != text:  # idempotent: unchanged corpus, untouched file
        out.write_text(text, encoding="utf-8", newline="\n")
    print(f"{'file':<42} {'regulation':<12} {'version':<26} {'pages':>5} {'text':>5}  sha256")
    for d in docs:
        print(f"{d.filename:<42} {d.regulation:<12} {d.doc_version:<26} {d.page_count:>5} "
              f"{'yes' if d.has_text_layer else 'NO':>5}  {d.sha256[:16]}…")
    print(f"wrote {out}")
    return 0


def _chunks(args) -> int:
    from .build import chunk_corpus, max_chars_from_env
    from .corpus import scan

    corpus = Path(args.corpus)
    for c in chunk_corpus(scan(corpus), corpus, max_chars_from_env()):
        if not args.superseded and not c.in_force:
            continue
        print(f"{c.passage_id}\tp{c.page}\t{len(c.text)}\t{' › '.join(c.heading_path)}")
        if args.text:
            print(f"    {c.text}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(message)s")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    return {"build": _build, "manifest": _manifest, "chunks": _chunks}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
