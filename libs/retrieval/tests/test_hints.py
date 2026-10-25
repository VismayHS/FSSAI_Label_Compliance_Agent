"""The claim-trigger map (corpus/claim_triggers.yaml): when it fires, and that every id it names exists."""
from __future__ import annotations

from pathlib import Path

import pytest

from fssai_contracts.context import RunContext
from fssai_contracts.schemas import Regulation
from fssai_retrieval.faiss_retriever import FaissRetriever
from fssai_retrieval.hints import ClaimHints

TRIGGERS = Path(__file__).resolve().parents[3] / "corpus" / "claim_triggers.yaml"


@pytest.fixture(scope="module")
def hints() -> ClaimHints:
    return ClaimHints.load(TRIGGERS)


def ids(refs):
    return [r.clause_id for r in refs]


def test_protein_claim_fires_the_protein_row_first(hints):
    assert ids(hints.match("Source of protein"))[0] == "Schedule I, item 11"
    assert "5(3)" in ids(hints.match("provides protein"))  # Schedule II synonym of "source"


def test_no_claim_word_no_hint(hints):
    assert hints.match("protein declared on the nutrition panel") == []
    assert hints.match("Contains wheat") == []  # an allergen statement, not a nutrient claim


def test_longer_nutrient_phrase_wins(hints):
    assert ids(hints.match("low saturated fat"))[0] == "Schedule I, item 4"
    assert "Schedule I, item 2" not in ids(hints.match("low saturated fat"))
    assert ids(hints.match("trans fat free"))[0] == "Schedule I, item 6"


def test_every_trigger_clause_exists_in_the_real_index(index_dir, hints):
    """The map must never name a clause the corpus does not have (AGENTS.md rule 4)."""
    r = FaissRetriever(index_dir)
    ctx = RunContext.new()
    for ref in hints.refs():
        p = r.get_clause(Regulation(ref.regulation), ref.clause_id, ctx)
        assert p is not None, f"{ref.regulation} {ref.clause_id} is not in the index"


@pytest.mark.parametrize("item,word", [(11, "Protein"), (14, "Dietary fibre"), (13, "Sodium"), (10, "Sugars"),
                                        (19, "Gluten")])
def test_schedule_rows_are_the_nutrients_the_map_says(index_dir, item, word):
    p = FaissRetriever(index_dir).get_clause(Regulation.CLAIMS_2018, f"Schedule I, item {item}", RunContext.new())
    assert p.text.startswith(f"{item}. {word}")
