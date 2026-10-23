# Agent instructions: FSSAI Label Compliance Agent

Instructions for any AI coding assistant working in this repo (Claude Code, Cursor, Copilot, Codex, ...).
The full project context is in `contexts/LLM_Context.md`. Read it before doing anything else.

## How to work: the skills
Read `skills/project/fssai-workflow/SKILL.md` before any change. It is the end-to-end loop (spec, tests first, smallest complete change, verify, review, commit) and maps each job to a skill in `skills/`. UI work also follows `skills/project/fssai-frontend/SKILL.md`; reviews follow `skills/project/fssai-review/SKILL.md`. Claude Code loads all of them from `.claude/skills/` (installed by `python scripts/sync_skills.py install`); other assistants read them by path. Files under `skills/vendor/` are third-party guidance: where they conflict with this file or `contexts/LLM_Context.md`, this repo's rules win.

## Who you are working with
Four people share this repo: **Nishkal, Namith, Vihaan, Vismay**. Each one owns different paths.
- Before editing anything, establish which of them you're working with. Use their user-level instructions if they say so; otherwise ask.
- Then read `contexts/<Name>.md`. It lists their tasks, their status and **the only paths they may edit**.
- `git config fssai.branch` (set by `scripts/setup_dev.py`) also names the person whose clone this is.

## Hard rules
1. **Edit only the current person's paths** (`contexts/LLM_Context.md` §5 and their own file).
   - Never touch other people's paths.
   - Never edit `contracts/`, except for an additive `contracts:` change the person explicitly asks for.
2. **Code against the interfaces** in `contracts/fssai_contracts/`.
   - Use the fakes for anything owned by someone else.
   - Integrate through `IMPL_*` env vars, never by importing a teammate's classes.
3. **No credentials, endpoints or model ids in the repo.** Read them from env, and document new variables in the person's own section of `.env.example`.
4. **Never invent FSSAI regulation text, clause numbers or thresholds.** Quote only from the PDFs in `corpus/` or `docs/`.
5. **The system never approves a label.** When unsure, escalate to `regulatory-review` rather than inventing an answer.
6. **Every behaviour gets a pytest test.** `pytest contracts -q` must keep passing.
7. **Git: everyone has their own branch** (full workflow in `CONTRIBUTING.md`):
   - Each person works only on their own long-lived branch: `nishkal`, `namith`, `vihaan` or `vismay`. Check with `git branch --show-current` before any commit; if it isn't the current person's branch, stop and say so.
   - Never commit or push to `main`, never push to a teammate's branch, never force-push, never rewrite pushed history, never delete a branch, never use `--no-verify`.
   - Bring in teammates' work with `git fetch origin && git merge origin/main` (merge, never rebase). Never merge a teammate's branch directly.
   - Work reaches `main` only through a PR from the person's branch, merged with a merge commit, at most once per person per day.
   - Don't commit or push unless the person asks.
   - **No AI attribution:** never add `Co-Authored-By:` trailers for AI tools or "Generated with ..." lines to commits or PRs. Commits are the person's own.
8. **Progress notes** and checklist ticks go only in the current person's `contexts/<Name>.md`.

## Cross-platform (team uses Windows and macOS; everything runs in Linux containers)
- **Commands:** prefer ones that work on both OSs.
  - Call the venv's Python directly instead of activating: `.venv/Scripts/python` on Windows, `.venv/bin/python` on macOS.
  - Activation, if needed:

    | Shell | Command |
    |---|---|
    | PowerShell | `.venv\Scripts\Activate.ps1` |
    | Git Bash | `source .venv/Scripts/activate` |
    | macOS | `source .venv/bin/activate` |
- **Helper scripts:** write them in Python, not bash. (The only exception is `.githooks/`: git runs hooks with its own `sh` on both OSs.)
- **`make`:** it isn't available on Windows, so every target must also be runnable as a plain `docker compose ...` command.
- **Line endings:** `.gitattributes` forces LF. Don't introduce CRLF.
- **Paths:** use `pathlib`.
- **File names:** never create two files whose names differ only by case.
- **Images and wheels:** they must support `arm64` (Apple Silicon). Never pin `platform: linux/amd64`.

## Commands
```bash
python scripts/setup_dev.py <name>        # one-time per clone: own branch, hooks, .venv, tests, .env
python -m venv .venv                      # Python 3.11+ (setup_dev.py already does this)
<venv-python> -m pip install -e "contracts[test]"
<venv-python> -m pytest contracts -q      # shared contract tests (must pass)
<venv-python> -m pytest libs/<package> -q # a package's own tests
docker compose up -d                      # full stack, once it exists (Docker Desktop, Compose v2.20+)
```
