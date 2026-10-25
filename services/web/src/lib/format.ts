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

/** What each recommendation means for the analyst, before any run (the route guide). */
export const ROUTE_MEANING: Record<string, string> = {
  "clear-for-print": "Every requirement it checked is met and every quote matched the regulation text. A regulatory professional still signs off.",
  "revise-and-recheck": "Something on the label does not meet a requirement, or the label lacks the information to tell. Fix it, then check again.",
  "regulatory-review": "The system could not answer with confidence (for example a conflict, a possible exemption, or an unsupported answer), so a professional decides. It never guesses.",
};

/** What each finding status means, in plain words (the legend under the filters). */
export const STATUS_MEANING: Record<string, string> = {
  unmet: "the label does not meet the requirement",
  cannot_determine: "the label lacks the information to tell",
  met: "the label meets it",
  not_applicable: "it does not apply to this product",
};

export const STATUS_WORD: Record<string, string> = {
  met: "Met",
  unmet: "Unmet",
  cannot_determine: "Cannot determine",
  not_applicable: "Not applicable",
};
