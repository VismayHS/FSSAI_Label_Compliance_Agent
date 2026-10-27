"""Hand-built dossiers for the verifier and router tests (Vihaan.md V2.1: that is how unsupported answers are tested).

The FSS-AC-2018 texts are copied from the indexed corpus (data/corpus/raw/FSS-AC-2018_compendium_2021-11-16.pdf,
substituted Schedule I, as fssai_ingest extracts it), not written from memory.
"""
from __future__ import annotations

import json

from fssai_contracts.conformance import sample_request
from fssai_contracts.schemas import (
    Citation, Finding, FindingStatus, LabelCheckRequest, LLMResponse, Passage, Regulation, ResearchDossier,
)

PROTEIN_ROW = ("11. Protein Source 10% of RDA per 100 g for solids 5% of RDA per 100 ml for liquids or 5% of RDA per "
               "100 kcal Rich / High 20% of RDA per 100 g for solids 10% of RDA per 100 ml for liquids or 10% of RDA "
               "per 100 kcal")
FIBRE_ROW = ("14. Dietary fibre Source Product contains at least 3 g of fibre per 100 g or 1.5 g of fibre per 100 ml or "
             "1.5 g of fibre per 100kcal High Or Rich The product contains at least 6 g of fibre per 100 g or 3 g of "
             "fibre per 100 ml or 3 g of fibre per 100 kcal")
SUGARS_ROW = ("10. Sugars Low The product contains not more than 6 g of sugars per 100 g for solids or 2.5 g of sugars "
              "per 100 ml for liquids. Free The product contains not more than 0.5 g of sugars per 100 g for solids or "
              "100 ml for liquids.")
SODIUM_ROW = ("13. Sodium Low Product contains not more than 0.12 g of sodium per 100 g for solids or 100 ml for "
              "liquids. Very low Product contains not more than 0.04 g of sodium per 100 g for solids or 100 ml for "
              "liquids. Sodium free Product contains not more than 0.005g of sodium per 100 g for solids or 100 ml "
              "for liquids.")
TRANS_ROW = ("6. Trans fat Free The food contains less than 0.2g trans fat per 100 g or 100ml of food Provided that for "
             "edible oils/fats: 1 g per 100 g/ml of edible oils/fats")
ALLERGEN = ("(14) Declaration regarding Food allergen: The following foods and ingredients which are known to cause "
            "allergy shall be declared separately as Contains............................ (Name of allergy causing "
            "ingredients)")


def passage(pid: str, text: str, reg: Regulation = Regulation.CLAIMS_2018, clause: str | None = None) -> Passage:
    return Passage(passage_id=pid, regulation=reg, clause_id=clause or pid.split(":", 1)[-1], text=text,
                   doc_version="test")


SCHED = {
    "protein": passage("FSS-AC-2018:Schedule I, item 11~substituted", PROTEIN_ROW, clause="Schedule I, item 11"),
    "fibre": passage("FSS-AC-2018:Schedule I, item 14~substituted", FIBRE_ROW, clause="Schedule I, item 14"),
    "sugars": passage("FSS-AC-2018:Schedule I, item 10~substituted", SUGARS_ROW, clause="Schedule I, item 10"),
    "sodium": passage("FSS-AC-2018:Schedule I, item 13~substituted", SODIUM_ROW, clause="Schedule I, item 13"),
    "trans": passage("FSS-AC-2018:Schedule I, item 6~substituted", TRANS_ROW, clause="Schedule I, item 6"),
    "allergen": passage("FSS-LD-2020:5(14)", ALLERGEN, reg=Regulation.LABELLING_2020),
}


def cite(p: Passage, quote: str | None = None) -> Citation:
    return Citation(regulation=p.regulation, clause_id=p.clause_id, passage_id=p.passage_id,
                    quote=p.text if quote is None else quote)


def finding(rid: str, status: FindingStatus, *citations: Citation, requirement: str = "", explanation: str = "") -> Finding:
    return Finding(requirement_id=rid, requirement=requirement or rid, status=status,
                   explanation=explanation, citations=list(citations))


def dossier(*findings: Finding, passages: list[Passage] | None = None, signals: tuple[str, ...] = (),
            attempt: int = 1) -> ResearchDossier:
    return ResearchDossier(findings=list(findings), passages=list(SCHED.values()) if passages is None else passages,
                           escalation_signals=list(signals), attempt=attempt)


def request(claims: tuple[str, ...] = (), **nutrition) -> LabelCheckRequest:
    r = sample_request(claims=claims)
    return r.model_copy(update={"nutrition": r.nutrition.model_copy(update=nutrition)})


class ScriptedLLM:
    """Answers the support check with a fixed JSON reply and records its llm step like a real client."""

    def __init__(self, labels: dict[str, str] | None = None, raw: str | None = None) -> None:
        self.labels, self.raw, self.calls = labels or {}, raw, []

    def complete(self, messages, ctx, *, agent, step, prompt=None, json_mode=False):
        self.calls.append(messages)
        text = self.raw if self.raw is not None else json.dumps(
            {"checks": [{"requirement_id": k, "label": v, "reason": f"scripted {v}"} for k, v in self.labels.items()]})
        ctx.record(agent=agent, kind="llm", name=step, prompt_name=prompt.name if prompt else None,
                   prompt_version=prompt.version if prompt else None)
        return LLMResponse(text=text, model_alias="scripted")
