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

**Where the contents come from.** The five agent prompts (`classifier`, `guardrail_judge`,
`researcher`, `researcher_draft`, `verifier_support`) each have a `<name>.json` fixture, so a load
test takes the same parse path as a real run. These were written by hand to match each prompt's
reply schema (`packages/prompts`, `packages/verification`), not copied from a live trace. Replace them
with trace copies (`GET /v1/runs/{id}/trace`, the `llm` step's output) once a full real run exists.
`researcher.json` finishes on the first step, so a load-test run is one researcher call long; the
verifier's support check returns no checks. The eval judges (`judge_*`) are not on the run path and
fall back to `_default.json`. `_default.json` still answers any unknown prompt, and the agents treat
it as an unusable answer. That is fine for measuring queue, worker and retrieval behaviour, and it is
what the breaker demo needs. It is not a correctness test, and `VERIFIER_SUPPORT_CHECK=off` still
applies if you want the verifier to skip its LLM check.

Never put real regulation text or thresholds in a fixture: the agents must get those from retrieval.
