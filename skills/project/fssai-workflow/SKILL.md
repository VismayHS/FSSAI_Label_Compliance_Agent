---
name: fssai-workflow
description: The end-to-end way of building anything in the FSSAI Label Compliance Agent repo - spec, search, test first, smallest complete change, verify, review, record, commit on your own branch. Combines SPARC (ruflo), TDD + verification loop + reviewers (ECC), the smallest-change discipline (ponytail) and the repo's own rules. Use on every coding, refactoring, bug-fix, review or documentation task in this repository, before writing code.
---

# FSSAI workflow

One loop for every change in this repo. It strings together the vendored skills in
`skills/vendor/` and says which one to use at each step. When two sources disagree, the order of
authority is:

1. `AGENTS.md` and `contexts/LLM_Context.md` §12 (non-negotiables), then `CONTRIBUTING.md`
2. this file and the other `skills/project/*` skills
3. the vendored skills

## 0. Orient (always)

- Who is this for? `git config fssai.branch` names the person. Read `contexts/<Name>.md`: their
  tasks, status and **the only paths they may edit**.
- `git branch --show-current` must be that person's branch. If not, stop and say so.
- Find the requirement ids the task serves (F1–F8, A1–A8, L1–L6, D1–D8 in LLM_Context §3). Every
  change should name at least one.

## 1. Specify (SPARC "Specification" + "Pseudocode", from `vendor/ruflo/plugins/ruflo-sparc`)

For anything bigger than a one-file fix, write before coding (in the PR description, or a
`### Notes` entry in the person's `contexts/<Name>.md`):

- **Acceptance criteria**, at least three, as `Given … when … then …`. They become the tests.
- **Edge cases**, at least three: invalid input, a dependency down, concurrency or scale.
- **Constraints**: latency, security, the seam (`contracts/fssai_contracts/interfaces.py`) it implements.
- **Data flow** in three to six lines of pseudocode when there is real logic.

A decision with options (queue library, async model, chunking) gets a decision record in
`docs/decisions/NNN-<name>-<slug>.md`: context, options, decision, consequences
(`vendor/ecc/skills/architecture-decision-records`, `vendor/ruflo/plugins/ruflo-adr`).

ruflo's own skills call ruflo's MCP memory tools. We keep the same phases but store the artifacts
as files in the repo, so they are reviewable and survive without ruflo installed.

## 2. Search first (`vendor/ecc/skills/search-first`, `vendor/ponytail/skills/ponytail`)

Take the first rung that fully works:

1. Does it need to exist at all? Name what you skip in one line.
2. Already in the repo? `contracts/` (schemas, fakes, `RunContext`, registry) covers most seams.
3. Standard library or platform feature.
4. A dependency already installed in this package.
5. Only then new code, the minimum that works. A new dependency needs a one-line reason.

## 3. Tests first (`vendor/ecc/skills/tdd-workflow`, `vendor/ecc/skills/python-testing`, `react-testing`)

- One failing test per acceptance criterion, then the code. Bug fix: a test that reproduces it first.
- Use the fakes from `contracts/fssai_contracts/fakes.py` for anyone else's seam. Tests never need
  a teammate's unfinished code, a real LLM or a network.
- Real-LLM or real-service tests are marked `slow` and skipped by default.
- Coverage: risky logic (branches, parsers, money, security, retries, data writes) always gets a
  test. We do not chase ECC's 80% number for its own sake (ponytail: one good test, not coverage).

## 4. Build the smallest complete change (`vendor/ponytail/skills/ponytail`, level `full`)

- Finish every part the task needs: callers, tests, fixtures, `.env.example`, docs.
- Never cut: validation at trust boundaries, error handling that prevents data loss, security,
  accessibility, anything the person asked for.
- Code against `contracts/` interfaces; select implementations through `IMPL_*` env vars.
- No credentials, endpoints or model ids in code. New settings go in the person's own section of
  `.env.example` with a comment.
- Every step a run takes goes through `ctx.record()`; every notable event through `ctx.event()`.
- Python: `vendor/ecc/rules/python`, `vendor/ecc/skills/python-patterns`, `fastapi-patterns`.
  TypeScript/React: `vendor/ecc/rules/typescript`, `rules/react`, and `skills/project/fssai-frontend`.
- A known limit gets a comment `shortcut: <the limit>, <when to upgrade>`.

## 5. Verify (`vendor/ecc/skills/verification-loop`)

Run, don't assume. Report the actual output.

```bash
<venv-python> -m pytest contracts -q            # must stay green
<venv-python> -m pytest <your package> -q
npm --prefix services/web run check             # web client: typecheck + lint + tests + build
```

Then exercise the real thing: start the service and hit it, or open the page in a browser
(`skills/project/fssai-frontend` §7). A green unit test is not proof the feature works.

## 6. Review (`skills/project/fssai-review`)

Self-review the diff before asking anyone else. Use the review skill's checklist and the ECC
reviewer agents it names for the file types you touched.

## 7. Record

- Tick the task in `contexts/<Name>.md` and add a dated line under Notes.
- Something really broke? `docs/incidents/YYYY-MM-DD-<name>-<slug>.md` (D8).
- Made a decision? `docs/decisions/` (§1).

## 8. Commit and push (only when the person asks)

- Commit on the person's own branch with `<area>: <what changed>` messages. No AI attribution lines.
- `git push` goes to `origin/<name>` only. Open a PR `main ← <name>`; never push to `main`.
- `vendor/ecc/skills/git-workflow` describes rebasing and squash merges. **Do not follow those
  parts here**: we merge `origin/main` in and merge PRs with merge commits (CONTRIBUTING.md).

## Which skill for which job

| Job | Use |
|---|---|
| New feature or service | this file, then `vendor/ecc/agents/planner.md`, `architect.md` |
| API endpoint, Pydantic models | `vendor/ecc/skills/api-design`, `fastapi-patterns`, agent `fastapi-reviewer` |
| Queue, cache, rate limits, breaker state | `vendor/ecc/skills/redis-patterns`, `backend-patterns`, `error-handling` |
| Postgres tables, SQL | `vendor/ecc/skills/postgres-patterns`, `database-migrations`, agent `database-reviewer` |
| LLM calls, cost, prompts | `vendor/ecc/skills/cost-aware-llm-pipeline`, `prompt-caching-strategy`, `vendor/ruflo/plugins/ruflo-cost-tracker` |
| Retrieval, chunking, RAG | `vendor/ecc/skills/iterative-retrieval`, agent `rag-pipeline-reviewer` |
| Agents, evals | `vendor/ecc/skills/agent-eval`, `eval-harness`, `ai-regression-testing`, `mle-workflow`, agent `mle-reviewer` |
| Load tests, SLO | `vendor/ecc/skills/benchmark-methodology`, `vendor/ruflo/plugins/ruflo-observability` |
| Containers, Compose | `vendor/ecc/skills/docker-patterns`, `deployment-patterns` |
| Web client, any UI | `skills/project/fssai-frontend`, `skills/project/react-bits` |
| Security-sensitive code | `vendor/ecc/skills/security-review` (installed as `ecc-security-review`), `security-scan`, agent `security-reviewer`, `vendor/ruflo/plugins/ruflo-security-audit` |
| Swallowed errors, flaky failures | agent `silent-failure-hunter` |
| Docs and the report | `vendor/ruflo/plugins/ruflo-docs`, agent `doc-updater` |
| Output keeps getting cut short | `vendor/taste-skill/skills/output-skill` |
| Too much code | `vendor/ponytail/skills/ponytail` level `ultra`, `ponytail-audit` |

## Overrides of vendored advice

| Vendored advice | What we do instead | Why |
|---|---|---|
| ECC git-workflow: rebase, squash merges | merge `origin/main`; merge-commit PRs | CONTRIBUTING.md: each person keeps their own history |
| ECC: 80%+ coverage required | a test for every risky behaviour | ponytail; LLM_Context §8.5 |
| ECC: "always immutable" | follow the surrounding code; Pydantic `model_copy` where shared | the contracts already define the style |
| ruflo: store artifacts in MCP memory | store them as repo files | reviewable, works without ruflo |
| ruflo / ECC: "spawn agents proactively" | use reviewer agents at the review step | keep runs cheap; free-tier LLM budget |
| taste-skill: rules for landing pages | Operate-mode rules in `fssai-frontend` | our web client is a tool, not a marketing page |
