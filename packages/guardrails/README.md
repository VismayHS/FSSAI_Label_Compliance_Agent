# fssai_guardrails (`packages/guardrails`)

Prompt-injection defence, toxicity in and out, and output filtering (L4).

**Owner:** Namith · tasks in [`docs/contexts/Namith.md`](../../docs/contexts/Namith.md) · design: decision [101](../../docs/decisions/101-namith-guardrails.md).

| File | What |
|---|---|
| `fssai_guardrails/guardrails.py` | `Guardrails`: `screen_input` (blocks the run before any agent) and `filter_output` (only ever makes a result safer) |
| `fssai_guardrails/detectors.py` | pluggable detectors: control characters, length, injection heuristics, toxicity (lexicon or model), optional LLM judge |
| `fssai_guardrails/text.py` | walk every string in a request; fold obfuscated text |
| `tests/attacks.yaml` | the red-team file: 29 attacks, 11 clean labels. Add new attacks here first |
| `tests/test_screen_input.py`, `test_filter_output.py`, `test_in_pipeline.py` | behaviour tests |

```bash
<venv-python> -m pip install -e "packages/guardrails[test]"
<venv-python> -m pytest packages/guardrails -q
```

**Switched on with** `IMPL_GUARDRAILS=fssai_guardrails.guardrails:Guardrails`. It passes `conformance.check_guardrails`.

| Env | Default | |
|---|---|---|
| `GUARDRAIL_DETECTORS` | `control,length,injection,toxicity` | add `judge` for the LLM second layer (one extra LLM step per run), or `module:Class` for your own |
| `GUARDRAIL_MAX_FIELD_CHARS` | `4000` | longer fields are flagged |
| `GUARDRAIL_TOXICITY_MODEL` | empty | a transformers text-classification model (`pip install -e "packages/guardrails[model]"`); empty = built-in lexicon |
| `GUARDRAIL_TOXICITY_THRESHOLD` | `0.8` | score at which the model flags |

Flags look like `prompt_injection:label.claims[0]`; the report names the field and the rule, never the attacker's text.
