---
name: react-bits
description: Choosing and adding React Bits components (reactbits.dev, 218 animated React components) to apps/web. Lists the components that fit this Operate-mode tool, the ones to avoid, and the pinned add script that copies a component with its licence header. Use when someone wants an animated component, a micro-interaction, a loader, a counter, or asks about React Bits.
---

# React Bits

React Bits ships each component in four flavors (JS/TS × CSS/Tailwind). We use **TS-CSS**:
TypeScript plus a plain CSS file, which fits the token-based CSS in `apps/web`. The full list,
generated from the pinned upstream commit, is `tools/skills/vendor/react-bits/CATALOG.md`
(`catalog.json` for scripts). Licence: MIT + Commons Clause, `tools/skills/vendor/react-bits/LICENSE.md`
(fine for this non-commercial university project; never sell the components themselves).

## Rule: a component must convey state

The web client is a working tool (`tools/skills/project/fssai-frontend`). A React Bits component earns
its place only when its motion tells the analyst something: a step started, finished or failed, a
number changed, the system is waiting. Decoration-only effects (cursors, backgrounds, 3D galleries,
text glitches) are out.

## Allowlist for apps/web

| Component | Use it for |
|---|---|
| `StatusMark` | Per-step status glyph in the run timeline: idle ring → progress arc → check / failure |
| ~~`CallChip`~~ | Tried for trace steps and removed: its chip-and-glyph status fought the square pack marks (finish review). Use `Mark` on the spine instead. |
| `ThoughtLine` | The run header while the agents work; folds the steps into one line when done |
| `LatticeLoader` | The "queued / running" row with a live stopwatch |
| `Counter` | Totals that change: cost, tokens, latency (odometer roll) |
| `WarmTooltip` | Tooltip groups on dense rows (instant after the first one opens) |
| `RubberSegment` | A segmented control, e.g. form ↔ JSON input |

In use in `apps/web`: `Counter` (trace totals), `LatticeLoader` (queued / running), `RubberSegment`
(Form | JSON). A component must speak the screen's own status grammar; if it brings a second one
(its own glyphs, pills, colours for state), map it or leave it out.

Anything else: propose it in the PR with the state it conveys, then add it here.

## Adding one

```bash
npm --prefix apps/web run add:react-bits -- StatusMark
```

`apps/web/scripts/add-react-bits.mjs` downloads `<Name>-TS-CSS.json` from the commit pinned in
`tools/skills/manifest.json`, writes its files to `apps/web/src/components/reactbits/<Name>/`, adds
the licence and source header, and prints the npm dependencies to install. Then:

1. Install the printed dependencies with exact versions (`npm i -E …`).
2. Map the component's colours and timings onto our tokens (`src/styles/tokens.css`) through its
   props or the CSS file. Leave no hard-coded palette that fights `DESIGN.md`.
3. Check `prefers-reduced-motion` behaviour and keyboard access; add them if missing.
4. Test the state it shows (`vitest`), then run the `fssai-frontend` gate.

Do not edit the component's logic beyond what steps 2–3 need, so updates stay easy. Never use
`npx shadcn add` here: it expects a shadcn + Tailwind setup we don't have.
