# fssai_verification (`libs/verification`)

The verifier agent (A3: every answer checked against retrieved text) and the router (F6, F7).

**Owner:** Vihaan · tasks in [`contexts/Vihaan.md`](../../contexts/Vihaan.md) · day-0 skeleton from the baseline.

| File | What | Task |
|---|---|---|
| `fssai_verification/verifier.py` | `AgentVerifier`, the `Verifier` seam | V2.1 |
| `fssai_verification/router.py` | `RuleRouter`, the `Router` seam | V2.2 |
| `tests/test_verification_contract.py` | conformance tests (xfail until built) | V2.1, V2.2 |

```bash
<venv-python> -m pip install -e "libs/verification[test]"     # setup_dev.py vihaan already does this
<venv-python> -m pytest libs/verification -q                  # xfail = not built yet; a FAIL says which contract edge broke
```

**Done when** the conformance test passes without its `xfail` marker and your own tests cover the
behaviour in your task. Then switch it on with `IMPL_VERIFIER` and `IMPL_ROUTER` (V2.3) in your `.env` (and as a comment in your
section of `.env.example`), and tell Vismay.
