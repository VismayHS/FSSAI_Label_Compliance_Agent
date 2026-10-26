# Report sections

Each owner writes their own section (LLM_Context §10). `python scripts/build_report.py` (or `make report`) assembles
them, with the decision records and the incidents, into `REPORT.md`. Edit the sections, never `REPORT.md`.

| Section | Covers | Owner |
|---|---|---|
| [`platform-and-integration.md`](platform-and-integration.md) | Problem and scope, architecture and deployment boundaries, async and reliability design, cost per 100 runs | Vismay |
| [`agent-design.md`](agent-design.md) | Topology, tools, loop limits, guardrails, prompt comparison | Namith |
| `verification-and-evaluation.md` | Verification design, data contract, evaluation before and after, feedback | Vihaan |
| [`retrieval-and-performance.md`](retrieval-and-performance.md) | Chunking and embeddings, p95 target and results, bottleneck, caching effect | Nishkal |

Design decisions and what was rejected come from [`../decisions/`](../decisions/); what did not work comes from
[`../incidents/`](../incidents/).
