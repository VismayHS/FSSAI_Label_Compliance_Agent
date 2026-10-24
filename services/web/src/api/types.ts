// Mirror of contracts/fssai_contracts/schemas.py and services/api/app/models.py.
// A contract change must change this file too; the compiler then shows every screen it touches.

export type Route = "clear-for-print" | "revise-and-recheck" | "regulatory-review";
export type RunState = "queued" | "running" | "completed" | "failed";
export type Regulation = "FSS-LD-2020" | "FSS-AC-2018";
export type FindingStatus = "met" | "unmet" | "not_applicable" | "cannot_determine";
export type VerifyAction = "accept" | "retry" | "escalate";
export type StepKind = "llm" | "tool" | "guardrail" | "classification" | "verification" | "routing";
export type NetQuantityUnit = "g" | "kg" | "ml" | "l";
export type NutritionBasis = "per_100g" | "per_100ml";
export type VegStatus = "veg" | "non_veg" | "not_declared";

export interface PackageSpec {
  net_quantity: number;
  net_quantity_unit: NetQuantityUnit;
  principal_display_panel_cm2: number;
  total_surface_area_cm2?: number | null;
  pack_type?: string | null;
}

export interface NutritionPanel {
  basis: NutritionBasis;
  serving_size?: number | null;
  serving_unit?: "g" | "ml" | null;
  energy_kcal: number;
  protein_g: number;
  carbohydrate_g: number;
  total_sugars_g: number;
  added_sugars_g?: number | null;
  total_fat_g: number;
  saturated_fat_g?: number | null;
  trans_fat_g?: number | null;
  sodium_mg?: number | null;
  other?: Record<string, number>;
}

export interface LabelText {
  product_name: string;
  brand_name?: string | null;
  front_of_pack_text?: string;
  claims?: string[];
  ingredients?: string;
  allergen_statement?: string | null;
  veg_status?: VegStatus;
  fssai_licence_number?: string | null;
  manufacturer_name_address?: string | null;
  date_marking?: string | null;
  batch_or_lot?: string | null;
  other_text?: string | null;
}

export interface LabelCheckRequest {
  schema_version?: string;
  client_reference?: string | null;
  declared_category: string;
  package: PackageSpec;
  label: LabelText;
  nutrition: NutritionPanel;
}

export interface FieldError {
  loc: string;
  message: string;
  code: string;
}

export interface Passage {
  passage_id: string;
  regulation: Regulation;
  clause_id: string;
  heading_path: string[];
  text: string;
  doc_version: string;
  score: number | null;
}

export interface DetectedClaim {
  text: string;
  claim_type: string;
  nutrient: string | null;
}

export interface Classification {
  category: string;
  in_scope: boolean;
  claims: DetectedClaim[];
  rationale: string;
}

export interface Citation {
  regulation: Regulation;
  clause_id: string;
  passage_id: string;
  quote: string;
}

export interface Finding {
  requirement_id: string;
  requirement: string;
  status: FindingStatus;
  explanation: string;
  citations: Citation[];
}

export interface FindingCheck {
  requirement_id: string;
  supported: boolean;
  unresolved_citations: string[];
  reason: string;
}

export interface Verdict {
  action: VerifyAction;
  checks: FindingCheck[];
  retry_hint: string | null;
  escalation_reason: string | null;
}

export interface Routing {
  route: Route;
  reason: string;
  escalation_reason: string | null;
}

export interface GuardrailReport {
  stage: "input" | "output";
  allowed: boolean;
  flags: string[];
  detail: string;
}

export interface StepRecord {
  step_index: number;
  agent: string;
  kind: StepKind;
  name: string;
  started_at: string;
  latency_ms: number;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  prompt_name: string | null;
  prompt_version: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  error: string | null;
}

export interface RunTotals {
  steps: number;
  tool_calls: number;
  llm_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  latency_ms: number;
}

export interface RunResult {
  run_id: string;
  correlation_id: string;
  complete: boolean;
  routing: Routing;
  classification: Classification | null;
  findings: Finding[];
  verdict: Verdict | null;
  guardrails: GuardrailReport[];
  prompt_versions: Record<string, string>;
  steps: StepRecord[];
  totals: RunTotals;
  notice: string;
}

export interface RunStatus {
  run_id: string;
  state: RunState;
  submitted_at: string;
  updated_at: string;
  client_id: string | null;
  correlation_id: string | null;
  request: LabelCheckRequest | null;
  result: RunResult | null;
  error: string | null;
}

export interface AgentRollup {
  steps: number;
  tool_calls: number;
  llm_calls: number;
  errors: number;
  latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
}

export interface RunTrace {
  run_id: string;
  correlation_id: string | null;
  state: RunState;
  submitted_at: string;
  updated_at: string;
  queue_wait_ms: number | null;
  request: LabelCheckRequest | null;
  complete: boolean | null;
  classification: Classification | null;
  findings: Finding[];
  verdict: Verdict | null;
  routing: Routing | null;
  guardrails: GuardrailReport[];
  prompt_versions: Record<string, string>;
  totals: RunTotals | null;
  agents: Record<string, AgentRollup>;
  steps: StepRecord[];
  error: string | null;
  notice: string;
}

export interface RunSummary {
  run_id: string;
  state: RunState;
  submitted_at: string;
  updated_at: string;
  product_name: string | null;
  route: Route | null;
  complete: boolean | null;
}

export interface Readiness {
  ready: boolean;
  checks: Record<string, { ok: boolean; detail: string }>;
}

export const TERMINAL_STATES: ReadonlySet<RunState> = new Set(["completed", "failed"]);
