# fssai_gate (`libs/gate`)

The ingestion boundary (F2, D1) and per-client rate limiting (D7). Nothing reaches an agent without passing it.

**Owner:** Vihaan · tasks in [`contexts/Vihaan.md`](../../contexts/Vihaan.md) · day-0 skeleton from the baseline.

| File | What | Task |
|---|---|---|
| `fssai_gate/gate.py` | `RequestGate`, the `RequestGate` seam | V1.2 |
| `tests/test_gate_contract.py` | conformance test (xfail until built) | V1.2 |

```bash
<venv-python> -m pip install -e "libs/gate[test]"     # setup_dev.py vihaan already does this
<venv-python> -m pytest libs/gate -q                  # xfail = not built yet; a FAIL says which contract edge broke
```

**Done when** the conformance test passes without its `xfail` marker and your own tests cover the
behaviour in your task. Then switch it on with `IMPL_GATE=fssai_gate.gate:RequestGate` in your `.env` (and as a comment in your
section of `.env.example`), and tell Vismay.
