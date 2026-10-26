# 2026-10-26: `setup_dev.py vihaan` failed twice on a fresh clone

- **Author:** Vihaan · **Severity:** local only; blocked setup for one person, nothing reached `main` ·
  **Components:** `scripts/setup_dev.py`, `services/worker/pyproject.toml`, branch `vihaan`

## What happened
On a fresh clone, `python scripts/setup_dev.py vihaan` stopped twice before running any test:

1. `ERROR: libs/gate[test] is not a valid editable requirement`.
2. After that was fixed: `ERROR: Could not find a version that satisfies the requirement fssai-observability (from
   fssai-worker)`.

## How it was noticed
The script exits on the first failed `pip install`, with the command in the traceback. Neither message points at the
real cause.

## Cause
1. The script switched to my long-lived branch, which tracked an `origin/vihaan` created on day 0, *before* the
   package skeletons existed. `libs/gate` was not on that branch, so pip read the path as a requirement name.
2. The script installs the API and worker for everyone (`RUNTIME`), but not `libs/observability`, which both now
   depend on (`fssai-observability`). It is not on PyPI, so pip searched the index and failed. The dependency was
   added to the services after the script's package list was written. Nobody saw it because their venvs already
   had the package from an earlier setup.

## Fix
1. `git fetch origin && git merge origin/main` on `vihaan` (merge, not rebase), as the 26 Oct instruction says. This
   brings in the skeletons.
2. Installed by hand, with the missing package added:
   `.venv/bin/python -m pip install -e "contracts[test]" -e "libs/gate[test]" -e "libs/verification[test]" -e "eval[test]" -e libs/observability -e services/worker -e services/api`,
   then ran the script's remaining steps (contract tests, own tests, `.env`, skills). Result: 22 contract tests
   passed and my three seams were `xfailed`, as expected for skeletons.
3. Reported to Vismay (owner of `scripts/setup_dev.py`): `RUNTIME` should include `libs/observability`, or the
   script should install each runtime package's local dependencies.

## Lesson
A setup script is only tested by a clean clone. Something you install once and keep in a long-lived venv can hide a
missing dependency for everyone who set up earlier. Merge `origin/main` into a long-lived branch *before*
anything that reads paths from the working tree. Running setup in CI on a fresh runner would catch this class of
failure.
