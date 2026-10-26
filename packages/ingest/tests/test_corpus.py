"""Corpus scanning and the manifest (N0.2), with a tiny PDF generated in the test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fssai_ingest.__main__ import main
from fssai_ingest.corpus import scan, sha256_of


def tiny_pdf(text: str) -> bytes:
    """A valid one-page PDF with a text layer, written by hand (no PDF library needed to make it)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for n, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


@pytest.fixture()
def corpus(tmp_path) -> Path:
    raw = tmp_path / "corpus" / "raw"
    raw.mkdir(parents=True)
    (raw / "claims.pdf").write_bytes(tiny_pdf("1. Short title. These regulations are about claims and labels."))
    (tmp_path / "corpus" / "sources.yaml").write_text(
        "claims.pdf:\n  regulation: FSS-AC-2018\n  title: Test claims\n  version_label: V-I\n"
        "  version_date: '2021-11-16'\n  source_url: https://example.invalid/claims.pdf\n", encoding="utf-8")
    return raw


def test_scan_reads_provenance_and_measures_the_file(corpus):
    (doc,) = scan(corpus)
    assert doc.regulation == "FSS-AC-2018" and doc.title == "Test claims" and doc.page_count == 1
    assert doc.has_text_layer and doc.sha256 == sha256_of(corpus / "claims.pdf")
    assert doc.doc_version == "V-I (2021-11-16)"


def test_unattributed_pdf_is_refused(corpus):
    (corpus / "mystery.pdf").write_bytes(tiny_pdf("Some regulation text that nobody recorded anywhere."))
    with pytest.raises(ValueError, match="mystery.pdf"):
        scan(corpus)


def test_manifest_cli_is_idempotent(corpus, capsys):
    assert main(["manifest", "--corpus", str(corpus)]) == 0
    out = corpus.parent / "manifest.json"
    first = out.stat().st_mtime_ns
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["documents"][0]["source_url"] == "https://example.invalid/claims.pdf"
    assert main(["manifest", "--corpus", str(corpus)]) == 0
    assert out.stat().st_mtime_ns == first
    assert "FSS-AC-2018" in capsys.readouterr().out


def test_committed_manifest_matches_the_corpus():
    """data/corpus/manifest.json must describe exactly the PDFs committed in data/corpus/raw (rerun the tool if not)."""
    root = Path(__file__).resolve().parents[3] / "data" / "corpus"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    on_disk = {p.name: sha256_of(p) for p in (root / "raw").glob("*.pdf")}
    assert {d["filename"]: d["sha256"] for d in manifest["documents"]} == on_disk
