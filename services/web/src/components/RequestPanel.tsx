import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { submitRun } from "../api/client";
import type { FieldError, LabelCheckRequest } from "../api/types";
import { clientId } from "../lib/clientId";
import { EMPTY_REQUEST, SECTION_41_EXAMPLE } from "../lib/example";
import RubberSegment from "./reactbits/RubberSegment/RubberSegment";

type Kind = "text" | "textarea" | "lines" | "number" | "select";
interface Field {
  path: string;
  label: string;
  kind: Kind;
  hint?: string;
  unit?: string;
  options?: [string, string][];
  required?: boolean;
}

const LABEL_FIELDS: Field[] = [
  { path: "label.product_name", label: "Product name", kind: "text", required: true },
  { path: "label.brand_name", label: "Brand name", kind: "text" },
  { path: "declared_category", label: "Declared category", kind: "text", required: true },
  { path: "label.veg_status", label: "Veg / non-veg mark", kind: "select",
    options: [["veg", "Veg"], ["non_veg", "Non-veg"], ["not_declared", "Not declared"]] },
  { path: "label.claims", label: "Claims as printed", kind: "lines", hint: "One per line, exactly as on the pack." },
  { path: "label.front_of_pack_text", label: "Front-of-pack text", kind: "textarea" },
  { path: "label.ingredients", label: "Ingredients", kind: "textarea" },
  { path: "label.allergen_statement", label: "Allergen statement", kind: "textarea" },
];
const PACK_FIELDS: Field[] = [
  { path: "package.net_quantity", label: "Net quantity", kind: "number", required: true },
  { path: "package.net_quantity_unit", label: "Unit", kind: "select", options: [["g", "g"], ["kg", "kg"], ["ml", "ml"], ["l", "l"]] },
  { path: "package.principal_display_panel_cm2", label: "Principal display panel", kind: "number", unit: "cm²", required: true },
];
const NUTRITION_FIELDS: Field[] = [
  { path: "nutrition.energy_kcal", label: "Energy", kind: "number", unit: "kcal", required: true },
  { path: "nutrition.protein_g", label: "Protein", kind: "number", unit: "g", required: true },
  { path: "nutrition.carbohydrate_g", label: "Carbohydrate", kind: "number", unit: "g", required: true },
  { path: "nutrition.total_sugars_g", label: "Total sugars", kind: "number", unit: "g", required: true },
  { path: "nutrition.total_fat_g", label: "Total fat", kind: "number", unit: "g", required: true },
];
const ALL_FIELDS = [...LABEL_FIELDS, ...PACK_FIELDS, ...NUTRITION_FIELDS, { path: "nutrition.basis", label: "Basis", kind: "select" as Kind }];

type Values = Record<string, string>;
type Notice =
  | { tone: "error"; title: string; errors: FieldError[]; quarantineId: string | null }
  | { tone: "warn"; title: string; until: number }
  | { tone: "error"; title: string };

const get = (obj: unknown, path: string): unknown =>
  path.split(".").reduce<unknown>((o, k) => (o && typeof o === "object" ? (o as Record<string, unknown>)[k] : undefined), obj);

function set(obj: Record<string, unknown>, path: string, value: unknown) {
  const keys = path.split(".");
  let o = obj;
  for (const k of keys.slice(0, -1)) o = (o[k] ??= {}) as Record<string, unknown>;
  const last = keys[keys.length - 1]!;
  if (value === undefined) delete o[last];
  else o[last] = value;
}

function fromRequest(req: LabelCheckRequest): Values {
  const values: Values = {};
  for (const f of ALL_FIELDS) {
    const v = get(req, f.path);
    values[f.path] = Array.isArray(v) ? v.join("\n") : v == null ? "" : String(v);
  }
  return values;
}

/** Form values merged over the last full request, so fields the form doesn't show are kept. */
function toRequest(values: Values, base: LabelCheckRequest): LabelCheckRequest {
  const out = structuredClone(base) as unknown as Record<string, unknown>;
  for (const f of ALL_FIELDS) {
    const raw = values[f.path] ?? "";
    if (f.kind === "number") set(out, f.path, raw.trim() === "" ? undefined : Number(raw));
    else if (f.kind === "lines") set(out, f.path, raw.split("\n").map((s) => s.trim()).filter(Boolean));
    else if (f.path === "label.brand_name" || f.path === "label.allergen_statement") set(out, f.path, raw.trim() || null);
    else set(out, f.path, raw);
  }
  return out as unknown as LabelCheckRequest;
}

/** Mount with `key` = the open run, so its request fills the form: fix the fields and check again. */
export function RequestPanel({ onAccepted, initial }: { onAccepted: (runId: string) => void; initial?: LabelCheckRequest | null }) {
  const formId = useId();
  const [mode, setMode] = useState<"form" | "json">("form");
  const [base, setBase] = useState<LabelCheckRequest>(initial ?? SECTION_41_EXAMPLE);
  const [values, setValues] = useState<Values>(() => fromRequest(initial ?? SECTION_41_EXAMPLE));
  const [json, setJson] = useState("");
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const noticeRef = useRef<HTMLDivElement>(null);
  const [me] = useState(clientId);

  const limitedUntil = notice && "until" in notice ? notice.until : 0;
  useEffect(() => {
    if (!limitedUntil) return;
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [limitedUntil]);
  const waitS = Math.max(0, Math.ceil((limitedUntil - now) / 1000));

  const fieldErrors = new Map<string, string>();
  if (notice && "errors" in notice && mode === "form") {
    for (const e of notice.errors) if (ALL_FIELDS.some((f) => f.path === e.loc)) fieldErrors.set(e.loc, e.message);
  }

  const load = (req: LabelCheckRequest) => {
    setBase(req);
    setValues(fromRequest(req));
    setJson(JSON.stringify(req, null, 2));
    setJsonError(null);
    setNotice(null);
  };

  const switchMode = (next: string) => {
    if (next === mode) return;
    if (next === "json") {
      setJson(JSON.stringify(toRequest(values, base), null, 2));
      setMode("json");
      return;
    }
    try {
      const parsed = JSON.parse(json) as LabelCheckRequest;
      setBase(parsed);
      setValues(fromRequest(parsed));
      setJsonError(null);
      setMode("form");
    } catch {
      setJsonError("This is not valid JSON, so it can't be shown as a form. Fix it, or submit it as it is to see the service reject it.");
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setNotice(null);
    const outcome = await submitRun(mode === "json" ? json : toRequest(values, base), me);
    setBusy(false);
    if (outcome.kind === "accepted") return onAccepted(outcome.runId);
    if (outcome.kind === "rejected") {
      setNotice({ tone: "error", title: `The service rejected the request: ${outcome.errors.length} problem${outcome.errors.length === 1 ? "" : "s"}. No run was started.`,
                  errors: outcome.errors, quarantineId: outcome.quarantineId });
    } else if (outcome.kind === "rate_limited") {
      setNow(Date.now());
      setNotice({ tone: "warn", title: "Too many checks from this browser.", until: Date.now() + outcome.retryAfterS * 1000 });
    } else {
      setNotice({ tone: "error", title: outcome.message });
    }
    requestAnimationFrame(() => noticeRef.current?.focus());
  };

  const field = (f: Field) => {
    const id = `${formId}-${f.path}`;
    const err = fieldErrors.get(f.path);
    const common = {
      id, name: f.path, value: values[f.path] ?? "", required: f.required,
      "aria-invalid": err ? true : undefined, "aria-describedby": err ? `${id}-err` : f.hint ? `${id}-hint` : undefined,
      onChange: (e: { target: { value: string } }) => setValues((v) => ({ ...v, [f.path]: e.target.value })),
    };
    return (
      <div key={f.path} className="field" data-kind={f.kind}>
        <label htmlFor={id}>{f.label}{f.unit && <span className="field__unit"> ({f.unit})</span>}</label>
        {f.kind === "select" ? (
          <select {...common}>{f.options!.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        ) : f.kind === "textarea" || f.kind === "lines" ? (
          <textarea {...common} rows={2} />
        ) : (
          <input {...common} type="text" inputMode={f.kind === "number" ? "decimal" : undefined} autoComplete="off" />
        )}
        {f.hint && !err && <p id={`${id}-hint`} className="field__hint">{f.hint}</p>}
        {err && <p id={`${id}-err`} className="field__error">{err}</p>}
      </div>
    );
  };

  return (
    <section className="panel request" aria-labelledby={`${formId}-title`}>
      <div className="request__head">
        <h2 id={`${formId}-title`}>Label to check</h2>
        <RubberSegment items={[{ value: "form", label: "Form" }, { value: "json", label: "JSON" }]} value={mode}
          onChange={switchMode} aria-label="Input format" size="sm" radius={0} inset={2} trackColor="var(--panel-2)" thumbColor="var(--ink)"
          textColor="var(--ink)" activeTextColor="var(--on-ink)" />
      </div>

      <form onSubmit={submit} noValidate aria-describedby={notice ? `${formId}-notice` : undefined}>
        {mode === "form" ? (
          <>
            <fieldset className="label-fields"><legend>Label</legend>{LABEL_FIELDS.map(field)}</fieldset>
            <fieldset className="pack"><legend>Package</legend>{PACK_FIELDS.map(field)}</fieldset>
            <fieldset className="nutrition">
              <legend className="visually-hidden">Nutritional information</legend>
              <div className="nutrition__panel">
                <div className="nutrition__title">
                  <span aria-hidden="true">Nutritional information</span>
                  <label htmlFor={`${formId}-basis`}>per</label>
                  <select id={`${formId}-basis`} value={values["nutrition.basis"]}
                    onChange={(e) => setValues((v) => ({ ...v, "nutrition.basis": e.target.value }))}>
                    <option value="per_100g">100 g</option>
                    <option value="per_100ml">100 ml</option>
                  </select>
                </div>
                <table className="nutrition__table">
                  <tbody>
                    {NUTRITION_FIELDS.map((f) => {
                      const id = `${formId}-${f.path}`;
                      const err = fieldErrors.get(f.path);
                      return (
                        <tr key={f.path}>
                          <th scope="row"><label htmlFor={id}>{f.label} <span className="field__unit">({f.unit})</span></label></th>
                          <td>
                            <input id={id} name={f.path} type="text" inputMode="decimal" autoComplete="off" required
                              value={values[f.path] ?? ""} aria-invalid={err ? true : undefined}
                              aria-describedby={err ? `${id}-err` : undefined}
                              onChange={(e) => setValues((v) => ({ ...v, [f.path]: e.target.value }))} />
                            {err && <p id={`${id}-err`} className="field__error">{err}</p>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </fieldset>
          </>
        ) : (
          <div className="field">
            <label htmlFor={`${formId}-json`}>LabelCheckRequest as JSON</label>
            <textarea id={`${formId}-json`} className="json" value={json} spellCheck={false} rows={22}
              onChange={(e) => { setJson(e.target.value); setJsonError(null); }} aria-describedby={`${formId}-json-hint`} />
            <p id={`${formId}-json-hint`} className="field__hint">Sent exactly as typed. The contract is published at <a href="/docs" target="_blank" rel="noreferrer">/docs</a>.</p>
            {jsonError && <p className="field__error" role="alert">{jsonError}</p>}
          </div>
        )}

        {notice && (
          <div id={`${formId}-notice`} ref={noticeRef} tabIndex={-1} className="banner" data-tone={notice.tone} role="alert">
            <p className="banner__title">{notice.title}{"until" in notice && (waitS > 0 ? ` Try again in ${waitS} s.` : " You can try again now.")}</p>
            {"errors" in notice && (
              <>
                <ul className="banner__errors">
                  {notice.errors.map((e, i) => <li key={`${e.loc}-${i}`}><code>{e.loc}</code> {e.message}</li>)}
                </ul>
                {notice.quarantineId && <p className="banner__meta">Quarantined as <code>{notice.quarantineId}</code>.</p>}
              </>
            )}
          </div>
        )}

        <div className="request__actions">
          <button type="submit" className="button" disabled={busy || waitS > 0} aria-busy={busy || undefined}>
            {busy ? "Checking…" : "Check label"}
          </button>
          <button type="button" className="button-link" onClick={() => load(SECTION_41_EXAMPLE)}>Load the §4.1 example</button>
          <button type="button" className="button-link" onClick={() => load(EMPTY_REQUEST)}>Clear</button>
        </div>
        <p className="request__client">Sent as client <code>{me}</code>; rate limits apply per client.</p>
      </form>
    </section>
  );
}
