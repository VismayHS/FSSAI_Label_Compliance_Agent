"""The on-disk index format, shared by the builder (fssai_ingest) and the reader (FaissRetriever).

One folder (INDEX_DIR) holds:

    index.faiss, index.pkl   LangChain FAISS store: one vector per chunk, docstore id = passage_id
    passages.jsonl           every chunk with its metadata, in-force and superseded (decision 002)
    chunk_table.json         passage_id -> {text_hash, model_alias}: what each vector was made from
    index_manifest.json      freshness (D2): built_at, document versions, chunk counts, model, throughput
    claim_triggers.yaml      optional retrieval hints copied from corpus/ (decision 002, extras)

The writer replaces each file atomically, so a reader never sees half an index.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from fssai_contracts.schemas import Passage, Regulation

FAISS_NAME = "index"  # LangChain writes index.faiss + index.pkl
PASSAGES = "passages.jsonl"
CHUNK_TABLE = "chunk_table.json"
MANIFEST = "index_manifest.json"
TRIGGERS = "claim_triggers.yaml"

HASHING_ALIAS_PREFIX = "hashing"  # EMBEDDING_MODEL=hashing or hashing-<dim>: offline, deterministic (tests)


class IndexNotBuilt(FileNotFoundError):
    """INDEX_DIR has no index. Build it: python -m fssai_ingest build --corpus corpus/raw --out <INDEX_DIR>."""


@dataclass
class Chunk:
    """One retrievable unit. `text` is verbatim document text (citations quote it); `embed_text`
    adds the context header that is embedded but never quoted."""
    passage_id: str
    regulation: str
    clause_id: str
    heading_path: list[str]
    text: str
    doc_version: str
    page: int
    order: int
    status: str = "in_force"          # in_force | superseded
    amendment: str | None = None      # substituted | inserted | partial | None (original text)
    effective: str | None = None      # e.g. "Operationalized w.e.f. 26th October, 2021 ..."
    source_file: str = ""
    embed_text: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def in_force(self) -> bool:
        return self.status == "in_force"

    def text_hash(self) -> str:
        return hashlib.sha256(self.embed_text.encode("utf-8")).hexdigest()

    def to_passage(self, score: float | None = None) -> Passage:
        return Passage(passage_id=self.passage_id, regulation=Regulation(self.regulation),
                       clause_id=self.clause_id, heading_path=list(self.heading_path), text=self.text,
                       doc_version=self.doc_version, score=score)

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> Chunk:
        return cls(**data)


# ------------------------------------------------------------------ clause ids

_ROMAN_SCHEDULE = re.compile(r"schedule\s*[-–]?\s*([ivx]+a?)\b")


def normalise_clause_id(clause_id: str) -> str:
    """Spacing, bracket and wording variants of one clause id compare equal:
    "5 (3)(c)" == "5(3)(c)", "Schedule-I item 11" == "Schedule I, item 11", "reg. 5(3)" == "5(3)"."""
    s = clause_id.lower().strip()
    s = s.replace("[", "(").replace("{", "(").replace("]", ")").replace("}", ")")
    s = re.sub(r"^\s*(regulation|reg\.?|sub-regulation|clause)\s*", "", s)
    s = _ROMAN_SCHEDULE.sub(lambda m: f"schedule {m.group(1)}", s)
    s = re.sub(r"\b(item\s*no\.?|sl\.?\s*no\.?|si\.?\s*no\.?|s\.?\s*no\.?|item|row|entry)\s*", "item ", s)
    s = re.sub(r"[\s,;:]+", " ", s).strip()
    s = re.sub(r"\s*\(\s*", "(", s)
    s = re.sub(r"\s*\)", ")", s)
    return s


def clause_contains(ancestor: str, clause: str) -> bool:
    """True if `clause` is `ancestor` or one of its sub-clauses ("5(3)" contains "5(3)(c)(i)")."""
    a, c = normalise_clause_id(ancestor), normalise_clause_id(clause)
    return c == a or c.startswith(a + "(") or c.startswith(a + " ")


# ------------------------------------------------------------------ files

def _atomic_write(path: Path, data: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(data, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def write_json(path: Path, data: object) -> None:
    _atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n")


def read_json(path: Path, default: object = None) -> object:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_passages(index_dir: Path, chunks: list[Chunk]) -> None:
    _atomic_write(index_dir / PASSAGES,
                  "".join(json.dumps(c.to_json(), ensure_ascii=False) + "\n" for c in chunks))


def read_passages(index_dir: Path) -> list[Chunk]:
    path = index_dir / PASSAGES
    if not path.exists():
        raise IndexNotBuilt(f"no {PASSAGES} in {index_dir}: build the index first "
                            f"(python -m fssai_ingest build --corpus corpus/raw --out {index_dir})")
    with path.open(encoding="utf-8") as fh:
        return [Chunk.from_json(json.loads(line)) for line in fh if line.strip()]


def index_version(manifest: dict | None) -> str:
    """Changes whenever any vector or chunk changes, so cache keys built on it go stale on rebuild (D7)."""
    return (manifest or {}).get("index_version", "none")


# ------------------------------------------------------------------ embeddings

try:
    from langchain_core.embeddings import Embeddings as _EmbeddingsBase
except ImportError:  # pragma: no cover - langchain-core is a dependency; this only keeps the module importable
    _EmbeddingsBase = object


class HashingEmbeddings(_EmbeddingsBase):
    """Feature-hashed bag of words + character trigrams, L2-normalised. No model download, deterministic.

    For tests and offline smoke runs only (EMBEDDING_MODEL=hashing). It is a lexical model with a
    dense interface, so it says nothing about semantic recall; the report numbers use the real model.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        words = re.findall(r"[a-z0-9]+", text.lower())
        feats = words + [f"{a}_{b}" for a, b in zip(words, words[1:])]
        for w in words:
            padded = f"#{w}#"
            feats += [padded[i:i + 3] for i in range(len(padded) - 2)]
        for f in feats:
            h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "big")
            vec[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


def embedding_alias() -> str:
    alias = os.environ.get("EMBEDDING_MODEL", "").split("#", 1)[0].strip()
    if not alias:
        raise RuntimeError("EMBEDDING_MODEL is not set. Put a local sentence-transformers model name in .env "
                           "(spec §12 suggests a small MiniLM-class model), or EMBEDDING_MODEL=hashing for an "
                           "offline lexical stand-in.")
    return alias


def get_embeddings(alias: str | None = None):
    """A LangChain Embeddings object for `alias` (default: EMBEDDING_MODEL). Vectors are L2-normalised,
    so the index's L2 distance ranks exactly like cosine similarity."""
    alias = alias or embedding_alias()
    if alias.startswith(HASHING_ALIAS_PREFIX):
        _, _, dim = alias.partition("-")
        return HashingEmbeddings(int(dim) if dim else 384)
    from langchain_huggingface import HuggingFaceEmbeddings  # heavy import: torch

    device = os.environ.get("EMBEDDING_DEVICE", "").strip() or "cpu"
    return HuggingFaceEmbeddings(model_name=alias, model_kwargs={"device": device},
                                 encode_kwargs={"normalize_embeddings": True, "batch_size": 32})


def l2_to_similarity(distance: float) -> float:
    """LangChain FAISS returns squared L2 distance; for unit vectors cos = 1 - d²/2."""
    return 1.0 - float(distance) / 2.0
