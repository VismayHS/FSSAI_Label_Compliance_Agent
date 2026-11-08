import { useEffect, useId, useState, type FormEvent } from "react";

import { apiKey, AUTH_REQUIRED, setApiKey } from "../lib/apiKey";

/** Asks for an API key only when the API has refused a call for want of one (keys on, docs/security.md). With
 * keys off, as in a clean clone, it never appears. Inline, not a modal: the analyst sees what they were doing. */
export function AccessKey({ reload = () => window.location.reload() }: { reload?: () => void }) {
  const [needed, setNeeded] = useState(false);
  const [hasKey, setHasKey] = useState(() => apiKey() !== null);
  const [value, setValue] = useState("");
  const inputId = useId();

  useEffect(() => {
    const onRequired = () => setNeeded(true);
    window.addEventListener(AUTH_REQUIRED, onRequired);
    return () => window.removeEventListener(AUTH_REQUIRED, onRequired);
  }, []);

  const save = (e: FormEvent) => {
    e.preventDefault();
    if (!value.trim()) return;
    setApiKey(value);
    reload(); // every panel fetches again, now with the key
  };
  const forget = () => {
    setApiKey(null);
    setHasKey(false);
    reload();
  };

  if (needed) {
    return (
      <form className="access banner" data-tone="warn" onSubmit={save} aria-labelledby={`${inputId}-title`}>
        <p className="banner__title" id={`${inputId}-title`}>
          {hasKey ? "The API key was not accepted" : "This service needs an API key"}
        </p>
        <p>Ask whoever runs the service for your key. It is kept only in this browser tab and is forgotten when you
          close it. Analyst keys see their own checks; reviewer keys also see everyone&rsquo;s and the quarantine.</p>
        <div className="access__row">
          <label htmlFor={inputId}>API key</label>
          <input id={inputId} type="password" autoComplete="off" spellCheck={false} value={value}
            onChange={(e) => setValue(e.target.value)} required />
          <button type="submit" className="button">Use this key</button>
          {hasKey && <button type="button" className="button-link" onClick={forget}>Forget the old key</button>}
        </div>
      </form>
    );
  }
  if (!hasKey) return null;
  return (
    <p className="access access--on">
      Using an API key for this tab. <button type="button" className="button-link" onClick={forget}>Forget it</button>
    </p>
  );
}
