# tools: for the people building the project

Nothing here runs in the deployed stack.

| Path | What | Owner |
|---|---|---|
| [`scripts/`](scripts/) | One-time clone setup, the smoke and clean-clone tests, every package's tests, the secrets audit, the cost report and the report builder. Python, so they run the same on Windows and macOS. | Vismay |
| [`skills/`](skills/) | Shared AI-assistant skills: our own `project/` skills (the workflow every change follows) and pinned `vendor/` copies of public libraries. `python tools/scripts/sync_skills.py install` puts them where Claude Code finds them. | Vismay |
