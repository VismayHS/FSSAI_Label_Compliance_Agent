import type { CSSProperties } from "react";

import type { StepRecord } from "../api/types";
import { ms } from "../lib/format";
import { Mark, type MarkKind } from "./Mark";

/** The agreed hand-off order (contracts/fssai_contracts/pipeline.py), shown as marks on one path. */
const STAGES: { label: string; role: string; match: (s: StepRecord) => boolean }[] = [
  { label: "Guardrails", role: "checks the text is safe to read", match: (s) => s.agent === "guardrails" && s.name === "screen_input" },
  { label: "Classifier", role: "finds the category and claims", match: (s) => s.agent === "classifier" },
  { label: "Researcher", role: "finds the rules that apply", match: (s) => s.agent === "researcher" },
  { label: "Verifier", role: "checks every quote", match: (s) => s.agent === "verifier" },
  { label: "Router", role: "picks the recommendation", match: (s) => s.agent === "router" },
  { label: "Output filter", role: "makes sure nothing reads as approved", match: (s) => s.agent === "guardrails" && s.name === "filter_output" },
];

export interface Stage {
  label: string;
  role: string;
  kind: MarkKind;
  detail: string;
}

export function stageStates(steps: StepRecord[]): Stage[] {
  return STAGES.map(({ label, role, match }) => {
    const mine = steps.filter(match);
    if (mine.length === 0) return { label, role, kind: "skipped", detail: "not reached" };
    const failed = mine.filter((s) => s.error);
    const attempts = label === "Verifier" && mine.length > 1 ? `, ${mine.length} attempts` : "";
    const time = ms(mine.reduce((sum, s) => sum + s.latency_ms, 0));
    return failed.length
      ? { label, role, kind: "error", detail: `${failed.length} failed step${failed.length > 1 ? "s" : ""}${attempts}` }
      : { label, role, kind: "done", detail: `${mine.length} step${mine.length > 1 ? "s" : ""}${attempts} · ${time}` };
  });
}

export function AgentStrip({ steps, working }: { steps: StepRecord[] | null; working: boolean }) {
  const stages: Stage[] = steps ? stageStates(steps) : STAGES.map(({ label, role }) => ({ label, role, kind: "pending", detail: role }));
  return (
    <ol className="strip" aria-label="Agents in this run" data-working={working || undefined}>
      {stages.map((stage, i) => (
        <li key={stage.label} className="strip__stage" data-kind={stage.kind} style={{ "--i": i } as CSSProperties}>
          <Mark kind={working ? "running" : stage.kind} />
          <span className="strip__label">{stage.label}</span>
          <span className="strip__meta">{stage.role}</span>
          {steps && !working && <span className="strip__detail">{stage.detail}</span>}
          <span className="visually-hidden">{working ? ", waiting" : `, ${stage.kind}`}</span>
        </li>
      ))}
    </ol>
  );
}
