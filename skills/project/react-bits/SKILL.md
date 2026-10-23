---
name: react-bits
description: Choosing and adding React Bits components (reactbits.dev, 218 animated React components) to services/web. Lists the components that fit this Operate-mode tool, the ones to avoid, and the pinned add script that copies a component with its licence header. Use when someone wants an animated component, a micro-interaction, a loader, a counter, or asks about React Bits.
---

# React Bits

React Bits ships each component in four flavors (JS/TS × CSS/Tailwind). We use **TS-CSS**:
TypeScript plus a plain CSS file, which fits the token-based CSS in `services/web`. The full list,
generated from the pinned upstream commit, is `skills/vendor/react-bits/CATALOG.md`
(`catalog.json` for scripts). Licence: MIT + Commons Clause, `skills/vendor/react-bits/LICENSE.md`
(fine for this non-commercial university project; never sell the components themselves).

## Rule: a component must convey state

The web client is a working tool (`skills/project/fssai-frontend`). A React Bits component earns
its place only when its motion tells the analyst something: a step started, finished or failed, a
number changed, the system is waiting. Decoration-only effects (cursors, backgrounds, 3D galleries,
text glitches) are out.

## Allowlist for services/web

| Component | Use it for |
|---|---|
| `StatusMark` | Per-step status glyph in the run timeline: idle ring → progress arc → check / failure |
| `CallChip` | A tool call or LLM call in the trace, with its live timer, ending green or red |
| `ThoughtLine` | The run header while the agents work; folds the steps into one line when done |
| `LatticeLoader` | The "queued / running" row with a live stopwatch |
| `Counter` | Totals that change: cost, tokens, latency (odometer roll) |
| `WarmTooltip` | Tooltip groups on dense rows (instant after the first one opens) |
| `RubberSegment` | A segmented control, e.g. form ↔ JSON input |

Anything else: propose it in the PR with the state it conveys, then add it here.

## Adding one

```bash
npm --prefix services/web run add:react-bits -- StatusMark
```

`services/web/scripts/add-react-bits.mjs` downloads `<Name>-TS-CSS.json` from the commit pinned in
`skills/manifest.json`, writes its files to `services/web/src/components/reactbits/<Name>/`, adds
the licence and source header, and prints the npm dependencies to install. Then:

1. Install the printed dependencies with exact versions (`npm i -E …`).
2. Map the component's colours and timings onto our tokens (`src/styles/tokens.css`) through its
   props or the CSS file. Leave no hard-coded palette that fights `DESIGN.md`.
3. Check `prefers-reduced-motion` behaviour and keyboard access; add them if missing.
4. Test the state it shows (`vitest`), then run the `fssai-frontend` gate.

Do not edit the component's logic beyond what steps 2–3 need, so updates stay easy. Never use
`npx shadcn add` here: it expects a shadcn + Tailwind setup we don't have.
