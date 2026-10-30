# 306 · Run wall clock: 180 s on the real free-tier provider, 90 s for load tests

**Status:** accepted · **Owner:** Vismay · **Requirements:** A1, A5, D6

## Context
Every run has a hard wall-clock bound (`RUN_MAX_WALL_S`, A1). The gateway caps each LLM call by the time left
and gives up on a retry that would cross it (A5). The bound was 90 s, picked together with the SLO (`infra/loadtest/SLO.md`),
which is measured against the stub LLM.

On the real provider (Groq free tier), two limits matter:
- **8,000 tokens per minute.** One run uses about 8,000 to 12,500 tokens, so a run can exhaust the minute and
  then wait for it to refill.
- **200,000 tokens per day per model.** Found on 30 Oct: after 16 runs the provider answered
  `429 ... tokens per day (TPD): Limit 200000, Used 197292` with `retry-after: 1022`. That is about 16 runs a day.

What was measured:
- **27 Oct, 90 s bound, 8 paced runs:** `s41-protein-clearly-above` and `small-pack-exemption` stopped at 90 s
  (`complete=false`, 11-12 steps) while waiting on a per-minute 429. The runs that finished took 36-78 s.
- **30 Oct, 180 s bound, researcher 1.0.0 on the eval set with 60 s between runs:** 16 of 16 runs completed in
  17-52 s (median 37 s), including all five section 4.1 scenarios.

## Options
| Option | For | Against |
|---|---|---|
| Keep 90 s | Matches the SLO's text | A run that has to wait for one per-minute refill (~60 s) after a 40-50 s start fails; on 27 Oct that was 2 of 8, including the 4.1 case (demo #10) |
| **180 s for the real provider, 90 s for load tests** | Room for one per-minute refill plus the slowest measured run; load tests keep the bound the SLO was written against | Two values to keep straight |
| No bound | Never cuts a run short | Breaks A1; a daily-quota 429 would hold a worker for minutes |
| Shrink the prompt (`RESEARCHER_DRAFT_CHARS`) instead | Fewer tokens, fewer per-minute waits | Less regulation text in the draft; the researcher's quality trade-off, Namith's decision (102), not a platform setting |

## Decision
`RUN_MAX_WALL_S=180` in `.env.example` (the real provider is the default deployment and the demo). Load tests
set `RUN_MAX_WALL_S=90` with the other stub settings, so the SLO and its measurements are unchanged.

A daily-quota 429 is not waited out: its `retry-after` (minutes) is longer than any run, so the gateway stops at
once and the run ends honestly incomplete, routed to `regulatory-review`.

## Consequences
- An analyst can wait up to 3 minutes for a run on the free tier. Typical runs still take under a minute.
- The RQ job timeout follows (`RUN_MAX_WALL_S + 30 s`, decision 302), and so does the SSE deadline in the API.
- The free tier's daily cap, not the wall clock, limits how many real runs we can do: about 16 a day per key.
  Plan eval runs and rehearsals around it (`docs/contexts/LLM_Context.md` §4).
