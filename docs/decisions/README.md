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
| [301](301-vismay-async-polling.md) | Async runs: 202 + run id, the client polls; callback later as an extra | Vismay | Accepted |
| [302](302-vismay-queue-rq.md) | Queue: RQ on Redis with in-process `SimpleWorker`s; inline mode for local development | Vismay | Accepted |
| [303](303-vismay-web-client-stack.md) | Web client: React + Vite + TypeScript, plain CSS tokens, React Bits for state | Vismay | Accepted |
| [304](304-vismay-deployment-boundaries.md) | Deployment boundaries: a Compose service per scaling, failure and release profile | Vismay | Accepted |
