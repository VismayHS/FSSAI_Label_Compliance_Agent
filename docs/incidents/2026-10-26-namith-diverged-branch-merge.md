# 2026-10-26: my local `namith` branch and `origin/namith` had diverged on the same tasks

- **Author:** Namith · **Severity:** none reached `main`; caught before the first push · **Components:** `libs/prompts`,
  `libs/agents`, `contexts/Namith.md`

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
Fetched first, committed the in-progress work and merged `origin/main` (merge, not rebase). The first resolution kept my
local M1.1/M1.2; when `origin/namith` then gained its own M2.1 as well, the decision was made to keep the versions already
on `main` for everything they cover (M1.1, M1.2, M2.1: store, classifier, researcher, tools, grounding, prompts). The
local duplicates (claims, llmio, extra prompt files, their tests) were removed, and only the work `main` did not have was
kept on top: the LangGraph pipeline, guardrails with their red-team fixtures, per-agent metrics, dashboard and runbook.
The merged tree was checked by running the pipeline built through the `IMPL_*` registry switches.

## Lesson
`git fetch` before starting a session, and push the branch after every finished task: a branch is only safe once it is on
the remote. Check `git log namith..origin/main` before building anything that might already exist.
