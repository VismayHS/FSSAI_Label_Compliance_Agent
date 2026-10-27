# Decision records

One file per decision: `NNN-<name>-<slug>.md` with **Context, Options, Decision, Consequences**.
Number blocks keep parallel branches from clashing: Nishkal `001–099`, Namith `100–199`,
Vihaan `200–299`, Vismay `300–399`. Add your row here in the same PR as the record.

The report's "design decisions and what was rejected" section is written from these files.

| # | Decision | Owner | Status |
|---|---|---|---|
| [001](001-nishkal-product-category.md) | Product category: breakfast cereals; health supplements out of scope | Nishkal | Proposed |
| [002](002-nishkal-chunking.md) | Clause-aware chunking, local embeddings, hybrid retrieval with claim hints | Nishkal | Accepted |
| [003](003-nishkal-caching.md) | Cache query embeddings and retrieval results in Redis; no whole-run cache | Nishkal | Accepted |
| [004](004-nishkal-corpus-versions.md) | Corpus: FSSAI compendia, amended text in force, provenance in the manifest | Nishkal | Accepted |
| [201](201-vihaan-routing-rules.md) | Routing: ordered rules, most cautious first; claims never clear without the Claims regulation | Vihaan | Accepted |
| [202](202-vihaan-verifier-design.md) | Verifier: deterministic citation + numeric checks, one LLM support check, specific retry hints | Vihaan | Accepted |
| [203](203-vihaan-gate-boundary.md) | Gate: strict shape, unknown fields rejected, out-of-corpus categories accepted, fail-open rate limit | Vihaan | Accepted |
| [204](204-vihaan-eval-judges.md) | Eval: groundedness vs faithfulness defined apart; reference / LLM / TruLens judges; RAGAS rejected | Vihaan | Accepted |
| [205](205-vihaan-before-after-change.md) | Before/after experiment: researcher prompt 1.0.0 vs 1.1.0 | Vihaan | Proposed |
| [301](301-vismay-async-polling.md) | Async runs: 202 + run id, the client polls; callback later as an extra | Vismay | Accepted |
| [302](302-vismay-queue-rq.md) | Queue: RQ on Redis with in-process `SimpleWorker`s; inline mode for local development | Vismay | Accepted |
| [303](303-vismay-web-client-stack.md) | Web client: React + Vite + TypeScript, plain CSS tokens, React Bits for state | Vismay | Accepted |
| [304](304-vismay-deployment-boundaries.md) | Deployment boundaries: a Compose service per scaling, failure and release profile | Vismay | Accepted |
| [305](305-vismay-repository-layout.md) | Repository layout: six top-level folders by purpose (apps, packages, infra, data, docs, tools) | Vismay | Accepted |
