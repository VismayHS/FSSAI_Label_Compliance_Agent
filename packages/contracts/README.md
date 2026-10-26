# contracts: the shared seams

`fssai_contracts` is the one package every other package depends on. It defines what passes between owners,
so nobody has to wait for anybody (LLM_Context §6). Steward: Vismay. Changes are additive only, each in its own
`contracts:` commit and PR.

| Module | What it holds |
|---|---|
| `schemas.py` | Every data shape: `LabelCheckRequest`, `Passage`, `Finding`, `Citation`, `ResearchDossier`, `Verdict`, `RunResult`, `RunStatus`, `Feedback`, `EvalScenario`, ... |
| `interfaces.py` | One `Protocol` per seam (gate, retriever, LLM client, prompts, guardrails, classifier, researcher, verifier, router, pipeline, run store), with its owner |
| `registry.py` | The switchboard: `IMPL_<SEAM>=module:Class` in `.env` picks the real implementation; empty means the fake |
| `fakes.py` | A working fake for every seam. Its regulation text is labelled PLACEHOLDER and is not real FSSAI text |
| `pipeline.py` | `ReferencePipeline`: the agreed hand-off order and edge behaviour, in plain Python |
| `context.py` | `RunContext`: loop bounds (`check_budget`), the step trace (`record`), structured events (`event`) |
| `conformance.py` | One `check_<seam>()` per seam: the behaviour every implementation keeps at its edges |
| `dev_llm.py` | A bare OpenAI-compatible client for early agent work (production uses `packages/llm_gateway`) |

```bash
<venv-python> -m pip install -e "packages/contracts[test]"
<venv-python> -m pytest packages/contracts -q      # the fakes pass every conformance check
```
