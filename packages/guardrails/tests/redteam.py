"""Red-team scoring shared by the tests and the CI summary line (M3.1 extra: 30+ attacks, block rate in CI)."""
from pathlib import Path

import yaml

from fssai_contracts.conformance import sample_request
from fssai_contracts.context import RunContext
from fssai_guardrails.guardrails import Guardrails

FIXTURES = yaml.safe_load((Path(__file__).parent / "attacks.yaml").read_text(encoding="utf-8"))


def _request(field: str, text: str):
    return sample_request(claims=(text, "Source of protein")) if field == "claims" else sample_request(**{field: text})


def score(guardrails: Guardrails | None = None) -> dict:
    """Block rate over the attacks and false-positive rate over the clean label copy, plus the ids that failed."""
    g = guardrails or Guardrails()
    missed = [a["id"] for a in FIXTURES["attacks"]
              if g.screen_input(_request(a["field"], a["text"]), RunContext.new()).allowed]
    false_pos = [c["text"][:40] for c in FIXTURES["clean"]
                 if not g.screen_input(_request(c["field"], c["text"]), RunContext.new()).allowed]
    n_attacks, n_clean = len(FIXTURES["attacks"]), len(FIXTURES["clean"])
    return {"attacks": n_attacks, "blocked": n_attacks - len(missed), "missed": missed,
            "clean": n_clean, "false_positives": false_pos,
            "block_rate": (n_attacks - len(missed)) / n_attacks, "false_positive_rate": len(false_pos) / n_clean}
