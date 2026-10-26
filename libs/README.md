# libs: the components

Each folder is its own Python package with its own `pyproject.toml` and tests. A package implements one or more
seams from `contracts/` and is switched on with an `IMPL_*` variable in `.env`. Nothing imports a teammate's
classes directly.

| Package | Implements | Switch | Owner |
|---|---|---|---|
| [`ingest/`](ingest/) | CLI that builds the search index: parse, chunk, embed, index (D2) | run by the `indexer` service | Nishkal |
| [`retrieval/`](retrieval/) | `Retriever`: hybrid FAISS + BM25 search, clause lookup, cache | `IMPL_RETRIEVER` | Nishkal |
| [`observability/`](observability/) | JSON logs, OpenTelemetry setup, metric helpers | imported by each service | Nishkal |
| [`prompts/`](prompts/) | `PromptStore`: versioned prompt files | `IMPL_PROMPTS` | Namith |
| [`agents/`](agents/) | `Classifier`, `Researcher`, `Pipeline` (LangGraph) | `IMPL_CLASSIFIER`, `IMPL_RESEARCHER`, `IMPL_PIPELINE` | Namith |
| [`guardrails/`](guardrails/) | `Guardrails`: prompt-injection screening, output filter | `IMPL_GUARDRAILS` | Namith |
| [`gate/`](gate/) | `RequestGate`: rate limit, validation, quarantine | `IMPL_GATE` | Vihaan |
| [`verification/`](verification/) | `Verifier` (an agent) and `Router` | `IMPL_VERIFIER`, `IMPL_ROUTER` | Vihaan |
| [`llm_gateway/`](llm_gateway/) | `LLMClient`: retries, circuit breaker, fallback, cost | `IMPL_LLM` | Vismay |
| [`run_store/`](run_store/) | `RunStore` in Postgres: runs and step traces | `IMPL_RUN_STORE` (set by Compose) | Vismay |

Run every package's tests with `python scripts/test_all.py`.
