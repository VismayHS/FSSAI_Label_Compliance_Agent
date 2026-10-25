"""The index build (D2, L1): idempotent, partial re-embed, freshness manifest. Uses the real corpus with
the offline hashing embedder, so it needs no model download."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from fssai_ingest import build as build_mod
from fssai_ingest.__main__ import main
from fssai_ingest.build import ReembedRequired, build_index
from fssai_retrieval.index import CHUNK_TABLE, MANIFEST, PASSAGES, TRIGGERS, HashingEmbeddings

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "corpus" / "raw"

pytestmark = pytest.mark.skipif(not any(CORPUS.glob("*.pdf")), reason="corpus PDFs missing")


class CountingEmbeddings(HashingEmbeddings):
    def __init__(self) -> None:
        super().__init__()
        self.embedded: list[str] = []

    def embed_documents(self, texts):
        self.embedded += texts
        return super().embed_documents(texts)


def _ntotal(out: Path) -> int:
    import faiss

    return faiss.read_index(str(out / "index.faiss")).ntotal


def _mtimes(out: Path) -> dict[str, int]:
    return {p.name: p.stat().st_mtime_ns for p in out.iterdir()}


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("built")
    build_index(CORPUS, out, model_alias="hashing")
    return out


def test_first_build_writes_everything(built):
    for name in (PASSAGES, CHUNK_TABLE, MANIFEST, TRIGGERS, "index.faiss", "index.pkl"):
        assert (built / name).exists(), name
    manifest = json.loads((built / MANIFEST).read_text(encoding="utf-8"))
    assert manifest["chunks"]["total"] == _ntotal(built) == len(json.loads((built / CHUNK_TABLE).read_text()))
    assert {d["regulation"] for d in manifest["documents"]} == {"FSS-AC-2018", "FSS-LD-2020"}
    assert all(len(d["sha256"]) == 64 and d["has_text_layer"] for d in manifest["documents"])
    assert manifest["throughput"]["chunks_per_second"] > 0 and manifest["built_at"]
    assert manifest["embedding_model"] == "hashing" and manifest["dimension"] == 384


def test_rerun_with_no_changes_does_nothing(built, tmp_path):
    out = tmp_path / "idx"
    shutil.copytree(built, out)
    before = _mtimes(out)
    emb = CountingEmbeddings()
    report = build_index(CORPUS, out, model_alias="hashing", embeddings=emb)
    assert report.status == "unchanged" and emb.embedded == []
    assert _mtimes(out) == before  # not even built_at is rewritten


def test_changed_text_reembeds_only_that_chunk(built, tmp_path, monkeypatch):
    out = tmp_path / "idx"
    shutil.copytree(built, out)
    real = build_mod.chunk_corpus
    target = "FSS-AC-2018:Schedule I, item 11~substituted"

    def edited(*args, **kwargs):
        chunks = real(*args, **kwargs)
        for c in chunks:
            if c.passage_id == target:
                c.text += " (corrected)"
                c.embed_text += " (corrected)"
        return chunks

    monkeypatch.setattr(build_mod, "chunk_corpus", edited)
    with pytest.raises(ReembedRequired):
        build_index(CORPUS, out, model_alias="hashing", reembed="none")
    emb = CountingEmbeddings()
    report = build_index(CORPUS, out, model_alias="hashing", reembed="changed", embeddings=emb)
    assert report.status == "updated" and report.reembedded == [target] and len(emb.embedded) == 1
    assert _ntotal(out) == report.chunks_total  # replaced in place, not duplicated


def test_removed_chunk_is_deleted_from_the_index(built, tmp_path, monkeypatch):
    out = tmp_path / "idx"
    shutil.copytree(built, out)
    real = build_mod.chunk_corpus
    gone = "FSS-AC-2018:Schedule IV, item 5"
    monkeypatch.setattr(build_mod, "chunk_corpus",
                        lambda *a, **k: [c for c in real(*a, **k) if c.passage_id != gone])
    before = _ntotal(out)
    report = build_index(CORPUS, out, model_alias="hashing")
    assert report.removed == [gone] and _ntotal(out) == before - 1
    assert gone not in json.loads((out / CHUNK_TABLE).read_text())


def test_model_change_needs_reembed(built, tmp_path):
    out = tmp_path / "idx"
    shutil.copytree(built, out)
    with pytest.raises(ReembedRequired, match="--reembed changed"):
        build_index(CORPUS, out, model_alias="hashing-128")
    report = build_index(CORPUS, out, model_alias="hashing-128", reembed="changed")
    assert len(report.reembedded) == report.chunks_total
    assert json.loads((out / MANIFEST).read_text())["dimension"] == 128


def test_reembed_all_rebuilds(built, tmp_path):
    out = tmp_path / "idx"
    shutil.copytree(built, out)
    report = build_index(CORPUS, out, model_alias="hashing", reembed="all")
    assert report.status == "built" and report.embedded == report.chunks_total == _ntotal(out)


def test_cli_build_and_exit_code_for_required_reembed(built, tmp_path, monkeypatch, capsys):
    out = tmp_path / "idx"
    shutil.copytree(built, out)
    monkeypatch.setenv("EMBEDDING_MODEL", "hashing")
    assert main(["build", "--corpus", str(CORPUS), "--out", str(out)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "unchanged"
    monkeypatch.setenv("EMBEDDING_MODEL", "hashing-64")
    assert main(["build", "--corpus", str(CORPUS), "--out", str(out)]) == 3


def test_embedding_model_must_be_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="EMBEDDING_MODEL is not set"):
        build_index(CORPUS, tmp_path / "idx")
