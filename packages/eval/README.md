# fssai_eval (`eval`)

The eval set, its runner and metrics (L3), live scoring and feedback tooling (L6). Metric definitions and the judge
choice: [decision 204](../../docs/decisions/204-vihaan-eval-judges.md) and
[`docs/report/verification-and-evaluation.md`](../../docs/report/verification-and-evaluation.md) §4.

**Owner:** Vihaan · tasks V1.4, V3.1–V3.4 and extras in [`docs/contexts/Vihaan.md`](../../docs/contexts/Vihaan.md).

```bash
<venv-python> -m pip install -e "packages/eval[test]"                 # + "packages/eval[trulens]" for --judge trulens
<venv-python> -m pytest packages/eval -q

# run the eval set through whatever IMPL_* selects (reads .env first; the shell wins)
<venv-python> -m fssai_eval run --scenarios packages/eval/scenarios.jsonl --tag baseline [--judge reference|llm|trulens]
<venv-python> -m fssai_eval compare baseline candidate        # before/after with deltas (V3.3)
<venv-python> -m fssai_eval gate --baseline baseline --candidate candidate   # exit 1 on regression (CI)

<venv-python> -m fssai_eval live --sample 10 [--every 300]    # score recent runs into quality_scores (L6)
<venv-python> -m fssai_eval candidates --days 7               # unsatisfactory feedback -> packages/eval/candidates.jsonl
<venv-python> -m fssai_eval calibrate template|score          # judge vs hand labels: agreement, Cohen's kappa

<venv-python> packages/eval/tools/check_scenarios.py --index <INDEX_DIR>   # every quote verbatim in the corpus, every request valid
<venv-python> packages/eval/tools/export_schema.py [--check]                # docs/data-contract.schema.json
<venv-python> packages/eval/tools/demo_trust.py --api http://localhost:8000 # rehearse demo items 4, 5, 6
```

| Path | What |
|---|---|
| `scenarios.jsonl` | 30 `EvalScenario`s (breakfast cereals): §4.1 variants, numeric claims, mandatory declarations, exemptions, out of scope, conflicts, claims without a condition, injection, traps |
| `fssai_eval/runner.py` | in-process runner, results files, `compare`, regression gate |
| `fssai_eval/metrics.py` | groundedness, context relevance, faithfulness, hallucination rate, route/finding accuracy; exact definitions in `DEFINITIONS` |
| `fssai_eval/judges.py` | `reference` (offline), `llm` (our judge prompts), `trulens` (TruLens feedback functions); disk cache |
| `fssai_eval/live.py` | live scorer → `quality_scores` (`infra/postgres/init/22-vihaan-quality-scores.sql`) |
| `fssai_eval/loop.py` | feedback → candidate scenarios; judge calibration |
| `fssai_eval/prompts/` | judge prompts `judge_support`, `judge_relevance`, `judge_status` (versioned, tagged) |
| `tools/` | scenario checker, schema exporter, demo rehearsal |
| `tests/test_api_routers.py` | tests for the API routes `feedback.py` and `quarantine.py` on the real app factory |
| `results/` | `<tag>.json` per run: config (no secrets), per-scenario rows, aggregates, definitions |
| `Dockerfile` | the `eval-scorer` image (`infra/compose/eval-scorer.yml`, profile `quality`) |

**Adding a scenario.**
1. Copy a line in `scenarios.jsonl` and give it a new `scenario_id`.
2. Set the expected route and findings. Requirement ids follow the researcher's convention: `LBL-<TOPIC>`
   (`LBL-ALLERGEN`, `LBL-VEG-MARK`, `LBL-NUTRITION`, `LBL-FSSAI-LICENCE`, `LBL-DATE-MARKING`, `LBL-INGREDIENTS`)
   and `CLM-<NUTRIENT>-<LEVEL>` (`CLM-PROTEIN-SOURCE`, `CLM-FIBRE-HIGH`, `CLM-SUGARS-LOW`).
3. Copy supporting quotes from the corpus with `data/corpus/tools/grep_pdf.py` or the index's `passages.jsonl`.
   Never quote from memory.
4. Run `check_scenarios.py --index ...`; it must say `ok`.
