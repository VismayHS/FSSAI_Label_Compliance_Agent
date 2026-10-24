export function ms(value: number | null | undefined): string {
  if (value == null) return "—";
  return value < 1000 ? `${Math.round(value)} ms` : `${(value / 1000).toFixed(value < 10_000 ? 2 : 1)} s`;
}

export function usd(value: number | null | undefined): string {
  if (value == null) return "—";
  return `$${value.toFixed(value !== 0 && value < 0.01 ? 6 : 4)}`;
}

export function tokens(prompt: number, completion: number): string {
  return prompt + completion === 0 ? "—" : `${prompt.toLocaleString("en-IN")} + ${completion.toLocaleString("en-IN")}`;
}

export function time(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "medium" });
}

export function shortId(id: string): string {
  return id.slice(0, 8);
}

export const ROUTE_LABEL: Record<string, string> = {
  "clear-for-print": "All checked requirements met, citations verified. A professional still decides.",
  "revise-and-recheck": "Fix what is unmet, then check again.",
  "regulatory-review": "Needs a regulatory affairs professional to decide.",
};

export const STATUS_WORD: Record<string, string> = {
  met: "Met",
  unmet: "Unmet",
  cannot_determine: "Cannot determine",
  not_applicable: "Not applicable",
};
