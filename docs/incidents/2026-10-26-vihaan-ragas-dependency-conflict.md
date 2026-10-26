# 2026-10-26: RAGAS cannot be installed next to the team's retrieval stack

- **Author:** Vihaan · **Severity:** design change before merge; nothing reached `main` · **Components:** `eval/`
  (judges), `libs/retrieval` (its pins)

## What happened
The plan for the L3 extras was a RAGAS faithfulness cross-check next to TruLens. In a throwaway venv, with the same
`langchain-core` 1.x the team uses:

- `ragas` 0.4.3 installed, pulled `openai` 3.x (which breaks `trulens-providers-openai`, pinned `openai<2`), and then
  failed on import: `ModuleNotFoundError: No module named 'langchain_community.chat_models.vertexai'`.
- `ragas` 0.2.15 with `openai<2` failed on the same import.

## How it was noticed
It was tried in a scratch venv before touching the project venv, precisely because RAGAS pins a lot.

## Cause
RAGAS imports a module that `langchain-community` 0.4 no longer has. `fssai_retrieval` requires
`langchain-community>=0.4,<1` (Nishkal's index), so the two cannot share an environment without downgrading the
retrieval stack.

## Fix
No RAGAS dependency (decision 204):
- Faithfulness is our own claim-level metric. Numeric conditions are re-derived; the rest is judged by our prompt or
  through TruLens.
- The RAGAS-style cross-check became judge calibration, which reports agreement and Cohen's kappa against hand
  labels (`python -m fssai_eval calibrate`).
- TruLens 2.16 was installed in the project venv and `pip check` reported no conflicts; the retrieval and agent
  tests still passed.

## Lesson
Try heavy evaluation libraries in a scratch environment against the team's pins first. An "extra" that forces a
downgrade of another person's core dependency costs more than it adds.
