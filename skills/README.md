# Skills: how we build, for people and AI assistants

Everything an AI coding assistant (or a person) needs to build this project the way the best
public skill libraries do, in one folder. It works without cloning anything else.

| Folder | What it is |
|---|---|
| [`project/`](project/) | **Our own skills. Start here.** They say which vendored skill to use at each step and where our rules override them. |
| [`vendor/`](vendor/) | Unmodified copies of seven upstream skill libraries, pinned to a commit, each with its licence ([SOURCES.md](SOURCES.md)). |
| [`manifest.json`](manifest.json) | What is vendored (repo, commit, paths) and which skills and agents get installed. |

## Our skills (`project/`)

| Skill | Use it |
|---|---|
| [`fssai-workflow`](project/fssai-workflow/SKILL.md) | For every change: orient, spec, search, test first, smallest complete change, verify, review, record, commit on your own branch. Maps each job to the right vendored skill. |
| [`fssai-frontend`](project/fssai-frontend/SKILL.md) | Any UI, above all `services/web`: impeccable Operate mode, the house rules, motion, React Bits, the real-browser gate. |
| [`react-bits`](project/react-bits/SKILL.md) | Choosing and adding React Bits components; the allowlist for our tool. |
| [`fssai-review`](project/fssai-review/SKILL.md) | Reviewing a branch before a PR: the graded project checks plus the right reviewer agents. |

## Vendored libraries (`vendor/`)

| Library | Upstream | What it gives us |
|---|---|---|
| [`taste-skill`](vendor/taste-skill/) | VismayHS/taste-skill-cc | Anti-slop art direction (taste-skill v2 for landing pages), minimalist and redesign skills, full-output enforcement, and the `lint.mjs` / `inspect.mjs` browser gate |
| [`emil-skills`](vendor/emil-skills/) | VismayHS/skills-frontend-cc | Emil Kowalski's design engineering: animation decisions, review standards, `break-ui`, `pick-ui-library`, prototyping, mobile-native fixes |
| [`impeccable`](vendor/impeccable/) | pbakaus/impeccable | One design skill with 24 commands (`shape`, `critique`, `audit`, `polish`, `harden`, …), modes, the craft floor, 4 helper agents |
| [`react-bits`](vendor/react-bits/) | DavidHDev/react-bits | [CATALOG.md](vendor/react-bits/CATALOG.md) of all 218 components (TS + CSS flavor) with dependencies and install names |
| [`ponytail`](vendor/ponytail/) | dietrichgebert/ponytail | Smallest-complete-change discipline, `ponytail-review`, `ponytail-audit`, debt and gain reports |
| [`ecc`](vendor/ecc/) | affaan-m/ECC | The parts of Everything Claude Code that fit our stack: 25 agents (planner, architect, reviewers per language, security, TDD, a11y, RAG/ML), 39 skills, coding rules for Python/TypeScript/React/web |
| [`ruflo`](vendor/ruflo/) | ruvnet/ruflo | SPARC, ADR, test generation, security audit, DDD, cost tracking, observability, docs and swarm plugins (their skills and agents, as reference) |

## Using them

**Claude Code** loads skills from `.claude/skills/` and agents from `.claude/agents/`. Both are
generated from this folder and gitignored:

```bash
python scripts/sync_skills.py install      # also run by scripts/setup_dev.py
```

That installs our four project skills, 63 vendored skills and 29 agents. Skills trigger by
themselves from their descriptions; you can also call one by name (`/impeccable audit`,
`/ponytail-review`, `/fssai-review`).

**Other assistants** (Cursor, Copilot, Codex, Gemini, …) don't read `.claude/`. `AGENTS.md` tells
them to read `skills/project/fssai-workflow/SKILL.md` first; point them at any other `SKILL.md`
by path when you need it.

**People:** the SKILL.md files are plain Markdown. `fssai-workflow` is a good read before your
first PR.

### Tools the skills run

| Tool | Needs | Notes |
|---|---|---|
| `vendor/taste-skill/skills/taste-skill/scripts/lint.mjs`, `inspect.mjs` | Node 22+, Chrome or Edge | Source lint and real-browser inspection at 1440/768/390 with screenshots. Installs nothing. |
| `vendor/impeccable/skills/impeccable/scripts/impeccable` (`.cmd` on Windows) | nothing | Downloads its engine binary once into `~/.impeccable/` and checks its sha256. If it can't run, the skill reads `PRODUCT.md` / `DESIGN.md` directly. |
| ruflo (optional, per person) | Node 20+ | ruflo's own skills call its MCP tools. To use them: `/plugin marketplace add ruvnet/ruflo` then `/plugin install ruflo-core@ruflo` in Claude Code. Never run `npx ruflo init` in this repo: it rewrites `.claude/` and adds hooks for everyone. Our `fssai-workflow` gives the same SPARC phases without it. |

## Updating

```bash
python scripts/sync_skills.py update               # move every pin to upstream HEAD, re-vendor
python scripts/sync_skills.py update --source ecc  # just one library
python scripts/sync_skills.py vendor               # re-copy at the current pins (e.g. after editing the manifest)
python scripts/sync_skills.py check                # verify vendor/ matches the manifest
```

To vendor more of a library, add the path to its `copy` map in `manifest.json`; to install it for
Claude Code, add it to `install` (skills) or `agents`. Review the diff of `skills/vendor/` like any
other change: it is text an assistant will follow. This folder is owned by Vismay (LLM_Context §5);
propose changes in a PR.

## Licences

Each `vendor/<library>/` keeps its upstream `LICENSE` (and impeccable's `NOTICE.md`). Five are MIT,
impeccable is Apache-2.0, React Bits is MIT + Commons Clause (use is free; selling the components
themselves is not). Files under `vendor/` are not modified; our adaptations live in `project/`.
