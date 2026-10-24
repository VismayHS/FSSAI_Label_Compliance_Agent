---
name: fssai-frontend
description: How to design, build, review and verify any UI in this repo, above all the web client in services/web (submit a label, watch the run, read route + findings + citations + trace). Runs impeccable's Operate-mode flow, applies the taste-skill and Emil Kowalski design-engineering rules adapted to a working tool, React Bits for state-conveying micro-interactions, break-ui worst-case data, ECC accessibility, and a real-browser gate. Use whenever you touch services/web or any other screen, component, style or animation.
---

# FSSAI frontend

The web client is an **Operate** surface (impeccable's term): a regulatory analyst opens it to get
a job done, so it must read as a first-class working tool before it reads as anything else. The
sources and what each contributes:

| Source (in `skills/vendor/`) | What we take |
|---|---|
| `impeccable/skills/impeccable` | The flow (context, shape, craft floor, critique, audit, polish, harden), Operate mode, PRODUCT.md / DESIGN.md |
| `taste-skill/skills/minimalist-skill`, `redesign-skill`, `taste-skill` | The anti-slop house rules, the redesign audit, the real-browser `lint.mjs` / `inspect.mjs` gate |
| `emil-skills/skills/*` | Motion decisions, component feel, `break-ui`, `pick-ui-library`, the Before/After review table |
| `react-bits` (+ `skills/project/react-bits`) | A short allowlist of animated components that show agent state |
| `ecc/skills/frontend-a11y`, `react-patterns`, `react-testing`, `vite-patterns`, agents `react-reviewer`, `a11y-architect` | Accessibility, React structure, tests, build |
| `ponytail/skills/ponytail` | Smallest complete change; platform features before libraries |

`skills/project/fssai-workflow` still governs the overall loop (spec, tests, review, commit). This
skill is its UI branch.

## 1. Context

1. Read `services/web/PRODUCT.md` (who uses it, what job, constraints) and `services/web/DESIGN.md`
   (the committed tokens, type, components, signature move). Never contradict them silently; if a
   change needs a new decision, update `DESIGN.md` in the same commit.
2. If the impeccable launcher works (`skills/vendor/impeccable/skills/impeccable/scripts/impeccable context --target services/web`),
   use it. If it can't run, say so in one line and read the two files directly, as impeccable's own
   fallback says.
3. Data shapes come only from `contracts/fssai_contracts/schemas.py` (mirrored in
   `services/web/src/api/types.ts`). The HTTP surface is LLM_Context §7.

## 2. Shape before code

Write the screen down first, region by region (impeccable `reference/shape.md`, `operate.md`):

- **Shell:** product name, where the analyst is, the one primary action.
- **Work areas:** request input, run progress, result (route, findings, citations), trace.
- **Every state for each area:** empty, loading, success, partial (`complete=false`), error
  (422 with field errors, 429 with retry-after, network down), and escalation.
- **Content:** real FSSAI-shaped data. The §4.1 "source of protein" request is the canonical
  example. No lorem ipsum, no "John Doe", no invented statistics.

## 3. Craft floor (read `impeccable/.../reference/craft-floor.md` right before editing)

Verify, on the rendered page: contrast (body ≥ 4.5:1, large ≥ 3:1), spacing rhythm, type measure,
states (hover, focus, active, disabled, loading, error, empty), themed browser surfaces (selection,
caret, focus ring, scrollbars, tabular numerals), copy that names actions and recoveries, and
coverage (every requirement findable in seconds).

## 4. House rules for this app

Merged from taste-skill, impeccable and minimalist-skill, resolved for an Operate surface:

| Rule | Detail |
|---|---|
| Tokens only | Colour, type, space, radius, motion live as CSS custom properties in `src/styles/tokens.css`. Components never hard-code a hex value or a pixel size outside the scale. |
| One family, fixed rem scale | A well-tuned sans for everything, ratio about 1.2, no fluid headings. A monospace face is allowed **only** for data: clause ids, run ids, JSON, numbers in the trace. |
| Restrained colour | One ground, one ink, one accent for the primary action and selection. State colours carry meaning only: route and finding status. Never colour alone; always a text label too. |
| No slop | No gradients, glass, glows, emoji, eyebrow labels above headings, 01/02/03 numbering, icon-topped card rows, nested cards, gradient text, coloured thick side borders, Inter/Roboto defaults, AI copy clichés ("seamless", "elevate"). |
| Lines where they mean something | Tables, form fields and the trace may use 1px rules. Elsewhere separate with space and a tone step. |
| Real controls | Native `<button>`, `<input>`, `<select>`, `<details>`, `<dialog>`; labelled fields; visible focus; 44px touch targets. Use `vendor/emil-skills/skills/pick-ui-library` before adding a primitive library. |
| No modal as first thought | Inline disclosure first. |
| Phone is its own composition | Check 390px; nothing scrolls sideways except the trace table, inside its own container. |

**Domain rules (these are graded):**

- The notice "Compliance finding only. This is not an approval for print…" (`NOT_AN_APPROVAL` from the
  contracts) is always visible with a result. The UI never says or implies "approved".
- The route is a badge **with its words** (`clear-for-print`, `revise-and-recheck`,
  `regulatory-review`) and the reason next to it. An escalation reason is shown prominently, never hidden.
- Each citation shows regulation, clause id and the verbatim quote, with the quote visually marked as a quote.
- `complete=false` runs say plainly that the run did not complete and why.
- Label text is untrusted input (L4). Render it as text, never as HTML; no `dangerouslySetInnerHTML`.
- The trace view lists every step: agent, kind, name, latency, tokens, cost, prompt version, error.
- Runtime config (API base URL) comes from `/config.js`, never from a value baked into the bundle.

## 5. Motion (`vendor/emil-skills/skills/emil-design-eng`, `animate`, `review-animations`)

- Motion shows state, nothing else: a run moving from queued to running to done, a step finishing,
  a field error appearing. No page-load choreography; the analyst came to work.
- Durations 120–250ms; enter with a strong ease-out (`--ease-out: cubic-bezier(0.23, 1, 0.32, 1)`);
  never `ease-in`; never animate from `scale(0)`; buttons get `:active { transform: scale(0.97) }`.
- Animate `transform` and `opacity` (plus `clip-path`/`filter` where smooth). Never `transition: all`.
- Keyboard-triggered actions do not animate.
- Every animation has a `prefers-reduced-motion: reduce` path that keeps the content and drops the travel.

## 6. React Bits

Use only the components on the allowlist in `skills/project/react-bits/SKILL.md` (agent status,
tool-call chips, the reasoning-trace header, the loader row, number rolls). Each one must convey
state. Add them with `npm --prefix services/web run add:react-bits -- <Name>`, which pins the
upstream commit and keeps the licence header.

## 7. Gate (run all of it; report real output)

```bash
npm --prefix services/web run check          # tsc --noEmit + eslint + vitest + vite build
node skills/vendor/taste-skill/skills/taste-skill/scripts/lint.mjs services/web/src
node skills/vendor/taste-skill/skills/taste-skill/scripts/inspect.mjs http://localhost:5173 --allow mono,few-pictures
```

- `lint.mjs` and `inspect.mjs` come from the taste-skill and were written for landing pages (Node
  22+ and an installed Chrome/Edge). Fix every finding that also holds for a tool (contrast,
  overflow, headline length, gradients, shadows, emoji, small text). The two allowed rules are the
  ones that contradict §4 on purpose: `mono` (monospace is correct for clause ids, JSON and trace
  numbers) and `few-pictures` (a tool has no photographs). Any other landing-page-only finding
  (`no-hero`, `no-footage`, `no-real-pictures`) is noted in the report with one sentence why, never
  silently ignored. Never mark the whole app `data-ui` to hide it from the meter.
- Look at the screenshots at 1440, 768 and 390 yourself (Read tool or browser). If a problem is
  visible, it is real.
- Break it (`vendor/emil-skills/skills/break-ui`): a 400-character product name, 40 claims, zero
  findings, a quote with no spaces, a 422 with 12 field errors, a 429, the API down, a run stuck in
  `queued`.
- Keyboard only: tab through submit → result → trace; focus is always visible and in order.
- `npm run check` includes component tests for every state in §2 (`vendor/ecc/skills/react-testing`).

## 8. Critique, then fix

Critique the screenshots with `impeccable/.../reference/critique.md` (Operate lens). Report UI code
issues as Emil's table:

| Before | After | Why |
| --- | --- | --- |

Fix the top three, run §7 again. Three rounds at most. Then `impeccable … polish` and `harden`
checklists before the PR.

## 9. Report

Say what was built, which states were verified and how (commands and screenshots), what the gate
flagged and what you did about each finding, and anything left undone. Never claim a check you did
not run.
