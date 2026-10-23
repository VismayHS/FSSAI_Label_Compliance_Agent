# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React + Vite + TypeScript, plain CSS with design tokens, React Bits (TS + CSS flavor) for run-state
motion. Served as static files; the API is reached at same-origin `/v1`. Decision record
`docs/decisions/303-vismay-web-client-stack.md`.

## Users

- **Regulatory affairs analyst** at a packaged-food manufacturer, checking a proposed label before it
  goes to print. Desk work on a laptop or large monitor, often with the label artwork and the
  regulation PDFs open beside it. Needs a clear finding per requirement, the exact clause and words it
  rests on, and a route. Decides themselves; the tool never decides for them.
- **Examiners and the team at the live demo** (confirmed second audience): need to see, one click from
  the result, how the run got there: every agent step, tool call, query, passage, prompt version,
  latency and cost (demo items 2, 3, 5–8, 10).

## Product Purpose

FSSAI Label Check takes a proposed packaged-food label (as text) and its package specification, checks
it against the FSSAI Labelling & Display Regulations 2020 and the Advertising & Claims Regulations 2018,
and returns a compliance finding for each requirement with citations to regulation and clause, routed
to `clear-for-print`, `revise-and-recheck` or `regulatory-review` with a reason. Success: the analyst
can act on the result (fix, recheck, or escalate) without re-reading the regulations, and can verify
every statement against its quoted source.

## Positioning

It follows a claim into the regulation that governs it even when the labelling rules never point there
(a "source of protein" claim is conditioned by the Claims regulation), verifies every citation
against text it actually retrieved, and escalates instead of guessing.

## Operating Context

- Input: the label's text fields, claims as printed, the nutrition panel and pack details; never images.
- The run takes tens of seconds; the client polls a run id.
- A rejected request returns field-level errors and a quarantine id; a busy client is rate limited.
- The canonical test is spec §4.1: "The label carries the claim 'source of protein'. Is the claim
  permitted, given the protein content declared on the nutrition panel?"

## Capabilities and Constraints

- Submit as a form or as raw JSON (`LabelCheckRequest`), load the §4.1 example, see validation errors
  per field, watch the run state, read route + reason + escalation, findings with citations and quotes,
  classification and detected claims, guardrail flags, and the full step trace.
- Must show: the notice "Compliance finding only. This is not an approval for print; a regulatory
  affairs professional decides." with every result. Nothing in the UI may read as an approval.
- Must show incomplete runs (`complete = false`) as incomplete, with the reason.
- Label text is untrusted input: always rendered as text.
- Terminology: route names exactly `clear-for-print`, `revise-and-recheck`, `regulatory-review`;
  regulations as `FSS-LD-2020` and `FSS-AC-2018`.
- Until the corpus lands (Nishkal) the API runs on fakes whose regulation text is marked PLACEHOLDER;
  the UI shows that text as it comes.

## Brand Commitments

- Name: **FSSAI Label Check** (confirmed). No logo exists; a wordmark only.
- No FSSAI logo or official insignia: this is not an FSSAI product.

## Evidence on Hand

- The spec (`docs/MiniProject_10_Food_Label_Compliance.pdf`), the contracts, and the §4.1 example
  request. No real customer data, testimonials or statistics exist; none may be invented.

## Product Principles

1. The analyst decides. Present evidence and a route, never a verdict of approval.
2. Every statement is checkable: clause id and verbatim quote are always one glance away.
3. Escalation is a first-class outcome, shown as clearly as a pass.
4. Show the work: the trace is part of the product, not a debug page.

## Accessibility & Inclusion

WCAG 2.2 AA: contrast, full keyboard operation, visible focus, status changes announced to screen
readers, reduced-motion support, state never conveyed by colour alone.
