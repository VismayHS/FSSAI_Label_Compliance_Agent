# 101. Injection and toxicity guardrails: heuristics first, no model in the request path

- **Status:** accepted · **Author:** Namith · **Task:** M3.1 (L4)

## Context
Every free-text label field reaches an agent that holds tools, so each is hostile input (LLM_Context §12.6). The brief
allows heuristics, a local classifier model or an LLM judge, "whichever you justify".

## Options considered
1. **LLM judge on every field.** Catches paraphrases. Costs a call per field per run on a free tier we are already rate
   limited on (see the runbook), adds latency to every run and is itself prompt-injectable. Rejected for the request path.
2. **Local classifier model (e.g. a Prompt-Guard style model).** Good recall, but a large download, extra container
   memory and an arm64 and offline-build risk for a project whose hard rule is that `docker compose up` always boots.
3. **Heuristics over normalised text, layered with structural defences.** Chosen.

## Decision
- `fssai_guardrails.detectors.InjectionHeuristics`: patterns in seven categories (instruction override, role play,
  prompt exfiltration, delimiter escape, verdict dictation, tool abuse, other languages) run over text folded for case,
  width, zero-width characters and look-alike letters.
- Toxicity uses a small lexicon by default. `GUARDRAIL_TOXICITY_MODEL` adds a local model on top when someone wants one;
  if it cannot load, the lexicon keeps working and the fallback is logged.
- Heuristics are a first layer, not a proof. They are backed by the layers that do not depend on recognising an attack:
  label text always travels inside data delimiters and is never in a system prompt; tool arguments are validated against
  an allowlist; every citation must be a verbatim substring of a retrieved passage; and `filter_output` can only
  downgrade a route, never upgrade one, so a successful injection still cannot make the system approve a label.
- Detectors are pluggable (`GUARDRAIL_DETECTORS`) so a judge or model can be added without touching the pipeline.

## Consequences
- `libs/guardrails/tests/attacks.yaml` is the regression suite (24 attacks across four fields, three languages, leetspeak,
  zero-width and full-width tricks). Writing it found three real misses: the normaliser stripped `_` and `|`, which hid
  `</label_data>`, `<|im_start|>` and `corpus_search`. A `keep_symbols` pass fixed them.
- A paraphrase the patterns do not know will get through the input screen. The other layers are what contain it.
  The 30+ attack CI suite with a measured block rate (extra) is where that gap gets quantified.
- A false positive blocks a run (the route is `regulatory-review`). Ordinary label wording is covered by a test.
