"""FaissRetriever behaviour on the real corpus: filters, lookups, superseded text, the §4.1 passages."""
from __future__ import annotations

import pytest

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import Regulation
from fssai_retrieval.faiss_retriever import FaissRetriever
from fssai_retrieval.index import IndexNotBuilt, clause_contains, normalise_clause_id

AC, LD = Regulation.CLAIMS_2018, Regulation.LABELLING_2020
PROTEIN_ROW = "Schedule I, item 11"  # docs/eval1/section-4.1-passages.md, passage P1

# Three phrasings of the §4.1 question. None of them names Schedule I, or "RDA".
SECTION_41_QUERIES = [
    "source of protein claim condition",
    "The label carries the claim 'source of protein'. Is the claim permitted, given the protein content "
    "declared on the nutrition panel?",
    "what must a food meet before it can say it is a source of protein",
]


@pytest.fixture(scope="module")
def retriever(index_dir) -> FaissRetriever:
    return FaissRetriever(index_dir)


@pytest.fixture()
def ctx() -> RunContext:
    return RunContext.new()


def test_missing_index_says_how_to_build_it(tmp_path):
    with pytest.raises(IndexNotBuilt, match="fssai_ingest build"):
        FaissRetriever(tmp_path)


@pytest.mark.parametrize("query", SECTION_41_QUERIES)
def test_section_41_claim_condition_is_in_top_5(retriever, ctx, query):
    hits = retriever.search(query, ctx, k=5)
    assert any(h.regulation == AC and h.clause_id == PROTEIN_ROW for h in hits), [h.passage_id for h in hits]


@pytest.mark.parametrize("query", SECTION_41_QUERIES)
def test_section_41_condition_found_without_hints_too(index_dir, ctx, query):
    """The claim-trigger map is a hint, not the only way in: exact-term search alone reaches the row in the
    top 10 of the Claims regulation. (With the real embedding model, hybrid without hints gets it into the
    top 5: test_retrieval_quality.py.)"""
    plain = FaissRetriever(index_dir, hints=False, mode="bm25")
    hits = plain.search(query, ctx, k=10, regulation=AC)
    assert any(h.clause_id == PROTEIN_ROW for h in hits), [h.passage_id for h in hits]


def test_the_in_force_protein_condition_is_returned_not_the_superseded_one(retriever, ctx):
    hits = retriever.search("protein source RDA per 100 g solids", ctx, k=10, regulation=AC)
    rows = [h for h in hits if h.clause_id == PROTEIN_ROW]
    assert rows and all("superseded" not in h.passage_id for h in rows)
    assert "10% of RDA per 100 g for solids" in rows[0].text
    assert "or 5% of RDA per 100 kcal" in rows[0].text  # the row is not cut across the page break


def test_superseded_text_only_when_asked(index_dir, ctx):
    q = "sugars low not more than per 100 g for solids"
    default = FaissRetriever(index_dir).search(q, ctx, k=20, regulation=AC)
    assert all("superseded" not in h.passage_id for h in default)
    everything = FaissRetriever(index_dir, include_superseded=True).search(q, ctx, k=20, regulation=AC)
    assert any("superseded" in h.passage_id for h in everything)


def test_labelling_side_of_section_41(retriever, ctx):
    hits = retriever.search("declare protein in nutritional information per 100g", ctx, k=8, regulation=LD)
    assert hits and all(h.regulation == LD for h in hits)
    assert any(clause_contains("5(3)", h.clause_id) for h in hits), [h.passage_id for h in hits]


def test_regulation_filter_never_starves_k(retriever, ctx):
    for reg in (AC, LD):
        hits = retriever.search("label", ctx, k=7, regulation=reg)
        assert len(hits) == 7 and all(h.regulation == reg for h in hits)


@pytest.mark.parametrize("spelling", ["Schedule I, item 11", "schedule-I item 11", "Schedule I item no. 11",
                                      "SCHEDULE – I, Sl. No. 11"])
def test_clause_lookup_normalises_spelling(retriever, ctx, spelling):
    p = retriever.get_clause(AC, spelling, ctx)
    assert p is not None and p.clause_id == PROTEIN_ROW and "Protein" in p.text


def test_clause_lookup_returns_the_whole_clause(retriever, ctx):
    p = retriever.get_clause(LD, "5 (3)(c)", ctx)
    assert p is not None and p.clause_id == "5(3)(c)"
    assert "exempted from mandatory nutritional labelling" in p.text
    # the proviso that ends the exemption list: a claim brings nutrition labelling back
    assert "nutritional information shall be required in the above -mentioned products if a nutrition or " \
           "health claim is made on the label" in p.text
    assert "Unprocessed products that comprise a single ingredient" not in p.text  # superseded item left out


def test_clause_lookup_finds_a_sub_clause_inside_a_merged_chunk(retriever, ctx):
    """Regulation 9 fits one chunk; 9(2) is still addressable, as a verbatim slice of that chunk."""
    p = retriever.get_clause(AC, "9(2)", ctx)
    assert p is not None and p.clause_id == "9(2)"
    assert p.text.startswith("(2) claims containing adjectives") and "Schedule V" in p.text
    whole = retriever.get_clause(AC, "9", ctx)
    assert p.text in whole.text and "(1) a claim may be made" not in p.text


def test_clause_lookup_is_exact(retriever, ctx):
    assert retriever.get_clause(AC, "Schedule I, item 99", ctx) is None
    assert retriever.get_clause(AC, "5(33)", ctx) is None
    assert retriever.get_clause(LD, "Schedule I, item 11", ctx) is None  # right clause, wrong regulation


def test_records_no_steps(retriever, ctx):
    retriever.search("protein", ctx)
    retriever.get_clause(AC, PROTEIN_ROW, ctx)
    assert ctx.steps == []


def test_normalise_clause_id():
    assert normalise_clause_id("5 (3) (c)") == normalise_clause_id("5(3)(c)") == normalise_clause_id("reg. 5(3)(c)")
    assert normalise_clause_id("Schedule II") != normalise_clause_id("Schedule I")
    assert clause_contains("5(3)", "5(3)(c)(i)") and not clause_contains("5(3)", "5(4)")
    assert clause_contains("Schedule I", "Schedule I, item 11") and not clause_contains("Schedule I", "Schedule II")


def test_reranker_reorders_the_head(index_dir, ctx):
    calls = []

    def prefer_protein(query, texts):
        calls.append(len(texts))
        return [1.0 if "Protein" in t else 0.0 for t in texts]

    r = FaissRetriever(index_dir, reranker=prefer_protein, rerank_top=10)
    hits = r.search("claim condition", ctx, k=3, regulation=AC)
    assert calls and len(hits) == 3


def test_reloads_when_the_index_is_rebuilt(index_dir, tmp_path, ctx):
    import shutil
    import time

    copy = tmp_path / "idx"
    shutil.copytree(index_dir, copy)
    r = FaissRetriever(copy)
    before = r.version
    manifest = copy / "index_manifest.json"
    manifest.write_text(manifest.read_text().replace(before, "rebuilt00000000"), encoding="utf-8")
    later = time.time() + 10
    import os

    os.utime(manifest, (later, later))
    r._last_check = 0
    r.search("protein", ctx)
    assert r.version == "rebuilt00000000"
