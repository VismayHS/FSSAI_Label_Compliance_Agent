# 201: Routing rules: ordered, explicit, most cautious first

- **Owner:** Vihaan · **Status:** Accepted
- **Requirement:** F6 (route to clear / revise / regulatory-review with a reason), F7 (escalate on conflict, possible
  exemption, out-of-corpus category), A3 (never return an unverified answer) · Code: `packages/verification/fssai_verification/router.py`

## Context

The router turns the verifier's verdict and the researcher's findings into one of three routes. It is the last
deterministic step before the output filter, so it decides what a regulatory affairs professional sees first. The
glossary is explicit about the costs: *"stating a provision that does not exist is more serious than declining to
answer"*. A wrong `clear-for-print` is therefore the worst outcome, a needless `regulatory-review` the cheapest.
The routes are never an approval.

## Options

| Option | For | Against |
|---|---|---|
| **Ordered rule list, first match wins, most cautious first** | Every route can be explained by one rule id; the order states the priorities; each rule is a unit test | Rules must be kept in sync with new signals |
| Score-based (weighted findings, thresholds) | One number | Hides *why*; a threshold is a number we would be inventing; hard to defend at review |
| Let the LLM pick the route | Flexible | Not auditable, and an LLM could be talked into "clear" by injected label text |

## Decision

An ordered rule list. The first rule that fires decides, and its id starts the reason text:

| Rule | When | Route | Why this order |
|---|---|---|---|
| R1 | verdict is not `accept` | regulatory-review | A3: an unverified answer is never routed on its content |
| R2 | category outside the corpus | regulatory-review | F7; normally the pipeline stops earlier, this is the safety net |
| R3 | escalation signals in the dossier | regulatory-review | F7: conflict, possible exemption, missing condition |
| R4 | no findings | regulatory-review | nothing was checked, so nothing can clear |
| R5 | any `cannot_determine` | regulatory-review (lists any `unmet` too) | an open question outranks a known fix; the reviewer also sees what to fix |
| R6 | a printed claim with no finding *about it* (quoting the claim or naming its nutrient) that cites FSS-AC-2018 | regulatory-review | the project's core obstacle: the claim condition lives in the other regulation. A labelling-only answer must not clear a claim, and checking one claim does not clear another. With a single claim, any `CLM-` finding citing FSS-AC-2018 counts |
| R7 | any `unmet` | revise-and-recheck, listing each with its explanation | a known, fixable problem |
| R8 | every finding `not_applicable` | regulatory-review | nothing confirms the label |
| R9 | all `met` / `not_applicable`, at least one `met` | clear-for-print + the not-an-approval notice | "no problem found in what was checked" |

`unmet` together with `cannot_determine` goes to regulatory-review rather than revise. A revise route would invite
a quick fix and a resubmission while the open question stays open.

## Consequences

- Every route has a human-readable reason, and every `regulatory-review` has an `escalation_reason`, so the
  reviewer console and the trace show why without reading code.
- R6 means a weak researcher (or the fake one) produces more escalations. That is the intended failure direction:
  on the fakes, switching the router on raised escalation recall from 0.31 to 0.62 on the eval set.
- The routing step records the rule id (`output.rule`), so the eval can count which rules fire.
- Adding a signal means adding a rule, a test in `packages/verification/tests/test_router.py` and a row above.
