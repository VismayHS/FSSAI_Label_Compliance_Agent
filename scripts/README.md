# scripts

Helpers written in Python, so they run the same on Windows and macOS. The `Makefile` wraps most of them.

| Script | What | `make` |
|---|---|---|
| `setup_dev.py <name>` | One-time setup of a clone: your branch, git hooks, `.venv`, tests, `.env`, skills | |
| `smoke.py` | Demo #1: the running stack is ready, completes a run, and rejects a malformed request without starting one | `make smoke` |
| `clean_clone_test.py` | Clone, `cp .env.example .env`, `docker compose up`, smoke test: what an examiner does | `make clean-clone` |
| `test_all.py` | Every Python package's tests, one pytest process each (what CI runs) | `make test` |
| `audit_secrets.py` | D4: fails on credentials, provider endpoints or model ids in the repo | `make audit` |
| `cost_report.py` | L5: cost per 100 runs, cost by step and agent, and the biggest cost driver, from the run store | `make cost` |
| `sync_skills.py` | Vendor, update and install the shared AI-assistant skills (see `skills/README.md`) | |
