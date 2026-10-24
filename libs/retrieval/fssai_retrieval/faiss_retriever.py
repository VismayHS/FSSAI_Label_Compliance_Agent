"""FaissRetriever: the real Retriever (contexts/Nishkal.md N2.2). Day-0 skeleton: keep the names and signatures.

What it must do (interface: fssai_contracts.interfaces.Retriever; checked by conformance.check_retriever):
- search(query, ctx, k, regulation): the top-k Passages with scores from the index in INDEX_DIR. With
  `regulation` set, over-fetch then keep only that regulation, so the filter never starves k.
- get_clause(regulation, clause_id, ctx): exact metadata lookup (normalise spacing and brackets), None if absent.
- Record no steps: the agent records the tool step with the passages it got back (LLM_Context §6.4).
- Passage metadata comes from the chunker (decision 002): regulation, clause_id, heading_path, doc_version.

Switch on: IMPL_RETRIEVER=fssai_retrieval.faiss_retriever:FaissRetriever
"""
from __future__ import annotations

import os
from pathlib import Path

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import Passage, Regulation


class FaissRetriever:
    def __init__(self, index_dir: Path) -> None:
        self.index_dir = index_dir

    @classmethod
    def from_registry(cls) -> FaissRetriever:
        return cls(Path(os.environ.get("INDEX_DIR", "/data/index")))

    def search(self, query: str, ctx: RunContext, *, k: int = 5,
               regulation: Regulation | None = None) -> list[Passage]:
        raise NotImplementedError("N2.2: search the FAISS index that fssai_ingest builds (N2.1)")

    def get_clause(self, regulation: Regulation, clause_id: str, ctx: RunContext) -> Passage | None:
        raise NotImplementedError("N2.2: exact lookup on (regulation, clause_id)")
