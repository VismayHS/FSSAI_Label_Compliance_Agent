# fssai_eval (`eval`)

The eval set (`scenarios.jsonl`, `EvalScenario` per line), its runner and metrics (L3), and live scoring (L6).

**Owner:** Vihaan · tasks in [`contexts/Vihaan.md`](../contexts/Vihaan.md) · day-0 skeleton from the baseline.

| File | What | Task |
|---|---|---|
| `fssai_eval/__main__.py` | CLI with the agreed options; runner not implemented | V3.2 |
| `tests/test_eval_cli.py` | the CLI options | V3.2 |

```bash
<venv-python> -m pip install -e "eval[test]"     # setup_dev.py vihaan already does this
<venv-python> -m pytest eval -q                  # xfail = not built yet; a FAIL says which contract edge broke
```

**Done when** the conformance test passes without its `xfail` marker and your own tests cover the
behaviour in your task. Then switch it on with nothing: it runs the configured pipeline in-process in your `.env` (and as a comment in your
section of `.env.example`), and tell Vismay.
