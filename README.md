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
1. Read [contexts/LLM_Context.md](contexts/LLM_Context.md): the project, architecture, ownership and working rules.
2. Read your own file in [contexts/](contexts/), which has your tasks, checklist and LLM prompts.
3. Run the shared contract tests:
   ```bash
   python -m venv .venv && . .venv/bin/activate
   pip install -e "contracts[test]"
   pytest contracts -q
   ```

## Repository map
| Path | What |
|---|---|
| `contexts/` | Team and LLM context files |
| `docs/` | Course documents (spec, glossary, index) and project docs |
| `contracts/` | Shared schemas, interfaces, fakes, reference pipeline |
| `libs/`, `services/` | Components (each one is its own package) |
| `eval/`, `loadtest/`, `observability/`, `deploy/` | Evaluation, load tests, monitoring, deployment |

## Running the system
*Coming soon:* `cp .env.example .env && docker compose up`.
