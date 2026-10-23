"""Shared data shapes. Every module in the repo codes against these.

Change rules (see contexts/LLM_Context.md, "Shared contracts"):
- Additive changes only: new *optional* fields, new enum members.
- Renaming or removing anything needs a `contracts:` PR that the affected owners approve.
- These models describe *shape*. The strict ingestion rules (ranges, permitted
  categories, cross-field checks) live in the gate (libs/gate, owner: Vihaan).
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"

NOT_AN_APPROVAL = (
    "Compliance finding only. This is not an approval for print; "
    "a regulatory affairs professional decides."
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- enums

class Route(str, Enum):
    CLEAR_FOR_PRINT = "clear-for-print"
    REVISE_AND_RECHECK = "revise-and-recheck"
    REGULATORY_REVIEW = "regulatory-review"


class RunState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Regulation(str, Enum):
    LABELLING_2020 = "FSS-LD-2020"  # Labelling and Display Regulations, 2020
    CLAIMS_2018 = "FSS-AC-2018"     # Advertising and Claims Regulations, 2018


class FindingStatus(str, Enum):
    MET = "met"
    UNMET = "unmet"
    NOT_APPLICABLE = "not_applicable"
    CANNOT_DETERMINE = "cannot_determine"


class VerifyAction(str, Enum):
    ACCEPT = "accept"
    RETRY = "retry"
    ESCALATE = "escalate"


# ---------------------------------------------------------------- request (F1 / D1)

class PackageSpec(BaseModel):
    net_quantity: float
    net_quantity_unit: Literal["g", "kg", "ml", "l"]
    principal_display_panel_cm2: float
    total_surface_area_cm2: float | None = None
    pack_type: str | None = None  # e.g. "single", "multipack", "institutional"


class NutritionPanel(BaseModel):
    basis: Literal["per_100g", "per_100ml"]
    serving_size: float | None = None
    serving_unit: Literal["g", "ml"] | None = None
    energy_kcal: float
    protein_g: float
    carbohydrate_g: float
    total_sugars_g: float
    added_sugars_g: float | None = None
    total_fat_g: float
    saturated_fat_g: float | None = None
    trans_fat_g: float | None = None
    sodium_mg: float | None = None
    other: dict[str, float] = Field(default_factory=dict)


class LabelText(BaseModel):
    """Everything printed on the pack, as text. Free-text fields are untrusted (L4)."""
    product_name: str
    brand_name: str | None = None
    front_of_pack_text: str = ""
    claims: list[str] = Field(default_factory=list)  # claims exactly as printed
    ingredients: str = ""
    allergen_statement: str | None = None
    veg_status: Literal["veg", "non_veg", "not_declared"] = "not_declared"
    fssai_licence_number: str | None = None
    manufacturer_name_address: str | None = None
    date_marking: str | None = None
    batch_or_lot: str | None = None
    other_text: str | None = None


class LabelCheckRequest(BaseModel):
    schema_version: str = SCHEMA_VERSION
    client_reference: str | None = None
    declared_category: str
    package: PackageSpec
    label: LabelText
    nutrition: NutritionPanel


# ---------------------------------------------------------------- gate (F2 / D1 / D7)

class FieldError(BaseModel):
    loc: str       # dotted path, e.g. "nutrition.protein_g"
    message: str
    code: str      # e.g. "range", "type", "category", "cross_field", "missing"


class GateDecision(BaseModel):
    accepted: bool
    request: LabelCheckRequest | None = None
    errors: list[FieldError] = Field(default_factory=list)
    quarantine_id: str | None = None
    rate_limited: bool = False
    retry_after_s: float | None = None


# ---------------------------------------------------------------- retrieval (L1 / A1)

class Passage(BaseModel):
    passage_id: str
    regulation: Regulation
    clause_id: str                      # e.g. "2.2.1(3)" or "Schedule I, item 4"
    heading_path: list[str] = Field(default_factory=list)
    text: str
    doc_version: str
    score: float | None = None


# ---------------------------------------------------------------- agents (F3-F7, A2, A3)

class DetectedClaim(BaseModel):
    text: str
    claim_type: str = "other"           # e.g. "nutrient_content", "health", "other"
    nutrient: str | None = None         # e.g. "protein"


class Classification(BaseModel):
    category: str
    in_scope: bool                      # False -> F7 escalation (category outside corpus)
    claims: list[DetectedClaim] = Field(default_factory=list)
    rationale: str = ""


class Citation(BaseModel):
    regulation: Regulation
    clause_id: str
    passage_id: str
    quote: str                          # verbatim span of that passage's text (A3)


class Finding(BaseModel):
    requirement_id: str                 # stable id, e.g. "LBL-ALLERGEN", "CLM-PROTEIN-SOURCE"
    requirement: str
    status: FindingStatus
    explanation: str
    citations: list[Citation] = Field(default_factory=list)


class ResearchDossier(BaseModel):
    """Hand-off from the research agent to the verifier agent."""
    findings: list[Finding] = Field(default_factory=list)
    passages: list[Passage] = Field(default_factory=list)  # all retrieved text; citations must point here
    queries: list[str] = Field(default_factory=list)
    escalation_signals: list[str] = Field(default_factory=list)  # conflict / exemption / out of scope
    attempt: int = 1


class FindingCheck(BaseModel):
    requirement_id: str
    supported: bool
    unresolved_citations: list[str] = Field(default_factory=list)
    reason: str = ""


class Verdict(BaseModel):
    """Hand-off from the verifier agent back to the graph."""
    action: VerifyAction
    checks: list[FindingCheck] = Field(default_factory=list)
    retry_hint: str | None = None
    escalation_reason: str | None = None


class Routing(BaseModel):
    route: Route
    reason: str
    escalation_reason: str | None = None  # set when routed to a human because we could not answer


class GuardrailReport(BaseModel):
    stage: Literal["input", "output"]
    allowed: bool
    flags: list[str] = Field(default_factory=list)  # e.g. "prompt_injection:label.front_of_pack_text"
    detail: str = ""


# ---------------------------------------------------------------- LLM + prompts (A5 / L2 / L5)

class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMResponse(BaseModel):
    text: str
    model_alias: str          # an alias from env, never a provider model id written in code (D4)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    degraded: bool = False


class PromptTemplate(BaseModel):
    name: str
    version: str
    system: str
    user_template: str        # str.format() placeholders

    def render(self, **values: object) -> list[LLMMessage]:
        return [
            LLMMessage(role="system", content=self.system),
            LLMMessage(role="user", content=self.user_template.format(**values)),
        ]


# ---------------------------------------------------------------- runs (A4 / D5 / L5)

StepKind = Literal["llm", "tool", "guardrail", "classification", "verification", "routing"]


class StepRecord(BaseModel):
    step_index: int
    agent: str                # e.g. "classifier", "researcher", "verifier"
    kind: StepKind
    name: str                 # e.g. tool name or LLM step name
    started_at: datetime
    latency_ms: float = 0.0
    input: dict = Field(default_factory=dict)
    output: dict = Field(default_factory=dict)
    prompt_name: str | None = None
    prompt_version: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None


class RunTotals(BaseModel):
    steps: int = 0
    tool_calls: int = 0
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0


class RunResult(BaseModel):
    run_id: str
    correlation_id: str
    complete: bool                      # False -> never a confident answer (A5)
    routing: Routing
    classification: Classification | None = None
    findings: list[Finding] = Field(default_factory=list)
    verdict: Verdict | None = None
    guardrails: list[GuardrailReport] = Field(default_factory=list)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    steps: list[StepRecord] = Field(default_factory=list)
    totals: RunTotals = Field(default_factory=RunTotals)
    notice: str = NOT_AN_APPROVAL


class RunStatus(BaseModel):
    run_id: str
    state: RunState
    submitted_at: datetime
    updated_at: datetime
    client_id: str | None = None
    correlation_id: str | None = None
    # The accepted request, so a run can be reconstructed from its id alone (D5) and re-scored (L6).
    request: LabelCheckRequest | None = None
    result: RunResult | None = None
    error: str | None = None


# ---------------------------------------------------------------- feedback + eval (L3 / L6)

class Feedback(BaseModel):
    run_id: str
    satisfactory: bool
    reason: str
    submitted_at: datetime = Field(default_factory=utcnow)


class SupportingPassage(BaseModel):
    regulation: Regulation
    clause_id: str
    quote: str


class EvalScenario(BaseModel):
    """One line of eval/scenarios.jsonl."""
    scenario_id: str
    description: str
    tags: list[str] = Field(default_factory=list)  # e.g. "section-4.1", "escalation", "injection"
    request: LabelCheckRequest
    expected_route: Route
    expected_findings: dict[str, FindingStatus] = Field(default_factory=dict)
    supporting: list[SupportingPassage] = Field(default_factory=list)
