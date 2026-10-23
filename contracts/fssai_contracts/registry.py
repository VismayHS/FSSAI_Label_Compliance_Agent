"""The switchboard: picks a fake or real implementation per seam from the environment.

    IMPL_RETRIEVER=fssai_retrieval.faiss_retriever:FaissRetriever

Unset or empty -> the fake below. Swapping in your real implementation is an
.env change, never an edit to somebody else's code.

Construction: if the class has a `from_registry()` classmethod it is used (so it
can `build()` its own dependencies), otherwise the class is called with no args.
"""
from __future__ import annotations

import importlib
import os

DEFAULTS: dict[str, str] = {
    "gate": "fssai_contracts.fakes:FakeRequestGate",
    "retriever": "fssai_contracts.fakes:FakeRetriever",
    "llm": "fssai_contracts.fakes:FakeLLM",
    "prompts": "fssai_contracts.fakes:FakePromptStore",
    "guardrails": "fssai_contracts.fakes:FakeGuardrails",
    "classifier": "fssai_contracts.fakes:FakeClassifier",
    "researcher": "fssai_contracts.fakes:FakeResearcher",
    "verifier": "fssai_contracts.fakes:FakeVerifier",
    "router": "fssai_contracts.fakes:FakeRouter",
    "pipeline": "fssai_contracts.pipeline:ReferencePipeline",
    "run_store": "fssai_contracts.fakes:InMemoryRunStore",
}


def resolve(name: str) -> type:
    # Tolerate inline "# comment" text from naive .env loaders.
    path = os.environ.get(f"IMPL_{name.upper()}", "").split("#", 1)[0].strip() or DEFAULTS[name]
    module, _, attr = path.partition(":")
    return getattr(importlib.import_module(module), attr)


def build(name: str):
    cls = resolve(name)
    factory = getattr(cls, "from_registry", None)
    return factory() if callable(factory) else cls()
