# 2026-10-26: my local `namith` branch and `origin/namith` had diverged on the same tasks

- **Author:** Namith · **Severity:** none reached `main`; caught before the first push · **Components:** `packages/prompts`,
  `packages/agents`, `docs/contexts/Namith.md`

## What happened
M1.1 and M1.2 (prompt store, classifier) existed twice: once on `origin/namith` (already merged to `main` in PR #4) and
once in my local clone as a different, fuller implementation, plus M2.1, M2.2 and guardrails work that had never been
pushed. The local branch was based on an older `main`, so the first `git merge origin/main` conflicted in seven files.

## How it was noticed
`git status` said the branch was "ahead of origin/namith by 38 commits" against a stale remote-tracking ref. After
`git fetch`, `git log namith..origin/main` showed the two histories had never met.

## Cause
Work was done in two places without fetching in between, and the local branch was not pushed after each task.

## Fix
Fetched first, committed the in-progress work and merged `origin/main` (merge, not rebase). Twice more, while the merge was
being finished, `origin/namith` gained its own versions of the same tasks (M2.1, then M2.2 and M3.1). The rule applied each
time: keep the versions already pushed for everything they cover (store, classifier, researcher, tools, grounding, prompts,
pipeline, guardrails), remove the local duplicates and their tests, and keep on top only the work the remote did not have:
per-agent metrics, the `agents.json` dashboard and the runbook. The merged tree was checked with the full test suites and by
running the pipeline built through the `IMPL_*` registry switches.

## Lesson
`git fetch` before starting a session, and push the branch after every finished task: a branch is only safe once it is on
the remote. Check `git log namith..origin/main` before building anything that might already exist.
