# 203: The ingestion gate: strict on shape, open on category, fail-open rate limit

- **Owner:** Vihaan · **Status:** Accepted
- **Requirement:** F1, F2, D1 (validate before any agent; quarantine rejects), D7 (per-client rate limiting) ·
  Code: `libs/gate/` · Contract: `docs/data-contract.md`

## Context

The gate is the single point where a request is accepted or refused (glossary: ingestion boundary). Everything
after it may assume valid data. Three choices are not obvious from the requirement.

## Decisions and the options rejected

1. **Out-of-corpus categories are accepted, not rejected.** *Rejected option:* a closed enum with only
   `breakfast-cereals`. F7 asks the system to *escalate* an out-of-corpus product, and a 422 would hide it from the
   trace, the reviewer and the eval (demo #5 needs the run). Malformed ids are still rejected, and the classifier
   and router escalate the rest.
2. **Unknown fields are rejected.** *Rejected option:* pydantic's default of ignoring them. A misspelt `protien_g`
   would be dropped silently and the label checked without it, which is worse than a 422 that names the typo.
3. **Mandatory declarations are *not* gate rules.** A label without an allergen statement is a valid request with an
   `unmet` finding. The gate checks the request, never compliance.
4. **Cross-field rules only where physics or the regulation gives the bound.** These are sugars ≤ carbohydrate,
   saturated + trans ≤ fat, mass balance ≤ 100 g, and energy within ±20 % of 4/4/9 kcal/g. The factors are
   FSS-LD-2020 5(3)(e)(i) and the tolerance is 5(3)(d). *Rejected:* a tighter energy band (e.g. ±10 %), which would
   reject real labels that count fibre at 2 kcal/g or round each nutrient.
5. **The rate limit is a Redis token bucket in one Lua script, and it fails open.** *Rejected:* a fixed-window
   counter, which lets twice the limit through at a window edge. *Rejected:* failing closed, which turns a Redis
   blip into a total outage for every client, when the queue on the same Redis already returns an honest 503.
   Rate-limited requests are not quarantined: they were not malformed, and the limit is checked before any
   validation work.
6. **The quarantine store never raises into the gate.** If Postgres is down, the record is kept in memory and
   logged, the caller still gets a quarantine id, and the reject still has its evidence.
7. **Backends are chosen by `auto`.** Redis and Postgres are used when reachable, memory otherwise. A clean clone
   run with `uvicorn` on a laptop (where the Compose host names do not resolve) still works.

## Consequences

- Property-based tests (`hypothesis`) feed arbitrary JSON and single-field corruptions. Writing them found one bug,
  a `FieldError` with an empty `loc` for a JSON key `""`, which is fixed.
- The JSON Schema in `docs/data-contract.schema.json` is generated from the gate's own tables, with a `--check` mode
  to keep it current. Cross-field rules are listed in it but cannot be enforced by JSON Schema alone.
- A new cross-field rule is a contract tightening: next `XF-` id, announced, never reused.
