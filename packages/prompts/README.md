# fssai_prompts (`packages/prompts`)

Versioned prompts and the store that serves them (L2). Prompt versions travel on every response.

**Owner:** Namith · tasks in [`docs/contexts/Namith.md`](../../docs/contexts/Namith.md) · day-0 skeleton from the baseline.

| File | What | Task |
|---|---|---|
| `fssai_prompts/store.py` | `FilePromptStore`, the `PromptStore` seam | M1.1, M3.2 |
| `tests/test_prompt_store_contract.py` | conformance test (xfail until built) | M1.1 |

```bash
<venv-python> -m pip install -e "packages/prompts[test]"     # setup_dev.py namith already does this
<venv-python> -m pytest packages/prompts -q                  # xfail = not built yet; a FAIL says which contract edge broke
```

**Done when** the conformance test passes without its `xfail` marker and your own tests cover the
behaviour in your task. Then switch it on with `IMPL_PROMPTS=fssai_prompts.store:FilePromptStore` in your `.env` (and as a comment in your
section of `.env.example`), and tell Vismay.
