# Stub LLM fixtures

One file per prompt the agents use, named after the prompt tag that opens its system prompt
(`[prompt:<name>@<version>]`, LLM_Context §6.5):

| File | Used for |
|---|---|
| `<name>@<version>.json` | exactly that prompt version |
| `<name>.json` | every version of that prompt |
| `_default.json` | any prompt without a fixture of its own (and untagged calls) |

A file holds either `{"content": "<the assistant text>"}` or any other JSON object, which is returned
serialised as the assistant text (what a `json_mode` prompt expects).

**Where the contents come from.** Copy a real, well-formed response for each prompt from a trace
(`GET /v1/runs/{id}/trace`, the `llm` step's output) once Namith's prompts exist, so a load-test run
exercises the same parsing path as a real one. Until then every call gets `_default.json`, which the
agents treat as an unusable answer. That is fine for measuring queue, worker and retrieval behaviour,
and it is what the breaker demo needs. It is not a correctness test.

Never put real regulation text or thresholds in a fixture: the agents must get those from retrieval.
