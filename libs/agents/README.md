# fssai_agents (`libs/agents`)

The classifier and research agents and the LangGraph pipeline that runs them (F3-F5, A1, A2).

**Owner:** Namith · tasks in [`contexts/Namith.md`](../../contexts/Namith.md) · day-0 skeleton from the baseline.

| File | What | Task |
|---|---|---|
| `fssai_agents/classifier.py` | `LLMClassifier`, the `Classifier` seam | M1.2 |
| `fssai_agents/researcher.py` | `LangGraphResearcher`, the `Researcher` seam | M2.1 |
| `fssai_agents/graph.py` | `LangGraphPipeline`, the `Pipeline` seam | M2.2 |
| `tests/test_agents_contract.py` | conformance tests (xfail until built) | M1.2, M2.1, M2.2 |

```bash
<venv-python> -m pip install -e "libs/agents[test]"     # setup_dev.py namith already does this
<venv-python> -m pytest libs/agents -q                  # xfail = not built yet; a FAIL says which contract edge broke
```

**Done when** the conformance test passes without its `xfail` marker and your own tests cover the
behaviour in your task. Then switch it on with `IMPL_CLASSIFIER`, `IMPL_RESEARCHER` and `IMPL_PIPELINE` (M2.3) in your `.env` (and as a comment in your
section of `.env.example`), and tell Vismay.
