"""The index build (D2, L1): read -> parse -> clause-aware chunk -> embed locally -> FAISS (via LangChain).

Idempotent by construction:
- A chunk's id is its passage_id ("FSS-AC-2018:Schedule I, item 11~substituted"): regulation + clause +
  standing, so it is stable across runs and does not change when the text is corrected.
- chunk_table.json records what each stored vector was made from: the hash of the embedded text and the
  embedding model alias.
- A run compares the corpus with that table. New chunks are embedded and added, vanished ones deleted,
  and nothing else is touched. Re-running with no changes rewrites nothing, not even built_at.

--reembed modes (the CLI options the indexer container uses):
- none     add new chunks, delete removed ones; refuse (exit 3) if a stored chunk's text or the
           embedding model changed, so stale and fresh vectors are never mixed silently
- changed  as none, and re-embed exactly the chunks whose text or model changed, in place (L1)
- all      embed everything again into a fresh index
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from fssai_retrieval.index import (
    CHUNK_TABLE, FAISS_NAME, MANIFEST, PASSAGES, TRIGGERS, Chunk, embedding_alias, get_embeddings, read_json,
    write_json, write_passages,
)

from .chunker import chunk_document
from .corpus import Document, scan
from .pdftext import page_texts

CHUNKER_VERSION = "3"  # bump when the chunker's output changes for the same PDF
DEFAULT_MAX_CHARS = 1200


class ReembedRequired(RuntimeError):
    """Stored chunks changed text or model; rerun with --reembed changed (or all)."""


@dataclass
class BuildReport:
    status: str                      # built | updated | unchanged
    index_dir: str
    mode: str
    chunks_total: int = 0
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    reembedded: list[str] = field(default_factory=list)
    embedded: int = 0
    embed_seconds: float = 0.0
    total_seconds: float = 0.0

    @property
    def chunks_per_second(self) -> float:
        return round(self.embedded / self.embed_seconds, 2) if self.embed_seconds > 0 else 0.0

    def summary(self) -> dict:
        out = asdict(self)
        for key in ("added", "removed", "reembedded"):
            out[key] = len(out[key])
        out["chunks_per_second"] = self.chunks_per_second
        return out


def max_chars_from_env() -> int:
    raw = os.environ.get("CHUNK_MAX_CHARS", "").split("#", 1)[0].strip()
    return int(raw) if raw else DEFAULT_MAX_CHARS


def chunk_corpus(docs: list[Document], corpus_dir: Path, max_chars: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in docs:
        if not doc.has_text_layer:
            raise ValueError(f"{doc.filename} has no text layer on most pages; OCR it before indexing (spec §3)")
        chunks += chunk_document(doc.regulation, page_texts(corpus_dir / doc.filename), doc_version=doc.doc_version,
                                 source_file=doc.filename, max_chars=max_chars)
    for i, c in enumerate(chunks):
        c.order = i
    ids = [c.passage_id for c in chunks]
    if len(ids) != len(set(ids)):
        raise AssertionError("duplicate passage ids across documents")
    return chunks


def _index_version(chunks: list[Chunk], alias: str) -> str:
    h = hashlib.sha256(alias.encode())
    for c in sorted(chunks, key=lambda c: c.passage_id):
        h.update(f"\n{c.passage_id}\t{c.text_hash()}".encode())
    return h.hexdigest()[:16]


def _metadata(c: Chunk) -> dict:
    return {"passage_id": c.passage_id, "regulation": c.regulation, "clause_id": c.clause_id, "status": c.status}


def _passages_bytes(chunks: list[Chunk]) -> str:
    return "".join(json.dumps(c.to_json(), ensure_ascii=False) + "\n" for c in chunks)


def _triggers_source(corpus_dir: Path) -> Path | None:
    for candidate in (corpus_dir / TRIGGERS, corpus_dir.parent / TRIGGERS):
        if candidate.exists():
            return candidate
    return None


def build_index(corpus_dir: Path, out_dir: Path, *, reembed: str = "none", embeddings=None,
                model_alias: str | None = None, max_chars: int | None = None) -> BuildReport:
    t_start = time.perf_counter()
    corpus_dir, out_dir = Path(corpus_dir), Path(out_dir)
    if reembed not in ("none", "changed", "all"):
        raise ValueError(f"unknown reembed mode {reembed!r}")
    docs = scan(corpus_dir)
    if not docs:
        raise ValueError(f"no PDFs in {corpus_dir}")
    max_chars = max_chars or max_chars_from_env()
    chunks = chunk_corpus(docs, corpus_dir, max_chars)
    alias = model_alias or embedding_alias()
    current = {c.passage_id: c for c in chunks}

    out_dir.mkdir(parents=True, exist_ok=True)
    table: dict[str, dict] = read_json(out_dir / CHUNK_TABLE, {}) or {}
    have_store = (out_dir / f"{FAISS_NAME}.faiss").exists() and bool(table)
    rebuild = reembed == "all" or not have_store

    report = BuildReport(status="built" if rebuild else "updated", index_dir=str(out_dir), mode=reembed,
                         chunks_total=len(chunks))
    if rebuild:
        to_embed = list(chunks)
        delete_ids: list[str] = []
        report.added = [c.passage_id for c in chunks]
    else:
        report.added = [pid for pid in current if pid not in table]
        report.removed = [pid for pid in table if pid not in current]
        changed = [pid for pid, c in current.items() if pid in table
                   and (table[pid].get("text_hash") != c.text_hash() or table[pid].get("model_alias") != alias)]
        if changed and reembed == "none":
            raise ReembedRequired(f"{len(changed)} stored chunk(s) changed text or embedding model "
                                  f"(e.g. {changed[0]}); rerun with --reembed changed")
        report.reembedded = changed
        to_embed = [current[pid] for pid in report.added + changed]
        delete_ids = report.removed + changed
        if any(v.get("model_alias") != alias for v in table.values()):
            # a new model may have a new vector size: the old FAISS index cannot hold its vectors
            rebuild, to_embed, delete_ids = True, list(chunks), []

    triggers_src = _triggers_source(corpus_dir)
    triggers_dst = out_dir / TRIGGERS
    triggers_changed = bool(triggers_src) and (
        not triggers_dst.exists() or triggers_src.read_bytes() != triggers_dst.read_bytes())
    passages_path = out_dir / PASSAGES
    passages_changed = not passages_path.exists() or \
        passages_path.read_text(encoding="utf-8") != _passages_bytes(chunks)

    if not rebuild and not to_embed and not delete_ids and not passages_changed and not triggers_changed:
        report.status = "unchanged"
        report.total_seconds = round(time.perf_counter() - t_start, 3)
        return report

    emb = embeddings or get_embeddings(alias)
    vectors: list[list[float]] = []
    if to_embed:
        t0 = time.perf_counter()
        vectors = emb.embed_documents([c.embed_text for c in to_embed])
        report.embed_seconds = round(time.perf_counter() - t0, 3)
        report.embedded = len(to_embed)

    if rebuild or to_embed or delete_ids:
        _write_store(out_dir, emb, to_embed, vectors, delete_ids, rebuild)
    write_passages(out_dir, chunks)
    if triggers_changed:
        shutil.copyfile(triggers_src, triggers_dst)

    new_table = dict(table) if not rebuild else {}
    for pid in report.removed:
        new_table.pop(pid, None)
    for c in to_embed:
        new_table[c.passage_id] = {"text_hash": c.text_hash(), "model_alias": alias}
    write_json(out_dir / CHUNK_TABLE, dict(sorted(new_table.items())))

    report.total_seconds = round(time.perf_counter() - t_start, 3)
    old = read_json(out_dir / MANIFEST, {}) or {}
    write_json(out_dir / MANIFEST, _manifest(docs, chunks, alias, vectors, old, report, max_chars))
    return report


def _write_store(out_dir: Path, emb, to_embed: list[Chunk], vectors: list[list[float]],
                 delete_ids: list[str], rebuild: bool) -> None:
    from langchain_community.vectorstores import FAISS

    pairs = [(c.embed_text, v) for c, v in zip(to_embed, vectors)]
    metas = [_metadata(c) for c in to_embed]
    ids = [c.passage_id for c in to_embed]
    if rebuild:
        store = FAISS.from_embeddings(pairs, emb, metadatas=metas, ids=ids)
    else:
        store = FAISS.load_local(str(out_dir), emb, index_name=FAISS_NAME, allow_dangerous_deserialization=True)
        if delete_ids:
            store.delete(delete_ids)
        if pairs:
            store.add_embeddings(pairs, metadatas=metas, ids=ids)
    # save next to the index, then swap the files in, so a reader never loads half a store
    with tempfile.TemporaryDirectory(dir=out_dir) as tmp:
        store.save_local(tmp, index_name=FAISS_NAME)
        for suffix in (".faiss", ".pkl"):
            os.replace(Path(tmp) / f"{FAISS_NAME}{suffix}", out_dir / f"{FAISS_NAME}{suffix}")


def _manifest(docs: list[Document], chunks: list[Chunk], alias: str, vectors: list[list[float]], old: dict,
              report: BuildReport, max_chars: int) -> dict:
    by_doc: dict[str, int] = {}
    for c in chunks:
        by_doc[c.source_file] = by_doc.get(c.source_file, 0) + 1
    in_force = sum(1 for c in chunks if c.in_force)
    throughput = old.get("throughput", {})
    if report.embedded:
        throughput = {"chunks_embedded": report.embedded, "embed_seconds": report.embed_seconds,
                      "chunks_per_second": report.chunks_per_second,
                      "pipeline_chunks_per_second": round(len(chunks) / report.total_seconds, 2)
                      if report.total_seconds else 0.0,
                      "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "index_version": _index_version(chunks, alias),
        "embedding_model": alias,
        "dimension": len(vectors[0]) if vectors else old.get("dimension"),
        "normalized": True,
        "chunker": {"version": CHUNKER_VERSION, "max_chars": max_chars},
        "documents": [{**asdict(d), "doc_version": d.doc_version, "chunks": by_doc.get(d.filename, 0)}
                      for d in docs],
        "chunks": {"total": len(chunks), "in_force": in_force, "superseded": len(chunks) - in_force,
                   "by_regulation": {r: sum(1 for c in chunks if c.regulation == r)
                                     for r in sorted({c.regulation for c in chunks})}},
        "throughput": throughput,
        "last_run": report.summary(),
    }
