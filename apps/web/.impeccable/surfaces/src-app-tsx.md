---
version: 1
slug: "src-app-tsx"
primary_target: "src/App.tsx"
related_targets: ["index.html"]
---

# Surface: the analyst workspace (apps/web)

**Mode:** Operate. **Audience:** a regulatory affairs analyst checking a label before print; examiners at
the live demo reading the trace. **Job:** submit a label, read the route and reason, check each
requirement against its clause and quoted words, open the trace. **Constraints:** never imply approval;
the not-an-approval notice with every result; incomplete runs shown as incomplete; label text rendered
as text only; WCAG 2.2 AA. **Memorable moment:** when a result lands, the agent strip's marks complete
in order along the ink-blue path, then the declaration block shows the route.
**Unresolved:** live per-step progress needs a progress field from the API (today steps arrive with the
result); the reviewer console is a later surface.

## Direction contract

THESIS: Every status in the check is a square pack mark, the grammar of the mandatory marks printed on
every Indian food pack. It refuses the category default of coloured pills on cards in a grey dashboard.

OWN-WORLD: Ink header #14181C over a pale grey-green ground #EEF1EE with white print panels. Marks are
20px outlined squares, 2px stroke, one inner symbol per state: filled square met #1A7F3C, cross unmet
#B3261E, half-fill cannot-determine #8A5A00, dash not-applicable #5B6470. Results open with a ruled
declaration block: 2px ink frame, 1px ink rules, condensed bold labels. Archivo throughout, condensed
widths for labels; JetBrains Mono only for ids, clause references, numbers in the trace and JSON. No
gradients, shadows at rest, pills, nested cards.
Raise (Split-flap Concourse): state changes restyle marks and rows in place; nothing jumps out of the grid.
Raise (Botanical Folio): findings share one baseline and fixed columns so requirements compare at a glance.
Raise (Crouwel Grid Specimen): one construction grid; the declaration block's rules are the layout grid.
Raise (Orienteering Map): ink blue #1D4F91 is reserved for the active run and its path through the trace.

STORY: The analyst fills in or pastes the label and checks it; sees route and reason first, then every
requirement with its mark, clause and quoted words, and decides. The examiner opens the trace and reads
every agent step in order with its latency, tokens and cost.

FIRST VIEWPORT: 56px ink header: wordmark, New check, Recent runs, API docs, API status. Two columns:
left 440px request panel (Form | JSON switch, product, category, claims, allergen statement, nutrition
table under a heavy rule, Check label as the primary action, the §4.1 example link); right result panel:
declaration block (route mark and words, reason, category, claims, run), the notice, the agent strip of
six marks joined by the ink-blue path, tabs Findings | Trace | Request, finding rows on one 4-column grid.

FORM: Pack Mark System, position 6 of 7 on the ordered list. seed:e973f2a8fe706613

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
