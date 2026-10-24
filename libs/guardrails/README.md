# fssai_guardrails (`libs/guardrails`)

Prompt-injection defence, toxicity in and out, and output filtering (L4).

**Owner:** Namith · tasks in [`contexts/Namith.md`](../../contexts/Namith.md) · day-0 skeleton from the baseline.

| File | What | Task |
|---|---|---|
| `fssai_guardrails/guardrails.py` | `Guardrails`, the `Guardrails` seam | M3.1 |
| `tests/test_guardrails_contract.py` | conformance test (xfail until built) | M3.1 |

```bash
<venv-python> -m pip install -e "libs/guardrails[test]"     # setup_dev.py namith already does this
<venv-python> -m pytest libs/guardrails -q                  # xfail = not built yet; a FAIL says which contract edge broke
```

**Done when** the conformance test passes without its `xfail` marker and your own tests cover the
behaviour in your task. Then switch it on with `IMPL_GUARDRAILS=fssai_guardrails.guardrails:Guardrails` in your `.env` (and as a comment in your
section of `.env.example`), and tell Vismay.
