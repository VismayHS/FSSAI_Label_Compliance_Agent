---
name: fssai-review
description: Reviewing a change in the FSSAI Label Compliance Agent repo before it goes into a PR - correctness, safety, load, tests, speed, leanness, plus this project's graded rules (gate before enqueue, citations resolve, never approve, no secrets, own paths only). Combines ponytail-review's method and output with ECC's reviewer agents. Use for "review this", "review my branch", before opening a PR, and as step 6 of fssai-workflow.
---

# FSSAI review

Review like the person who gets paged when it breaks (`vendor/ponytail/skills/ponytail-review`).
Order: correct, safe, holds under load, tested, fast, lean.

## 1. Scope

- Default target: the person's branch against `origin/main` (`git diff origin/main...HEAD`), or the
  uncommitted changes if there are any.
- Read the diff, then the code it touches: callers of every changed function, the tests, the
  contracts it implements. A changed signature means grepping every caller.
- Expected load: `--scale worker=3`, Locust at the SLO concurrency (`loadtest/SLO.md` once it exists).

## 2. Project checks (each one is graded or zero-marks if missed)

| Check | Where it bites |
|---|---|
| Only the person's own paths changed (LLM_Context §5) | any |
| No credentials, endpoints or model ids in code; new env vars in the owner's `.env.example` section | D4 |
| Gate runs before any enqueue; a 422 starts no agent run | D1, demo #4 |
| Every citation resolves to a passage retrieved in this run; unverified → `regulatory-review` | A3, F5 |
| Nothing ever "approves" a label; `NOT_AN_APPROVAL` notice present | non-negotiable 1 |
| `ctx.check_budget()` before steps; every step recorded with `ctx.record()` incl. full passages for tool calls | A1, D5 |
| Timeouts on every outbound call; bounded retries; breaker state shared across workers | A5, A7 |
| Workers stateless (nothing per-process that must be shared) | A7 |
| Free-text label fields treated as untrusted (never executed, never rendered as HTML) | L4 |
| `pytest contracts -q` still green | everyone |

## 3. Reviewer agents by file type (`skills/vendor/ecc/agents/`)

| Touched | Run |
|---|---|
| any code | `code-reviewer`, `silent-failure-hunter` |
| `*.py` | `python-reviewer`; FastAPI routes → `fastapi-reviewer` |
| SQL, `deploy/postgres/` | `database-reviewer` |
| `*.ts`, `*.tsx` | `typescript-reviewer`, `react-reviewer`; UI → `a11y-architect` + `fssai-frontend` §7–8 |
| auth, input handling, secrets, shell | `security-reviewer` |
| retrieval, chunking, eval | `rag-pipeline-reviewer`, `mle-reviewer` |
| tests | `pr-test-analyzer` |

Run them at the review step only (not after every edit); they cost free-tier budget.

## 4. Before reporting

- Every finding has a concrete case: "this input leads to this wrong result". No case, no finding.
- Re-read the lines and confirm. Propose the smallest fix; prefer fixes that delete code.
- A `shortcut:` comment that names its limit is a decision, not a finding, unless the expected
  load already crosses it.

## 5. Output (ponytail-review format)

Plain English. Start with `What this change does:` in two or three sentences, then:

- **Must fix:** bugs, security, data loss, a graded rule above broken, breaks at the expected load.
- **Should fix:** risky code without a test, real slowness, duplication, code that should not exist.
- **Nice to have:** small speed-ups, shorter forms.

Each finding: file:line, what happens, the fix, what happens if we skip it. UI findings use Emil's
`| Before | After | Why |` table. End with what you did not check.
