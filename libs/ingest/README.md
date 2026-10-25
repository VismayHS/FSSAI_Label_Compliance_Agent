# fssai_ingest (`libs/ingest`)

The idempotent index builder (D2, L1). Owner: Nishkal · task N2.1 · design: decision
[002](../../docs/decisions/002-nishkal-chunking.md).

```bash
python -m fssai_ingest build --corpus corpus/raw --out <INDEX_DIR> [--reembed none|changed|all]
python -m fssai_ingest manifest --corpus corpus/raw        # corpus/manifest.json (provenance, sha256, text layer)
python -m fssai_ingest chunks --corpus corpus/raw [--text]  # what the build would index
```

| File | What |
|---|---|
| `fssai_ingest/chunker.py` | clause-aware parser: regulations, markers, schedule tables, amendment blocks → chunks |
| `fssai_ingest/build.py` | idempotent build, partial re-embed, `index_manifest.json` |
| `fssai_ingest/corpus.py` | scan `corpus/raw` + `sources.yaml` → documents with sha256 and version |
| `fssai_ingest/pdftext.py` | pypdf text extraction |
| `Dockerfile` | the `indexer` image (CPU torch); Compose: `deploy/compose/indexer.yml` |

`build` exit codes: `0` built, updated or unchanged (JSON report on stdout); `3` stored chunks changed and
`--reembed none` was given. Needs `EMBEDDING_MODEL` (`hashing` works offline for tests).

```bash
<venv-python> -m pip install -e "libs/ingest[test,embeddings]"
<venv-python> -m pytest libs/ingest -q    # chunker rules, real-corpus checks, idempotency, partial re-embed
```

In Compose the `indexer` service runs `build --reembed changed` on every `docker compose up` and exits 0.
The worker starts after it (`service_completed_successfully`) and reads the `index-data` volume.
