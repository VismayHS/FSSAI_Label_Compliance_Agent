# Evaluation 1: project plan

Owner: Vismay (S1.3), assembled from the team's own documents; each section links its source, which stays
the authority. Status as of **2026-10-25**. Sections marked *pending* fill in as their owners merge.

## 1. Problem and scope
We check a proposed packaged-food label (as text) and its package specification against two FSSAI
regulations, the **Labelling & Display Regulations 2020** (`FSS-LD-2020`) and the **Advertising & Claims
Regulations 2018** (`FSS-AC-2018`), and return a finding per requirement with citations, routed to
`clear-for-print`, `revise-and-recheck` or `regulatory-review`. The system never approves a label.

The obstacle the course names for this project: a claim condition lives in a different regulation from
the labelling rules, and the Labelling text never points to it. A single embedding search does not find
it; the agent must look for the modifying provision, search again from what it read, and verify that the
passages support the answer (spec §5). Escalating is always better than inventing.

Out of scope: model training, cloud deployment, label images. Source: [LLM_Context §2](../../contexts/LLM_Context.md).

## 2. Corpus and product category
- **Corpus:** both regulations as the official FSSAI compendia, `FSS-AC-2018` Version-II (16.11.2021) and
  `FSS-LD-2020` Version-VI (22.02.2023), with provenance and sha256 in `corpus/manifest.json`
  ([decision 004](../decisions/004-nishkal-corpus-versions.md)).
- **Category:** breakfast cereals; health supplements out of scope
  ([decision 001](../decisions/001-nishkal-product-category.md), *proposed*: the team confirms it in the group chat).

## 3. The §4.1 reference case
Full passages, pages and passage ids: [section-4.1-passages.md](section-4.1-passages.md) (Nishkal). In short:
"source of protein" is a nutrient content claim (FSS-AC-2018 2(1)(l)(i)); by regulation 5(3) it must meet
**Schedule I, item 11**, a share of the **RDA** (10 % of RDA per 100 g for solids). The protein figure comes
from the nutrition panel that FSS-LD-2020 5(3)(b) requires, and the Labelling text never mentions Schedule I.

**Open question for the team:** neither regulation states an RDA value for protein; both refer to ICMR.
The reference answer needs a team decision on how the system treats that (the options are in the passages
file) before the test values are final.

Test values: *pending* (Vihaan, `section-4.1-test-values.md`, V1.3).

## 4. Architecture and deployment boundaries
Diagram and boundary table: [docs/architecture.md](../architecture.md); why each service is separate:
[decision 304](../decisions/304-vismay-deployment-boundaries.md). The system runs from a clean clone with
`cp .env.example .env` and `docker compose up -d --build`: web, API, worker (scalable), Redis, Postgres,
indexer, stub LLM, Prometheus, Grafana, Jaeger, cAdvisor. Async model: 202 + run id, the client polls
([decision 301](../decisions/301-vismay-async-polling.md)); queue: RQ on Redis ([decision 302](../decisions/302-vismay-queue-rq.md)).

## 5. Agent topology
Three agents with their own prompts, tools and state, joined only by the hand-off schemas in
`contracts/fssai_contracts/schemas.py`; guardrails and the router are deterministic steps around them:

| Agent | Owner | Input → output | Tools |
|---|---|---|---|
| Classifier | Namith | `LabelCheckRequest` → `Classification` | request field lookup |
| Researcher | Namith | `Classification` → `ResearchDossier` | `corpus_search`, `clause_lookup`, `request_field_lookup` |
| Verifier | Vihaan | `ResearchDossier` → `Verdict` | `resolve_citation`, `clause_lookup` |

Order and edge behaviour: `guardrails → classifier → (researcher → verifier) × ≤3 → router → output filter`
(`contracts/fssai_contracts/pipeline.py`). Mid-run failure handling and the LangGraph design: *pending*
(Namith, `docs/agent-topology.md`, M1.3).

## 6. Data contract
Request shape: `LabelCheckRequest` (published at `/docs` as OpenAPI). Every reject is quarantined with
field-level errors, and no run is created (demo #4, verified by `scripts/smoke.py`). Published contract with
ranges and cross-field rules: *pending* (Vihaan, `docs/data-contract.md`, V1.1).

## 7. SLO (declared before measuring)
**p95 of complete-run latency ≤ 60 s with 5 runs in flight**, LLM replaced by the stub (mean 1.5 s, p95 4 s),
one worker; **≤ 1 % of runs fail**. Declared 2026-10-25 in [loadtest/SLO.md](../../loadtest/SLO.md)
(Nishkal), before any load test.

## 8. Owners and requirements
Every F, A, L and D requirement has one primary owner: [LLM_Context §3](../../contexts/LLM_Context.md).
Each person's tasks, status and prompts: `contexts/<Name>.md`. Work is integrated by switching `IMPL_*`
variables, and every seam has a conformance check (`contracts/fssai_contracts/conformance.py`) that defines
"done" the same way for everybody.

## 9. Status

| Part | Owner | State |
|---|---|---|
| API, queue, workers, Postgres run store, LLM gateway (timeouts, retry, shared breaker, cost) | Vismay | built; on `main` after the next PR |
| Compose stack, smoke test, clean-clone test, CI, breaker demo, cost report + dashboard | Vismay | built and verified on 2026-10-25 |
| Web client | Vismay | built; feedback buttons appear when Vihaan's endpoint lands |
| Corpus, chunking, index, hybrid retriever, cache, observability stack, stub LLM, load-test tooling | Nishkal | built; real retriever verified in the Compose stack |
| Prompts, classifier, researcher, LangGraph pipeline, guardrails | Namith | skeletons ready, not started |
| Gate, verifier, router, eval set, feedback, quarantine endpoint | Vihaan | skeletons ready, not started |

## 10. Plan
Phases and milestones: [LLM_Context §9](../../contexts/LLM_Context.md) (dates to be filled in once announced).
Next, in order: confirm decision 001 and the RDA question; Namith's classifier and researcher and Vihaan's
gate and verifier behind their conformance tests; the §4.1 case on the real stack by the end of week 2;
then Nishkal's load test against the SLO, guardrails, the eval set and its before/after comparison.

## 11. Risks

| Risk | Mitigation |
|---|---|
| `docker compose up` fails at the demo (zero marks) | CI boots the stack and runs the smoke test on every PR into `main`; `scripts/clean_clone_test.py` before every rehearsal |
| The agent misses the claim condition in the other regulation | Claim-trigger hints in retrieval (decision 002), the researcher's modifying-provision step, the §4.1 case in the eval set |
| A finding cites text that wasn't retrieved | The verifier resolves every citation verbatim; unverified answers go to `regulatory-review` |
| Free-tier rate limits or outages | Gateway retries with backoff, a shared circuit breaker, a fallback model, `complete=false` with an honest reason |
| No protein RDA value in the corpus | Team decision recorded before the test values are final; the system escalates rather than inventing a number |
