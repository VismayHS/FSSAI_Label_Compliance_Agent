# fssai_retrieval (`libs/retrieval`)

Search and exact clause lookup over the regulation index (F4, L1), plus the Redis retrieval cache (D7).

**Owner:** Nishkal · tasks in [`contexts/Nishkal.md`](../../contexts/Nishkal.md) · day-0 skeleton from the baseline.

| File | What | Task |
|---|---|---|
| `fssai_retrieval/faiss_retriever.py` | `FaissRetriever`, the `Retriever` seam | N2.2, N3.3 |
| `tests/test_retriever_contract.py` | conformance test (xfail until built) | N2.2 |

```bash
<venv-python> -m pip install -e "libs/retrieval[test]"     # setup_dev.py nishkal already does this
<venv-python> -m pytest libs/retrieval -q                  # xfail = not built yet; a FAIL says which contract edge broke
```

**Done when** the conformance test passes without its `xfail` marker and your own tests cover the
behaviour in your task. Then switch it on with `IMPL_RETRIEVER=fssai_retrieval.faiss_retriever:FaissRetriever` in your `.env` (and as a comment in your
section of `.env.example`), and tell Vismay.
