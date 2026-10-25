# Corpus (`corpus/`)

Owner: Nishkal. The regulation documents the system knows, and nothing else (spec §3).

| Path | What |
|---|---|
| `raw/FSS-AC-2018_compendium_2021-11-16.pdf` | Advertising and Claims Regulations 2018, compendium Version-II (16.11.2021) |
| `raw/FSS-LD-2020_compendium.pdf` | Labelling and Display Regulations 2020, compendium Version-VI (22.02.2023) |
| `sources.yaml` | hand-kept provenance: regulation code, version, official URL, where the bytes came from |
| `manifest.json` | generated: the above plus sha256, page count and text layer per file |
| `claim_triggers.yaml` | claim wording → Claims-regulation clauses, a retrieval hint (decision 002) |
| `eval/retrieval_queries.jsonl` | 28 labelled queries for recall@k (`python -m fssai_retrieval.evaluate`) |
| `tools/manifest.py` | regenerate `manifest.json` |
| `tools/grep_pdf.py` | search the PDFs page by page, to find and quote passages |

Why compendia, what "superseded" means in the index, and where the files came from: decision 004 and
`docs/incidents/2026-10-25-nishkal-fssai-site-unreachable.md`. The §4.1 passages, quoted from these files:
`docs/eval1/section-4.1-passages.md`.

## Adding or updating a document

1. Put the PDF in `raw/` and add its entry to `sources.yaml`. A PDF without an entry is refused, because
   an unattributed document must not reach the index.
2. `<venv-python> corpus/tools/manifest.py`. Check that the text layer says `yes`; otherwise OCR it first.
3. Rebuild the index: `python -m fssai_ingest build --corpus corpus/raw --out <INDEX_DIR> --reembed changed`.
   In Compose, `docker compose run --rm indexer` does the same. Only changed chunks are re-embedded.
4. Re-run `pytest libs/ingest libs/retrieval` and the recall evaluation. A changed clause id breaks the
   tests that pin the §4.1 passages, on purpose.
