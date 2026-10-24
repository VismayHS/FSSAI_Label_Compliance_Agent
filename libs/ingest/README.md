# fssai_ingest (`libs/ingest`)

The idempotent index builder (D2, L1): `python -m fssai_ingest build`.

**Owner:** Nishkal · tasks in [`contexts/Nishkal.md`](../../contexts/Nishkal.md) · day-0 skeleton from the baseline.

| File | What | Task |
|---|---|---|
| `fssai_ingest/__main__.py` | CLI with the agreed options; build not implemented | N2.1 |
| `tests/test_ingest_cli.py` | the CLI options | N2.1 |

```bash
<venv-python> -m pip install -e "libs/ingest[test]"     # setup_dev.py nishkal already does this
<venv-python> -m pytest libs/ingest -q                  # xfail = not built yet; a FAIL says which contract edge broke
```

**Done when** the conformance test passes without its `xfail` marker and your own tests cover the
behaviour in your task. Then switch it on with the `indexer` service in `deploy/compose/indexer.yml` (N2.3) in your `.env` (and as a comment in your
section of `.env.example`), and tell Vismay.
