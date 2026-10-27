# Verification, data contract, evaluation and feedback

Owner: Vihaan · Requirements: F1, F2, F6, F7, A3, D1, D7 (rate limiting), L3, L6 · Status: draft. The design and
the harness are final. The before/after numbers marked **TODO(LLM)** need a free-tier key in `.env` and are filled
from `packages/eval/results/` (decision 205).

## 1. Problem and scope of this part

The system must be trustworthy at both ends. On the way **in**, nothing malformed may reach an agent. On the way
**out**, nothing unverified may reach a person as an answer. The spec says F5 (grounded findings) and F7 (knowing
when not to answer) "hold most of the difficulty", and the glossary sets the priority: *"stating a provision that
does not exist is more serious than declining to answer."* This part also has to *prove* the system's quality,
with an evaluation set and metrics, and keep measuring it after deployment.

## 2. The data contract and the ingestion gate (F1, F2, D1, D7)

The published contract is `docs/data-contract.md`, with a JSON Schema generated from the same code
(`docs/data-contract.schema.json`). The gate (`fssai_gate.gate:RequestGate`) is the single ingestion boundary:

```
X-Client-Id + size (API) -> rate limit -> schema/type + unknown fields -> version, ranges, lengths, formats
                         -> category id -> cross-field rules XF-01..XF-10 -> accept | 422 + quarantine
```

- **All errors at once.** Every stage that can run does. Ranges are checked on raw values, so a type error in
  one field does not hide a range error in another. Each error is `FieldError{loc, message, code}` with a stable
  `code`.
- **Quarantine with evidence.** Each reject is stored with the raw payload, client id, errors and time (Postgres
  table `quarantine`; in memory without a database). It is readable at `GET /v1/quarantine`. A rejected request
  never gets a run row or a queue job, which demo #4 checks by counting runs and the `rejected` counter.
- **Cross-field rules** come from physics or from the regulation itself. Energy must be within ±20 % of
  4/4/9 kcal/g: the factors are FSS-LD-2020 5(3)(e)(i) and the tolerance is 5(3)(d). The others are sugars ≤
  carbohydrate, saturated + trans ≤ fat, mass ≤ 100 g per 100 g, basis vs net-quantity unit, serving pairs, and a
  claimed nutrient being declared.
- **What the gate does not do.** It does not judge compliance (a label with no allergen line is a valid request
  with an `unmet` finding), and it does not reject out-of-corpus categories, which must *escalate* (F7) and so
  need a run.
- **Rate limiting** (D7) is a token bucket per `X-Client-Id` in one Redis Lua script, so all API replicas share it
  atomically and use the Redis clock. It is checked before any validation work, and rate-limited calls are not
  quarantined. If Redis is down it fails open: the queue on the same Redis already answers an honest 503, and
  failing closed would turn a counter-store blip into a total outage.

Decision record 203 lists the options rejected. The gate has 83 tests, including property-based tests (Hypothesis)
that feed arbitrary JSON. They found one real bug, an error with an empty `loc` for a JSON key `""`.

## 3. Verification design (A3, A2)

The verifier (`fssai_verification.verifier:AgentVerifier`) is the second agent: its own prompt
(`verifier_support@1.0.0`), its own tools (`resolve_citation`, `clause_lookup`) and its own per-finding state.
For each finding:

| # | Check | How | Result if it fails |
|---|---|---|---|
| 1 | Citations resolve | The quote must be a substring of a passage retrieved in this run (whitespace, curly quotes and dashes normalised; case kept) | retry, with a hint naming the clause, or the passage that really holds the quote |
| 2 | Numbers | Re-read the claim's condition from the **cited passage** (claim word, threshold, unit, basis per 100 g / ml / kcal) and compare with the declared value, independently of the researcher | `mismatch` → retry; `% of RDA` with no value, bases that disagree, or a value whose ±20 % tolerance band spans the threshold → escalate |
| 3 | Support | One LLM call per attempt (NLI-style): does the passage, with the request facts, entail the finding's status? Only for findings that passed 1 and 2 | retry with "search for the provision that decides …" |
| 4 | Action | Signals or escalate-class problems → escalate; fixable → retry (or escalate on the last attempt); else accept | |

Check 2 exists because of the pitfall that a citation can be real while the conclusion is wrong. In the tests, a
"Source of fibre" finding marked `met` with a perfect quote of *"Product contains at least 3 g of fibre per 100 g"*,
on a panel declaring 1 g, is sent back even when an LLM judge waves it through. Retry hints are specific, and their
strategy changes with the attempt (clause lookup first, then the other regulation), so a retry is never the same
search. `clause_lookup` only sharpens the hint ("the clause exists but was not retrieved"). It never makes a finding
supported, because A3 requires text the researcher retrieved in the run.

**Routing** (`RuleRouter`, decision 201) is an ordered list of nine rules, most cautious first. Each route's reason
starts with its rule id. An unverified verdict, an out-of-corpus category, escalation signals, no findings or any
`cannot_determine` go to `regulatory-review`. So does R6, which encodes the project's core obstacle: **a printed
claim with no finding about it that cites the Claims regulation is never cleared**, and checking one claim does
not clear another. Any `unmet` goes to
`revise-and-recheck` with what to fix; only all-met goes to `clear-for-print`, with the not-an-approval notice.

**§4.1.** The protein condition is *"10% of RDA per 100 g for solids … or 5% of RDA per 100 kcal"* and the RDA value
is not in the corpus. A `met`/`unmet` verdict on it is therefore escalated (check 2: `needs_reference`), and the
reference answers in `docs/eval1/section-4.1-test-values.md` are `regulatory-review` until the team adopts a cited
value. For each case they give the exact range of RDA values under which each basis is met, so the answer can be
read off once a value is chosen.

## 4. Evaluation method (L3)

**Eval set:** `packages/eval/scenarios.jsonl`, 30 scenarios in the breakfast-cereal category:

Groups overlap, because one scenario can carry several tags:

| Group | Scenarios |
|---|---|
| §4.1 variants | 5: pass, fail, synonym, high, basis differs |
| Numeric claims on conditions stated in grams | 10: fibre, sugar, fat and sodium, including a boundary and a basis-differs case |
| Mandatory declarations, veg mark, allergen | 7 |
| Possible small-pack exemptions | 2 |
| Out of scope | 2 |
| Conflicting statements | 3 |
| Claims with no condition | 1 |
| Prompt injection | 2 |
| Traps where one retrieval pass gives the wrong answer | 5, e.g. "Contains protein" as a Schedule II synonym, and a small pack whose exemption is undone by a claim |

Expected routes: 14 `regulatory-review`, 12 `revise-and-recheck`, 4 `clear-for-print`. Each scenario has an
expected route, expected findings and **real supporting quotes**.
`packages/eval/tools/check_scenarios.py` proves each quote is verbatim text of the named clause in the built index, and that
each request passes the gate. It caught one hand-typed quote: the corpus reads "n o sugars" where it was typed as
"no sugars".

**Runner:** `python -m fssai_eval run --tag <name>` runs every scenario through `build("pipeline")` in-process, so
it measures whatever the `IMPL_*` switches select. It writes `packages/eval/results/<tag>.json` with per-scenario rows,
aggregates, the config (no secrets) and the definitions below. `compare` prints a before/after table with deltas;
`gate` fails CI if hallucination or unsafe clears rise, or route accuracy drops.

**Unit:** a *statement* is one finding (requirement, status, explanation).

| Metric | Exactly how it is computed |
|---|---|
| **Groundedness** (TruLens) | Per statement: **0** if any citation does not resolve verbatim to a passage retrieved in this run (or a met/unmet statement cites nothing). Otherwise the judge's support score of the statement against its cited passages, 0–1 (TruLens `groundedness_measure_with_cot_reasons`; the offline judge scores a resolving citation as 1). Per response: the mean over its statements. Reported: the mean over responses that make at least one statement. |
| **Context relevance** (TruLens) | Per retrieved passage (everything any tool returned in the run): relevance to the scenario question, 0–1 (TruLens `context_relevance_with_cot_reasons`; offline: 1 if the passage is one of the scenario's gold supporting clauses, else 0). Per response: the mean over passages. Reported: the mean over responses that retrieved anything. |
| **Faithfulness** | Per decisive statement (met/unmet): **1 if its *status* follows from its cited passages plus the request's declared values**, else 0. Numeric claim conditions are re-derived deterministically; the rest are judged (prompt `judge_status`). Reported: the share over judged statements, with coverage. |
| **Hallucination rate** | Per **response**: true if at least one statement is unsupported (groundedness < 0.5) or unfaithful. Reported: the share of responses that make statements (glossary: per response, not an average). |
| Route accuracy, finding accuracy | Against the expected route; the share of expected (requirement, status) pairs found with that status. Ids are matched exactly, else by same prefix and token overlap ≥ 0.5 (`LBL-VEG-MARK` ~ `LBL-VEG-LOGO`). |
| Escalation recall, unsafe-clear rate | The share of expected-`regulatory-review` scenarios routed there; the share of `clear-for-print` routes that should not have cleared. |

**Why groundedness and faithfulness differ.** Groundedness asks whether the *words* are backed by the cited text.
Faithfulness asks whether the *conclusion* follows from that text and the label's numbers. The fibre example above
is fully grounded (1.0) and unfaithful (0); a unit test pins exactly that case.

**Judges** (decision 204):

- `reference`: offline, deterministic and free; used in CI.
- `llm`: our versioned judge prompts through the gateway.
- `trulens`: the TruLens feedback functions on any OpenAI-compatible provider from env.

All judge calls are cached on disk. RAGAS was rejected: both 0.2 and 0.4 fail to import next to the
`langchain-community` 0.4 that retrieval needs (incident 2026-10-26). The cross-check is judge calibration
instead: agreement and Cohen's kappa against hand labels (`fssai_eval calibrate`).

**Caveats, stated rather than hidden.** Offline numbers are lower bounds on what a reading judge would flag.
Offline context relevance is a gold-clause proxy, not TruLens's reference-free score. With the verifier on, offline
faithfulness shares its numeric parser with the verifier, so the LLM and TruLens judges are the independent
measure.

## 5. Results

**Harness check on the contracts' fakes** (29 scenarios, offline judge). This shows the measurement and the
verifier/router effect, *not* model quality, because the fake researcher only checks the allergen line:

| Metric | Fake verifier + router | AgentVerifier + RuleRouter | Δ |
|---|---|---|---|
| Route accuracy | 0.310 | 0.345 | +0.034 |
| Escalation recall | 0.308 | 0.615 | +0.308 |
| Citation resolution | 1.000 | 1.000 | 0 |

The rise in escalation recall is rule R6: claims the fake researcher never checked against FSS-AC-2018 are no
longer cleared.

**Before/after, one deliberate change** (decision 205: researcher prompt 1.0.0 → 1.1.0, everything else fixed,
`--judge llm`): **TODO(LLM)**. The table is produced by
`python -m fssai_eval compare researcher-1.0.0 researcher-1.1.0`.

| Metric | 1.0.0 | 1.1.0 | Δ |
|---|---|---|---|
| Groundedness | TODO | TODO | |
| Context relevance | TODO | TODO | |
| Faithfulness | TODO | TODO | |
| Hallucination rate | TODO | TODO | |
| Route accuracy | TODO | TODO | |

## 6. Feedback and live quality (L6)

- `POST /v1/runs/{id}/feedback {satisfactory, reason}` stores feedback with the run's route at that moment, in
  Postgres table `feedback`. It returns 404 for an unknown run and 409 for an unfinished one.
- `GET /v1/feedback/summary?days=` gives the satisfactory rate overall, by route and by day, and the top reasons
  (normalised text).
- `python -m fssai_eval live --sample 10` scores the newest completed runs with the same metrics (the
  reference-free ones; there is no gold answer live) into `quality_scores`, once per run and scorer version. The
  opt-in Compose service `eval-scorer` runs it every `LIVE_SCORE_EVERY_S`.
- Grafana "Quality and trust" (`quality.json`) charts live groundedness, faithfulness and hallucination over time,
  the feedback rate by route and day with the top reasons, and the gate's accepted, rejected and rate-limited flow
  with quarantine by error code.
- `python -m fssai_eval candidates` turns unsatisfactory feedback into **draft** scenarios, tagged `needs-review`.
  A person sets the expected answer before one joins the eval set; nothing is added automatically, because an
  unreviewed "expected answer" would be invented.

## 7. What did not work, and what was rejected

- RAGAS as a dependency (dependency conflict; section 4).
- A borderline band measured from the *threshold*. It was replaced by the regulation's own rule: the ±20 %
  tolerance applies to the *declared* value (FSS-LD-2020 5(3)(d)), so a value is uncertain exactly when
  declared × (1 ± 20 %) spans the threshold.
- An absolute "no unsafe clears" rule in the CI gate. It would fail on today's fakes forever, so it is relative to
  the baseline, like the other rules.
- Recording `resolve_citation` as a tool step. It touches no corpus, and doing so would spend the run's tool-call
  budget (A1), so its calls are listed inside the verification step.
