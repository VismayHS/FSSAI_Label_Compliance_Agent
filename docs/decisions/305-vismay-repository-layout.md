# 305 · Repository layout: six top-level folders by what a thing is for

**Status:** accepted · **Owner:** Vismay · **Requirements:** report/code/docs quality, D3

## Context
The repository grew to twelve top-level folders (`contexts contracts corpus deploy docs eval libs loadtest
observability scripts skills services`), one per concern as each was added. A reader could not tell from the top
level what runs, what is a library, what is deployment and what is only for the people building it. Every folder
already had a README and the root README a map, but the shape itself was the first thing a reviewer saw.

## Options
1. **Keep the twelve folders**, explained by READMEs. No risk, but the top level stays noisy.
2. **Fold only Vismay's folders** (contexts into docs, scripts and skills into tools): twelve to ten, and every
   teammate's prompts still change.
3. **Group everything by purpose** into `apps/` (what runs), `packages/` (Python components, including the shared
   contracts and the eval package), `infra/` (Compose, Postgres tables, observability config, load test), `data/`
   (the corpus), `docs/` (including the context files) and `tools/` (scripts, AI skills).

## Decision
Option 3, done on 27 Oct 2026 in one change, when no teammate had unmerged work (all three branches were level with
`main`), so nothing in flight could conflict. Folders were moved with `git mv`, so history follows each file
(`git log --follow`), and a teammate's later edits merge onto the moved files through git's rename detection.

| Was | Now |
|---|---|
| `services/` | `apps/` |
| `libs/`, `contracts/`, `eval/` | `packages/`, `packages/contracts/`, `packages/eval/` |
| `deploy/`, `observability/`, `loadtest/` | `infra/`, `infra/observability/`, `infra/loadtest/` |
| `corpus/` | `data/corpus/` |
| `contexts/` | `docs/contexts/` |
| `scripts/`, `skills/` | `tools/scripts/`, `tools/skills/` |

Unchanged on purpose: Python package names (`fssai_*`), the paths inside containers (`/src/...`, `/corpus`,
`/data/index`), Compose service and volume names, every `IMPL_*` value and every environment variable. Ownership
is the same; only the paths in LLM_Context §5 and CODEOWNERS changed.

## Consequences
- The top level reads as six purposes. Each has a README with an owner table.
- Every editable install points at the old paths, so after pulling each person re-runs
  `python tools/scripts/setup_dev.py <name>` once.
- Every reference was rewritten by a script and then checked: all package tests, the web check, `docker compose
  config`, a full image build and smoke test, the clean-clone test, every relative Markdown link, and CI.
- A path in a teammate's own notes or prompts written before this change points at the old location; the mapping
  above translates it.
