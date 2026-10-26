# 2026-10-25: chunker split Schedule I rows and invented a schedule

- **Author:** Nishkal · **Severity:** would have broken the §4.1 case (demo #10) silently; caught by inspection before any index was shared
- **Component:** `packages/ingest/fssai_ingest/chunker.py`

## What happened

The first dump of parsed units from the Claims compendium showed two wrong things:

1. **A phantom row.** Schedule I "2. Fat Low Not more than" was followed by a unit "Schedule I, item 3"
   whose text was "3 g of fat per 100 g for solids or 1.5 g of fat per 100ml for liquids". The fat
   condition had become a row of its own, and the real row 3 (Cholesterol) was swallowed into it. Every
   later row was shifted, so "item 11" was no longer guaranteed to be Protein.
2. **A phantom schedule.** In regulation 7, the line "Schedule – IIA.]" (the end of the sentence "…may
   be made as provided in Schedule – IIA.]") was taken as a schedule heading. Regulations 7(3) to 15
   were then parsed as if they were inside a schedule, so "12(1)(i)" came out as "Schedule IIA, (i)".

## How we noticed

By reading the unit dump (`clause_id` and the first 110 characters of every unit) against the PDF text
before building any index. The output looked plausible at a glance. Only reading row by row showed that
the conditions had moved.

## Cause

1. The row pattern accepted a number followed by any text, so "3 g of fat" matched "3" as the next
   expected row number. Row numbering is sequential, and 3 was indeed next.
2. The schedule-heading pattern accepted anything after "SCHEDULE – IIA", including the sentence's
   closing "]".

## Fix

1. A row number must be followed by a period ("11. Protein"), by a capitalised word ("1 Calcium", as in
   Schedule III), or stand alone. A unit such as "3 g" is condition text.
2. A schedule heading must be the whole line.
3. Later, a related guard: a line like "2. Above 100 to 500 4 3.5 8" (a table row inside a clause) is not
   accepted as regulation 2 when its title is mostly numbers.

Tests now pin these: `test_schedule_rows_hold_their_conditions_across_a_page_break` (synthetic), plus
`test_real_protein_row_is_whole_and_in_force` and `test_real_schedule_rows_each_start_with_their_number`
on the real PDFs. The last checks all 19 in-force Schedule I rows.

## Lesson

A parser for legal text can be wrong in ways that still look like legal text. Inspect its output against
the source before trusting any downstream metric. Recall@k would have stayed high with the shifted rows,
because the word "protein" was still in some chunk, while every citation pointed at the wrong row.
