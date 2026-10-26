"""The clause-aware chunker (decision 002): synthetic pages for each rule, then the real corpus."""
from __future__ import annotations

from pathlib import Path

import pytest

from fssai_ingest.chunker import chunk_document, parse_units
from fssai_ingest.pdftext import page_texts

CORPUS = Path(__file__).resolve().parents[3] / "data" / "corpus" / "raw"
AC_PDF = CORPUS / "FSS-AC-2018_compendium_2021-11-16.pdf"
LD_PDF = CORPUS / "FSS-LD-2020_compendium.pdf"


def units(*pages: str, reg: str = "FSS-AC-2018"):
    return {(u.clause_id, u.status, u.amendment): u for u in parse_units(reg, list(pages))}


def ids(*pages: str, reg: str = "FSS-AC-2018") -> list[str]:
    return [u.clause_id for u in parse_units(reg, list(pages))]


# ------------------------------------------------------------------ structure

def test_regulations_and_nested_markers():
    page = """Version –II (16.11.2021)
1. Short title.- (1) These regulations may be called X.
(2) They shall come into force on publication.
2. Definitions – (1) In these regulations,-
(a) “Act” means the Act;
(b) “claim” means any representation which-
(i) is printed; or
(ii) is oral;
(c) “fat” means total lipids."""
    assert ids(page) == ["1", "1(1)", "1(2)", "2", "2(1)", "2(1)(a)", "2(1)(b)", "2(1)(b)(i)", "2(1)(b)(ii)", "2(1)(c)"]


A_TO_G = "\n".join(f"({c}) “term {c}” means something;" for c in "abcdefg")


def test_letter_i_versus_roman_i():
    """(i) after (h) is the letter i, unless (h) ends with a lead-in, where it opens a roman list."""
    page = f"""2. Definitions.- (1) In these regulations,-
{A_TO_G}
(h) “health claim” means any representation, namely: -
(i) “nutrient function claim” is one thing;
(ii) “other function claim” is another;
(i) “marketer” refers to persons;
(j) “nutrient” means a constituent."""
    assert ids(page)[9:] == ["2(1)(h)", "2(1)(h)(i)", "2(1)(h)(ii)", "2(1)(i)", "2(1)(j)"]


def test_letter_i_after_a_plain_h_is_a_letter():
    page = f"2. Definitions.- (1) In these regulations,-\n{A_TO_G}\n(h) “catering” means food served;\n(i) “Front of Pack” means the front."
    assert ids(page)[-2:] == ["2(1)(h)", "2(1)(i)"]


def test_out_of_sequence_markers_and_references_stay_text():
    page = """5. Rules.- (1) Apply these:
(a) the first;
(vi) printed out of order;
(b) declarations under 1.1 (1),
(2), (3) and 1.9 of schedule II;
(2) The second."""
    got = parse_units("FSS-AC-2018", [page])
    assert [u.clause_id for u in got] == ["5", "5(1)", "5(1)(a)", "5(1)(b)", "5(2)"]
    assert "(vi) printed out of order" in got[2].text and "(2), (3) and 1.9" in got[3].text


def test_regulation_numbers_must_be_in_sequence():
    page = """1. First.- (1) Text with a table:
1. Upto 100 3 2.5 6
2. Above 100 to 500 4 3.5 8
2. Second.- (1) More."""
    assert ids(page) == ["1", "1(1)", "2", "2(1)"]


# ------------------------------------------------------------------ amendments

def test_substitution_supersedes_the_original_and_its_sub_clauses():
    page = """5. Claims.- (1) Old first.
(a) old a;
(b) old b;
Substitution of highlighted provision
(1) New first.
(a) new a;
[Operationalized w.e.f. 26th October, 2021 vide Direction: F. No.1-94,
FBOs to comply with the provisions by 1st July, 2022]
(2) Untouched second."""
    got = parse_units("FSS-AC-2018", [page])
    status = {(u.clause_id, u.amendment): u.status for u in got}
    assert status[("5(1)", None)] == status[("5(1)(a)", None)] == status[("5(1)(b)", None)] == "superseded"
    assert status[("5(1)", "substituted")] == status[("5(1)(a)", "substituted")] == "in_force"
    assert status[("5(2)", None)] == "in_force"
    new = next(u for u in got if u.amendment == "substituted")
    assert "26th October, 2021" in new.effective and "1st July, 2022" in new.effective


def test_omission_supersedes_the_unit_before_it():
    page = """5. Exempt.- (1) The following are exempt:
(i) item one;
(ii) item two;
Omission of highlighted provision
[Re-operationalized w.e.f. 1st Jan,2023 vide Direction]
(iii) item three;"""
    got = {u.clause_id: u for u in parse_units("FSS-LD-2020", [page])}
    assert got["5(1)(ii)"].status == "superseded" and got["5(1)(ii)"].effective.startswith("Omitted")
    assert got["5(1)(i)"].status == got["5(1)(iii)"].status == "in_force"


def test_words_only_amendment_is_a_partial_unit_on_the_same_clause():
    page = """14. Procedure.- (1) First.
(2) Second.
(3) Submit within thirty days from the issue of the letter.
Substitution of highlighted words
date of receipt of letter seeking clarification.
[Operationalized w.e.f. 26th October, 2021]
(4) After scrutiny."""
    got = parse_units("FSS-AC-2018", [page])
    partial = [u for u in got if u.amendment == "partial"]
    assert len(partial) == 1 and partial[0].clause_id == "14(3)" and partial[0].status == "in_force"
    assert next(u for u in got if u.clause_id == "14(3)" and not u.amendment).status == "in_force"
    assert got[-1].clause_id == "14(4)"


def test_text_after_a_replaced_unit_belongs_to_the_parent_clause():
    page = """5. Labels.- (1) Nutrition.-
(a) Definitions apply.
(b) Declare per 100 g.
(c) The following foods are exempted:
(i) one;
(ii) old two;
Substitution of highlighted provision
(ii) new two;
[Re-operationalized w.e.f. 1st Jan,2023]
However, nutritional information shall be required if a claim is made.
(d) Tolerance."""
    got = parse_units("FSS-LD-2020", [page])
    proviso = next(u for u in got if "nutritional information shall be required" in u.text)
    assert proviso.clause_id == "5(1)(c)" and proviso.status == "in_force"
    assert got[-1].clause_id == "5(1)(d)"


# ------------------------------------------------------------------ schedules

SCHEDULE_PAGE_1 = """SCHEDULE – I
[See regulation 5 (3)]
Nutrient Content Claim
A claim may be made subject to the conditions in column (4):
(1) (2) (3) (4)
Sl. No Nutrient/
component
Claim Conditions
1.
Energy Low Not more than
40 kcal per 100 g
2. Fat Low Not more than
3 g of fat per 100 g for solids or
1.5 g of fat per 100ml for liquids.
3. Protein Source
10% of RDA per 100 g for solids"""
SCHEDULE_PAGE_2 = """Version –II (16.11.2021)
(1) (2) (3) (4)
Sl. No Nutrient/
component
Claim Conditions
or 5% of RDA per 100 kcal
4. Sodium Low Not more than 0.12 g
Note: Health supplements are governed by other regulations.
* To make these claims the nutrient must provide energy."""


def test_schedule_rows_hold_their_conditions_across_a_page_break():
    got = {u.clause_id: u for u in parse_units("FSS-AC-2018", [SCHEDULE_PAGE_1, SCHEDULE_PAGE_2])}
    assert list(got) == ["Schedule I", "Schedule I, item 1", "Schedule I, item 2", "Schedule I, item 3",
                         "Schedule I, item 4", "Schedule I, notes"]
    assert got["Schedule I, item 2"].text.endswith("1.5 g of fat per 100ml for liquids.")  # "3 g of fat" is not row 3
    protein = got["Schedule I, item 3"].text
    assert protein == "3. Protein Source 10% of RDA per 100 g for solids or 5% of RDA per 100 kcal"
    assert "Sl. No" not in protein  # the header repeated on page 2 is dropped
    assert "Health supplements" in got["Schedule I, notes"].text


def test_schedule_heading_carries_title_and_cross_reference():
    chunks = chunk_document("FSS-AC-2018", [SCHEDULE_PAGE_1, SCHEDULE_PAGE_2], doc_version="v", max_chars=120)
    (chunk,) = [c for c in chunks if c.clause_id == "Schedule I, item 3"]
    assert "Schedule I [See regulation 5 (3)]: Nutrient Content Claim" in chunk.heading_path[0]
    assert "columns:" in chunk.heading_path[0]
    assert chunk.embed_text.startswith("Food Safety and Standards (Advertising and Claims) Regulations, 2018")
    assert chunk.embed_text.endswith(chunk.text)


# ------------------------------------------------------------------ chunks

def test_small_regulation_is_one_chunk_with_addressable_sub_clauses():
    page = "9. Conditional Claims.- (1) a claim may be made if natural.\n(2) claims with adjectives need Schedule V."
    (chunk,) = chunk_document("FSS-AC-2018", [page], doc_version="v")
    assert chunk.clause_id == "9" and chunk.passage_id == "FSS-AC-2018:9"
    start, end = chunk.extra["subclauses"]["9(2)"]
    assert chunk.text[start:end] == "(2) claims with adjectives need Schedule V."


def test_big_clause_splits_into_sub_clauses_and_never_crosses_one():
    items = "\n".join(f"({chr(97 + i)}) " + "word " * 60 + ";" for i in range(6))
    page = f"5. Big.- (1) Lead in:\n{items}\n(2) Next."
    chunks = chunk_document("FSS-AC-2018", [page], doc_version="v", max_chars=400)
    # "5. Big.-" and "(1) Lead in:" are bare headings: kept in the sub-clauses' heading_path, not as chunks
    assert [c.clause_id for c in chunks] == [*(f"5(1)({chr(97 + i)})" for i in range(6)), "5(2)"]
    assert all(len(c.text) <= 400 for c in chunks)
    assert chunks[0].heading_path == ["Regulation 5: Big", "(1) Lead in:"]


def test_oversized_single_clause_splits_into_parts():
    page = "5. Big.- (1) " + " ".join(f"Sentence {i} is here." for i in range(80))
    parts = [c for c in chunk_document("FSS-AC-2018", [page], doc_version="v", max_chars=300)
             if c.clause_id == "5(1)"]
    assert len(parts) > 2 and all(len(p.text) <= 300 for p in parts)
    assert [p.passage_id for p in parts] == [f"FSS-AC-2018:5(1)#p{n}" for n in range(1, len(parts) + 1)]


def test_superseded_and_amended_chunks_have_distinct_ids():
    page = """4. Principles.- (1) Claims must be truthful.
(2) Claims shall specify the number of servings of the food per day for the claimed benefit.
Substitution of highlighted provision
(2) Reduction of disease risk claims shall specify the number of servings per day.
[Operationalized w.e.f. 26th October, 2021]
(3) Next."""
    chunks = {c.passage_id: c for c in chunk_document("FSS-AC-2018", [page], doc_version="v")}
    assert chunks["FSS-AC-2018:4(2)~superseded"].status == "superseded"
    assert chunks["FSS-AC-2018:4(2)~substituted"].in_force
    assert "Substituted text now in force" in chunks["FSS-AC-2018:4(2)~substituted"].heading_path
    assert chunks["FSS-AC-2018:4(1)"].in_force and chunks["FSS-AC-2018:4(3)"].in_force


# ------------------------------------------------------------------ the real corpus

needs_corpus = pytest.mark.skipif(not AC_PDF.exists() or not LD_PDF.exists(), reason="corpus PDFs missing")


@pytest.fixture(scope="module")
def real_chunks():
    return {c.passage_id: c for reg, pdf in (("FSS-AC-2018", AC_PDF), ("FSS-LD-2020", LD_PDF))
            for c in chunk_document(reg, page_texts(pdf), doc_version="v")}


@needs_corpus
def test_real_protein_row_is_whole_and_in_force(real_chunks):
    row = real_chunks["FSS-AC-2018:Schedule I, item 11~substituted"]
    assert row.in_force and row.text == (
        "11. Protein Source 10% of RDA per 100 g for solids 5% of RDA per 100 ml for liquids or 5% of RDA per "
        "100 kcal Rich / High 20% of RDA per 100 g for solids 10% of RDA per 100 ml for liquids or 10% of RDA "
        "per 100 kcal")
    assert real_chunks["FSS-AC-2018:Schedule I, item 11~superseded"].status == "superseded"


@needs_corpus
def test_real_schedule_rows_each_start_with_their_number(real_chunks):
    rows = [c for c in real_chunks.values() if c.regulation == "FSS-AC-2018" and ", item " in c.clause_id
            and c.clause_id.startswith("Schedule I,") and c.in_force]
    assert len(rows) == 19
    for c in rows:
        n = c.clause_id.rsplit(" ", 1)[1]
        assert c.text.startswith(f"{n}. "), c.passage_id


@needs_corpus
def test_real_nutrition_exemption_proviso_is_in_force(real_chunks):
    proviso = [c for c in real_chunks.values() if "if a nutrition or health claim is made on the label" in c.text]
    assert proviso and all(c.in_force and c.clause_id == "5(3)(c)" for c in proviso)


@needs_corpus
def test_real_chunks_are_bounded_and_unique(real_chunks):
    assert len(real_chunks) > 300
    assert all(len(c.text) <= 1200 for c in real_chunks.values())
    for c in real_chunks.values():
        assert c.text and c.clause_id and c.doc_version
