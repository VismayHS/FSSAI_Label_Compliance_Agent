# fssai_observability (`libs/observability`)

JSON logs, OTel tracing and metric helpers that every service imports (D5).

**Owner:** Nishkal · tasks in [`contexts/Nishkal.md`](../../contexts/Nishkal.md) · day-0 skeleton from the baseline.

| File | What | Task |
|---|---|---|
| `fssai_observability/__init__.py` | `setup_logging`, `setup_tracing` | N3.1 |
| `tests/test_observability_contract.py` | what callers rely on (xfail until built) | N3.1 |

```bash
<venv-python> -m pip install -e "libs/observability[test]"     # setup_dev.py nishkal already does this
<venv-python> -m pytest libs/observability -q                  # xfail = not built yet; a FAIL says which contract edge broke
```

**Done when** the conformance test passes without its `xfail` marker and your own tests cover the
behaviour in your task. Then switch it on with nothing: the API and worker call it at start-up once it works in your `.env` (and as a comment in your
section of `.env.example`), and tell Vismay.
