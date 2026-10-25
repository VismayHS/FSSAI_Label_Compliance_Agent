"""The corpus folder: which PDFs exist, which regulation and version each one is, and its fingerprint.

Provenance is hand-maintained in corpus/sources.yaml (next to corpus/raw/); everything measurable
(sha256, pages, text layer) is computed. corpus/manifest.json is the committed result (N0.2).
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml
from pypdf import PdfReader

from .pdftext import has_text_layer, page_texts

SOURCES_NAME = "sources.yaml"


@dataclass
class Document:
    filename: str
    regulation: str
    title: str
    version_label: str
    version_date: str
    sha256: str
    page_count: int
    has_text_layer: bool
    source_url: str
    retrieved_via: str = ""
    retrieved_on: str = ""
    principal_notification: str = ""

    @property
    def doc_version(self) -> str:
        """What every Passage.doc_version says, e.g. "Version-II (2021-11-16)"."""
        return f"{self.version_label} ({self.version_date})".strip()


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def find_sources(corpus_dir: Path) -> Path | None:
    for candidate in (corpus_dir / SOURCES_NAME, corpus_dir.parent / SOURCES_NAME):
        if candidate.exists():
            return candidate
    return None


def load_sources(corpus_dir: Path) -> dict[str, dict]:
    path = find_sources(corpus_dir)
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path else {}


def _pdf_title(path: Path, pages: list[str]) -> str:
    meta = PdfReader(str(path)).metadata
    if meta and meta.title:
        return str(meta.title)
    for line in (pages[0] if pages else "").splitlines():
        if len(line.strip()) > 20 and "version" not in line.lower():
            return line.strip()
    return path.stem


def scan(corpus_dir: Path) -> list[Document]:
    """Every PDF in corpus_dir, sorted by name. A PDF missing from sources.yaml is an error: an
    unattributed document must not reach the index (we could not cite its regulation or version)."""
    sources = load_sources(corpus_dir)
    docs = []
    for path in sorted(corpus_dir.glob("*.pdf")):
        src = sources.get(path.name)
        if not src or not src.get("regulation"):
            raise ValueError(f"{path.name} has no entry with a `regulation` in {SOURCES_NAME}; add its provenance first")
        pages = page_texts(path)
        docs.append(Document(
            filename=path.name, regulation=src["regulation"], title=src.get("title") or _pdf_title(path, pages),
            version_label=str(src.get("version_label", "")), version_date=str(src.get("version_date", "")),
            sha256=sha256_of(path), page_count=len(pages), has_text_layer=has_text_layer(pages),
            source_url=src.get("source_url", ""), retrieved_via=src.get("retrieved_via", ""),
            retrieved_on=str(src.get("retrieved_on", "")),
            principal_notification=src.get("principal_notification", "")))
    return docs


def manifest(docs: list[Document]) -> dict:
    return {"documents": [asdict(d) for d in docs]}
