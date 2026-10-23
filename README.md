# FSSAI Label Compliance Agent

A multi-agent service that checks a proposed packaged-food label against FSSAI regulations. It
returns a compliance finding for each requirement, with citations to regulation and clause, and
routes the label to `clear-for-print`, `revise-and-recheck` or `regulatory-review`.
**It never approves a label for print; a regulatory affairs professional decides.**

Mini Project 10 for UE24AM342AA5, ML System Design & AgentOps (Dept of CSE (AI & ML), PESU).

| Team | Workstream |
|---|---|
| Nishkal | Knowledge & Performance: corpus, retrieval, caching, observability, SLO + load testing |
| Namith | Agent Reasoning: LangGraph agents, prompts, guardrails, agent metrics |
| Vihaan | Trust & Evaluation: data contract + validation, verifier agent, routing, evaluation, feedback |
| Vismay | Platform & Integration: API, queue, workers, LLM gateway, Docker Compose, tracing, web client |

## Status
🚧 In development. Shared contracts and fakes are in place. Services are being built.
This README will become the full "run it from a clean clone" guide before submission.

## Start here (team)
Everyone works on **their own branch** (`nishkal`, `namith`, `vihaan`, `vismay`) and keeps their own
commit history. Nobody commits or pushes to `main`; work reaches it only through PRs. Read
[CONTRIBUTING.md](CONTRIBUTING.md) before your first commit.

1. Set your git identity to your GitHub account, then clone and run the setup script with your name:
   ```bash
   git config --global user.name  "Your Name"
   git config --global user.email "you@example.com"     # the email on your GitHub account
   git clone https://github.com/VismayHS/FSSAI_Label_Compliance_Agent.git
   cd FSSAI_Label_Compliance_Agent
   python scripts/setup_dev.py <your-name>             # nishkal | namith | vihaan | vismay
   ```
   It switches you to your branch, turns on the git hooks, creates `.venv`, installs the shared
   contracts, runs their tests and creates `.env`.
2. Read [contexts/LLM_Context.md](contexts/LLM_Context.md): the project, architecture, ownership and working rules.
3. Read your own file in [contexts/](contexts/), which has your tasks, checklist and LLM prompts.
   AI coding assistants pick up [AGENTS.md](AGENTS.md) (and Claude Code also loads [CLAUDE.md](CLAUDE.md)) automatically.

Re-run the contract tests any time with `.venv/Scripts/python -m pytest contracts -q` (Windows)
or `.venv/bin/python -m pytest contracts -q` (macOS/Linux).

## Repository map
| Path | What |
|---|---|
| `contexts/` | Team and LLM context files |
| `docs/` | Course documents (spec, glossary, index) and project docs |
| `contracts/` | Shared schemas, interfaces, fakes, reference pipeline |
| `scripts/`, `.githooks/` | One-time clone setup; git hooks that keep everyone on their own branch |
| `libs/`, `services/` | Components (each one is its own package) |
| `eval/`, `loadtest/`, `observability/`, `deploy/` | Evaluation, load tests, monitoring, deployment |

## Running the system
*Coming soon:* `cp .env.example .env && docker compose up`.
