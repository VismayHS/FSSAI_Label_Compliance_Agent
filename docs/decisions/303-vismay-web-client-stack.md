# 303 · Web client: React + Vite + TypeScript, CSS tokens, React Bits for state

**Status:** accepted · **Owner:** Vismay · **Requirements:** A8 (+ the reviewer-console extra)

## Context
A8 asks for a simple client that submits a request, gets the result and shows the recommendation with
citations and the escalation path. "No marks for appearance", but the demo is watched live and the
trace view (D5, demo #3) and a reviewer console (extra) need real interaction: polling, a step
timeline, expandable passages.

## Options
1. Plain HTML + vanilla JS served by the API.
2. **React + Vite + TypeScript**, static build served by nginx.
3. Next.js.

## Decision
Option 2.
- TypeScript types mirror `packages/contracts/fssai_contracts/schemas.py`, so a contract change shows up as a
  compile error instead of a blank field during the demo.
- React fits the stateful parts (polling, timeline, disclosure) without hand-written DOM code, and lets
  us use React Bits' agent-status components (`StatusMark`, `CallChip`, `ThoughtLine`, `LatticeLoader`)
  where motion conveys run state.
- Vite builds to static files: one small nginx container, no Node at runtime. Next.js would add a
  server we don't need.
- Plain CSS with design tokens (`src/styles/tokens.css`), no Tailwind: one less build layer, and React
  Bits ships a TS + CSS flavor.
- The API is reached through a same-origin `/v1` path (Vite dev proxy locally, nginx in Compose), so
  no CORS configuration is needed; `/config.js` supplies runtime settings.

## Consequences
- The design rules live in `apps/web/DESIGN.md` and `tools/skills/project/fssai-frontend`.
- `npm run check` (types, lint, tests, build) is part of the definition of done for web changes.
