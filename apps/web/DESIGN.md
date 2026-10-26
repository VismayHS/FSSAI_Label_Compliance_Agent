---
name: FSSAI Label Check
description: The analyst's workspace for checking a packaged-food label against FSSAI regulations; every status is a square pack mark.
colors:
  ink: "#14181c"
  ink-2: "#4a535c"
  ground: "#eef1ee"
  panel: "#ffffff"
  panel-2: "#f4f6f4"
  rule: "#c9cfc9"
  on-ink: "#ffffff"
  on-ink-2: "#c8cdd2"
  met: "#1a7f3c"
  unmet: "#b3261e"
  undet: "#8a5a00"
  na: "#5b6470"
  met-field: "#dcefe2"
  undet-field: "#f5e6c8"
  review-field: "#e4e6e8"
  path: "#1d4f91"
  path-wash: "#e3ebf6"
typography:
  display:
    fontFamily: "Archivo Variable, Archivo, system-ui, sans-serif"
    fontSize: "2.75rem"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.02em"
    fontVariation: "\"wdth\" 78"
  headline:
    fontFamily: "Archivo Variable, Archivo, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.2
    fontVariation: "\"wdth\" 88"
  title:
    fontFamily: "Archivo Variable, Archivo, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 700
    lineHeight: 1.2
    fontVariation: "\"wdth\" 88"
  wordmark:
    fontFamily: "Archivo Variable, Archivo, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 800
    letterSpacing: "-0.01em"
    fontVariation: "\"wdth\" 78"
  section:
    fontFamily: "Archivo Variable, Archivo, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 800
    fontVariation: "\"wdth\" 80"
  body:
    fontFamily: "Archivo Variable, Archivo, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Archivo Variable, Archivo, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    fontVariation: "\"wdth\" 82"
  meta:
    fontFamily: "Archivo Variable, Archivo, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
  data:
    fontFamily: "JetBrains Mono Variable, JetBrains Mono, ui-monospace, monospace"
    fontSize: "0.8125rem"
    fontWeight: 400
    fontFeature: "\"tnum\" 1"
  data-total:
    fontFamily: "JetBrains Mono Variable, JetBrains Mono, ui-monospace, monospace"
    fontSize: "1.25rem"
    fontWeight: 600
    fontFeature: "\"tnum\" 1"
rounded:
  none: "0px"
spacing:
  s-1: "4px"
  s-2: "8px"
  s-3: "12px"
  s-4: "16px"
  s-5: "24px"
  s-6: "32px"
  s-7: "48px"
components:
  header-shell:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
    typography: "{typography.wordmark}"
    padding: "0 32px"
    height: "56px"
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
    rounded: "{rounded.none}"
    padding: "0 24px"
    height: "44px"
  button-primary-hover:
    backgroundColor: "#2b3138"
  button-primary-disabled:
    backgroundColor: "{colors.na}"
    textColor: "{colors.on-ink}"
  button-link:
    textColor: "{colors.path}"
    typography: "{typography.label}"
    height: "44px"
  input-field:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "8px 12px"
    height: "40px"
  input-json:
    backgroundColor: "{colors.panel-2}"
    typography: "{typography.data}"
  nutrition-title:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
    typography: "{typography.section}"
    padding: "8px 12px"
  filter-toggle:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0 12px"
    height: "40px"
  filter-toggle-off:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink-2}"
  tab:
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
    height: "44px"
  tab-selected:
    textColor: "{colors.ink}"
  decl-route-clear:
    backgroundColor: "{colors.met-field}"
    textColor: "{colors.ink}"
    typography: "{typography.display}"
  decl-route-revise:
    backgroundColor: "{colors.undet-field}"
    textColor: "{colors.ink}"
    typography: "{typography.display}"
  decl-route-review:
    backgroundColor: "{colors.review-field}"
    textColor: "{colors.ink}"
    typography: "{typography.display}"
  agent-strip:
    backgroundColor: "{colors.panel-2}"
    padding: "16px 16px 12px"
  quote:
    backgroundColor: "{colors.panel-2}"
    textColor: "{colors.ink}"
    padding: "12px 16px"
  mark:
    size: "20px"
    rounded: "{rounded.none}"
  mark-strip:
    size: "24px"
  mark-route:
    size: "28px"
---

# Design System: FSSAI Label Check

## Overview

**Creative North Star: "The Pack Mark System"**

Every status in a check is a square pack mark, taken from the mandatory marks printed on Indian food packs: an outlined square with one inner symbol, always next to words. The interface is a printed pack, not a dashboard. Ink header, a pale grey-green ground, white print panels, ruled tables, condensed bold labels. There are no pills, no cards in cards, no shadows and no gradients. Depth comes from rules and frames.

Density is high on purpose. The analyst compares requirements, clauses and quoted words, so findings share one grid and one baseline, and the trace reads as a ledger. Ink-blue is the only non-status hue. It marks where you are and where the run went: the agent path, the trace spine, the running mark, focus, links and the selected tab.

**Key Characteristics:**
- Square marks for every state (findings, routes, stages, steps, API readiness, recent runs), never colour alone.
- A ruled declaration block opens every result: 2px ink frame, 1px ink rules, labels on the left.
- One family (Archivo Variable), with the width axis doing the hierarchy work; JetBrains Mono only for data.
- Zero radius everywhere, flat at rest, state changes restyle in place.

## Colors

The palette is ink on grey-green paper, plus four status inks, their pale field tints and one reserved blue.

### Primary
- **Ink** (`ink`): header band, primary button, nutrition panel title, frames and rules of the declaration block, the regulatory-review mark. Every surface's text.
- **Path Blue** (`path`): the active run and its path. Stage connectors on the agent strip (3px), the step spine in the trace (3px), the running mark, focus ring, input focus border, selected tab underline, links, `button-link`, caret and native `accent-color`.
- **Path Wash** (`path-wash`): text selection only.

### Secondary: status inks (marks and status words)
| Token | State | Mark symbol | Contrast note (tokens.css) |
|---|---|---|---|
| `met` | met, done, clear-for-print | filled inner square (50%) | 5.1:1 |
| `unmet` | unmet, error | cross (two 2px bars at 45 deg, 70%) | 6.0:1 |
| `undet` | cannot determine, revise-and-recheck | half fill (lower-left triangle) | 5.3:1 |
| `na` | not applicable, skipped | dash (60% x 2px) | 5.9:1 |
| `ink` | regulatory-review | hollow inner square, 2px | |
| `path` | running | inner square breathing | |
| `rule` | pending | empty outline | |

### Tertiary: status fields (whole areas behind ink text, ink on each > 12:1)
| Token | Where |
|---|---|
| `met-field` | declaration route row, route `clear-for-print` |
| `undet-field` | declaration route row, route `revise-and-recheck` |
| `review-field` | declaration route row, route `regulatory-review`; neutral grey so blue stays reserved |

### Neutral
| Token | Role |
|---|---|
| `ground` | page background, scrollbar track |
| `panel` | print panels, inputs, filter toggles |
| `panel-2` | one tone step: quotes, code blocks, JSON textarea, agent strip, row hover, segment track |
| `rule` | 1px hairlines (`--line`), input borders, off filter border, scrollbar thumb |
| `ink-2` | secondary text, hints, meta, units, unselected tabs (7.7:1 on white) |
| `on-ink` / `on-ink-2` | text on the ink header and nutrition title: active / inactive |

### Named Rules
**The One Blue Rule.** `path` means position and movement: the run's path, focus, links, the selected tab. It is never a status colour and never a field tint.

**The Words With Marks Rule.** A state colour never appears without its mark shape and its word (finding status text, stage label plus a visually hidden state, route name).

## Typography

**Display / Body Font:** Archivo Variable (`@fontsource-variable/archivo/wdth.css`, the width axis is loaded), fallback Archivo, system-ui.
**Data Font:** JetBrains Mono Variable, fallback ui-monospace.

**Character:** a grotesque that condenses like pack print. The `wdth` axis, set with `font-stretch`, separates labels from values, so size can stay small.

### Hierarchy
Fixed rem scale, ratio about 1.2: `--t-xs` 0.8125rem, `--t-sm` 0.875rem, `--t-md` 1rem, `--t-lg` 1.25rem, `--t-xl` 1.5rem.

| Role | Values | Used for |
|---|---|---|
| Display | 800, 2.75rem, lh 1, -0.02em, stretch 78% | route name in the declaration block; empty-state heading (max 16ch). 1.875rem (route) / 2.125rem (empty heading) at 720px and below |
| Headline | 700, `--t-xl`, lh 1.2, stretch 88% | run title (product name) |
| Title | 700, `--t-lg`, stretch 88% | panel headings, §4.1 example heading |
| Wordmark | 800, `--t-lg`, stretch 78%, -0.01em | "FSSAI Label Check" in the header |
| Section | 800, `--t-md`, stretch 80% | fieldset legends (under a 1px ink rule), nutrition title |
| Body | 400, `--t-md`, lh 1.5 | text; notice 600, max 72ch; finding body max 72ch |
| Label | 600, `--t-sm`, stretch 82% (`--stretch-label`) | field labels; 700 for declaration and table heads |
| Meta | 400, `--t-xs` | hints, run meta, stage meta, quote captions |
| Data | JetBrains Mono, `--t-xs`, tabular-nums | requirement ids, clause refs, regulation codes, run and correlation ids, JSON, prompt versions, trace step metrics |
| Data total | JetBrains Mono 600, `--t-lg`, tabular-nums | trace totals values |

Headings use `text-wrap: balance`, paragraphs `text-wrap: pretty`. Numbers outside mono use `.num` (tabular-nums).

### Named Rules
**The Width Not Weight Rule.** Labels are told apart by condensed width (78-88%), not by uppercase, tracking or colour.

**The Mono Is Data Rule.** JetBrains Mono only for literal data: ids, clause references, JSON, trace numbers and the loader timer. Never for labels or prose.

## Layout

| Rule | Value |
|---|---|
| Spacing | 4px base, 8px grid: `--s-1` 4 to `--s-7` 48 |
| Header | flex, min-height 56px, padding 0 `--s-6`, gap `--s-6`; API status pushed right, max 34ch, ellipsis |
| Workspace | grid `minmax(360px, 440px) minmax(0, 1fr)`, gap `--s-5`, max-width 1600px, padding `--s-5 --s-6 --s-7` |
| Panels | padding `--s-5`; children stacked with `--s-4` |
| Label fields | 2 columns, gap `--s-3`; textareas span both |
| Package | `1fr 96px 1fr` |
| Findings row | `20px 11rem minmax(0, 1fr) 8.5rem`: mark, id, body, status (right-aligned) |
| Agent strip | 6 equal columns, gap `--s-3` |
| Trace totals | 7 columns under a 4px ink rule |
| Step rows | 6 tracks `20px 2rem minmax(0, 1fr) 4.5rem 6.5rem 5.5rem`, areas `mark idx name lat tok cost`; a second row puts `meta` (kind · prompt) under the name; no min-width, no sideways scroll; head row and every summary share the template |
| Declaration labels | column 9.5rem |

### Responsive
| Breakpoint | Changes |
|---|---|
| `max-width: 1100px` | single column; the run panel moves above the request panel; totals 4 columns |
| `max-width: 720px` | totals 2 columns; header wraps, API status on its own line; layout padding `--s-4`, panel padding `--s-4`; label fields 1 column; package `1fr 88px` with the third field full width; declaration labels 6.5rem; route mark stacks above the route name; findings `mark 1fr auto` with body on row 2; agent strip 3 columns, the path breaks after every third stage; step detail loses its indent; steps head and index hidden, summary `20px minmax(0, 1fr) auto auto auto` on three lines (name, meta, then latency · tokens · cost) |

## Elevation & Depth

Flat. No `box-shadow` anywhere. Depth is made with rules, frames and one tone step.

| Device | Value | Where |
|---|---|---|
| Hairline | `1px solid var(--rule)` | table rows, inputs, totals cells |
| Ink rule | `1px solid var(--ink)` | declaration rows, legends, sticky action bar top, filter toggles |
| Frame | `2px solid var(--ink)` | declaration block, nutrition panel, §4.1 example, table heads |
| Heavy rule | `4px solid var(--ink)` | top of trace totals |
| Tone step | `panel-2` on `panel` | quotes, code, strip, hover |
| Knock-out | mark `outline: 4px` (strip) / `3px` (steps) in its background colour | cuts the blue path behind each mark |

### Named Rules
**The Rules Are The Grid Rule.** Structure is drawn with ink rules and frames, never with shadows or nested cards.

## Shapes

Square everything: `border-radius: 0` on inputs, selects, buttons, segment control (`radius={0}`) and marks. Marks are 20px squares with a 2px stroke (`--mark`), 24px on the agent strip, 28px with a 3px stroke for the route. Quotes take curly quote marks from CSS (`“ ”`).

## Components

### Header (readiness)
Ink band, wordmark, nav (New check, Recent runs, API docs). Nav links `on-ink-2`, 500; hover `on-ink`; current page 700 with a 2px `on-ink` underline. Readiness is a `role="status"` line with a mark: pending (checking), done (ready), error (unreachable or not ready, failing checks listed), polled every 15 s. Focus ring switches to `on-ink` inside the band.

### Request form
- **Head:** "Label to check" plus a Form | JSON segment (React Bits RubberSegment, track `panel-2`, thumb `ink`, active text `on-ink`).
- **Fields:** label 600 at 82% width; inputs 40px, 1px `rule`, hover border `ink-2`, focus border `path` plus 3px `path` ring; invalid border 2px `unmet` with a 600 `unmet` error line; hints `--t-xs` `ink-2`.
- **Nutrition table:** framed 2px ink like the printed panel; ink title bar "Nutritional information" with a per-basis select (ink on ink, `on-ink-2` border); rows of 36px right-aligned tabular inputs, 120px column.
- **JSON mode:** mono textarea on `panel-2`, `white-space: pre`.
- **Sticky actions:** `position: sticky; bottom: 0`, `panel` background, 1px ink top rule, bleeds to the panel edges. Primary "Check label", then link buttons "Load the §4.1 example" and "Clear". Busy label "Checking…"; disabled while rate limited, with a countdown in the banner.
- **Banners:** `panel-2` with a 2px tone border (ink, `unmet` error, `undet` warn), title in the tone colour; rejections list field errors with mono locations and the quarantine id. Focus moves to the banner.

### Buttons
| Variant | Default | Hover | Active | Disabled |
|---|---|---|---|---|
| Primary | `ink` fill, `on-ink` 700 `--t-md`, 44px, padding 0 24px | `--ink-hover` `#2b3138` | `scale(0.97)` | `na` fill, not-allowed |
| Link | `path` 600 `--t-sm`, 44px, underline transparent | underline `currentColor` | | |

### Declaration block
A fixed-layout table with a 2px ink frame and 1px ink rules (the row and column rules are the grid). Rows: Route, Reason, Escalation (bold, when present), Guardrails (mono flags, when present), Category (with in scope or "outside our corpus"), Claims (text plus type and nutrient in `ink-2`), Run (mono id, steps, latency, cost). The route row takes the route's field tint, `--s-4` block padding, a 28px mark, the route name in Display and its one-line help. The not-an-approval notice follows the block on every result, 600 weight. An incomplete run adds a warn banner.

### Agent stage strip
Six stages in contract order (Guardrails, Classifier, Researcher, Verifier, Router, Output filter) on `panel-2`, each a 24px mark, a 700 label at 85% width and a meta line (role while waiting; step count, attempts and latency when done). Stages are joined by a 3px `path` line knocked out behind each mark. States: pending (empty outline), running (all marks breathing in `path`), done, error, skipped (label `ink-2`, 500).

### Tabs
Findings N | Trace · N steps | Request. 44px, 600 `--t-sm`, `ink-2`; hover `ink`; selected `ink` with a 3px `path` underline. Arrow keys move between tabs (roving tabindex); the trace tab is deep-linkable as `#/runs/<id>/trace`.

### Findings with filter toggles
- **Summary:** one toggle per status present, ordered unmet, cannot determine, met, not applicable: mark plus count plus word, 40px, 1px ink border, `panel` fill, hover `panel-2`, press `scale(0.97)`, `aria-pressed`. Off: dashed `rule` border, `ink-2` text, line-through, mark at 0.35 opacity. The verifier result sits right-aligned in `ink-2`.
- **Rows:** sorted most severe first, on the shared 4-column grid. Mono id, 700 title, explanation, then each citation as a `panel-2` quote figure (mono regulation · clause caption, verbatim quote). Status word right-aligned in its status colour. Missing citation or verifier rejection adds a 600 `unmet` warning line. If everything is filtered out, an empty line says how to undo it.

### Trace
- **Totals:** a `dl` of 7 cells under a 4px ink rule; labels `--t-xs` 600 at 82% width in `ink-2`; values Data total. Latency, steps, tool calls and LLM calls roll in with React Bits Counter (tabular).
- **Per-agent table:** captioned "By agent"; head 700 at 82% width over a 2px ink rule; 1px `rule` rows; tabular numbers.
- **Prompt versions:** mono `name@version` codes.
- **Step spine:** a head row and an `ol` of `details` rows on one template. A 3px `path` spine runs through the mark column, knocked out behind each mark (done or error). Head: #, "Step · agent, kind · prompt", Latency, Tokens, Cost. Summary line 1: index, mono step name with agent (700, 82%), right-aligned mono latency, tokens and cost. Line 2 (`--t-xs`): kind (`unmet` 700 with ", failed" on error) · mono prompt version. Hover `panel-2`. Detail: error banner, the query, returned passages (mono regulation and clause, score, full text) and a "Raw input and output" disclosure in `path` with JSON on `panel-2`, max 28rem.

### Waiting and empty states
Waiting: React Bits LatticeLoader (3x3 square cells, arrow pattern, `path` colour, no glow) with a mono timer and "Queued for a worker" or "Agents are checking the label", in a `role="status"` region.

### First-time guidance (plain words for someone new)
- **Empty run:** the Display heading; the demo notice (below); a three-step `ol.howto` (describe the label, press Check label, read the result; bold lead-in per step, max 68ch); the pending strip; the framed example ("Try the example", button "Check the example label"; §4.1 named once, in brackets); the route guide (`dl.route-guide`, a heading plus three columns of mark + route word + what it means, one column on phones); the never-approves notice.
- **Form:** a one-line `request__intro` under the panel heading says the form starts filled in and Clear empties it.
- **Result:** the route row is labelled *Recommendation* and its help line is this run's outcome in plain words (`whatItMeans`: how many requirements need attention, by title, and what to do; clear and review have their own sentences). The router's own text stays as *Reason given*. Each tab opens with a one-line `tabpanel__intro`. Findings carry a status legend (`dl.findings__legend`, `--t-xs`) and the verifier line reads "Quotes verified".
- **Strip:** each stage keeps its plain role ("finds the rules that apply") and, after a run, adds its step count and time on a 600-weight line (`strip__detail`). Stages align to the top (`align-content: start`).
- **Demo notice:** a `warn` banner (`role="note"`, text max 60ch), shown on the empty and result views whenever `/readyz` reports reasoning parts as stand-ins, naming them in plain words. It disappears by itself as real parts are switched on. Never hide it to make a demo look finished.
- **Header:** plain status words ("Service ready", "Service not ready: …"); the technical detail is in the tooltip.

### Recent runs
A table with route mark plus route (or state), product link, state (", incomplete" when `complete` is false), tabular time and a short mono id.

### Motion
State only, 120 to 250 ms, strong ease-out.

| Token / effect | Value | Use |
|---|---|---|
| `--ease-out` | `cubic-bezier(0.23, 1, 0.32, 1)` | marks, tabs, presses |
| `--ease-in-out` | `cubic-bezier(0.77, 0, 0.175, 1)` | the running mark's breathing |
| `--dur-1` / `--dur-2` / `--dur-3` | 120 / 200 / 250 ms | hover colour / mark and tab restyle / mark landing |
| mark-breathe | scale 0.4 to 1, opacity 0.35 to 1, 1.1s alternate infinite | running mark |
| mark-land | from scale 0.4 opacity 0, `--dur-3`, delay index x 60ms | strip marks complete in order when a result lands (crosses do not animate) |
| press | `scale(0.97)` at `--dur-1` | primary button, filter toggles |

**Reduced motion:** a global clamp sets animation and transition durations to 1ms and delays to 0; the running mark becomes a static filled square; the jump to a new run scrolls with `behavior: auto`; Counter, LatticeLoader and RubberSegment use their own reduced-motion handling.

### Accessibility
WCAG 2.2 AA. Status tokens are 5.1:1 or more on white; `ink-2` is 7.7:1; ink on each field tint is above 12:1. Focus is visible everywhere (3px `path` outline, offset 2px; `on-ink` in the header). There is a skip link. Marks are `aria-hidden`; meaning is carried by words, with visually hidden stage states. Readiness, waiting and the incomplete-run warning are `role="status"`; errors are `role="alert"`; a new run focuses its heading and a rejection focuses its banner. Tabs follow the ARIA tab pattern. Targets are 44px for buttons, tabs and link buttons, 40px for inputs and filter toggles. Off filters read without colour (dashed border plus line-through).

## Do's and Don'ts

### Do:
- **Do** give every status a square mark plus its word, using the kinds in Colors; add a new state as a new inner symbol, never as a new colour alone.
- **Do** open every result with the declaration block and follow it with the not-an-approval notice.
- **Do** keep findings and trace rows on one shared column template (`minmax(0, …)` tracks) so values compare down the column.
- **Do** take every colour, size, space and duration from `tokens.css`.
- **Do** render placeholder regulation text exactly as the API returns it, its `[PLACEHOLDER, NOT REAL REGULATION TEXT]` marker included.
- **Do** show `complete = false` runs as incomplete, with the reason.

### Don't:
- **Don't** render label text or any API text as HTML; it is untrusted input. ESLint bans `dangerouslySetInnerHTML` (`no-restricted-syntax`).
- **Don't** use the FSSAI logo or any official insignia; the brand is the wordmark only.
- **Don't** let any word, colour or mark read as approval. `clear-for-print` is a route, not a pass, and its help text says a professional still decides.
- **Don't** strip, restyle away or paraphrase the PLACEHOLDER marker in fake regulation text.
- **Don't** use `path` blue for a status or a field tint; `regulatory-review` uses the neutral `review-field`.
- **Don't** add shadows, gradients, rounded corners, pills or cards nested in cards.
- **Don't** set labels or prose in JetBrains Mono.
- **Don't** edit the vendored React Bits components beyond token mapping; theme them through props and tokens.
