// The API key, when the deployment turns keys on (docs/security.md). Kept in sessionStorage, so it lasts for this tab
// and is gone when the tab closes; never in localStorage, never in the bundle or /config.js. Storage can be
// unavailable (private mode, blocked site data): then it lives in memory for this page only.
const KEY = "fssai.apiKey";
export const AUTH_REQUIRED = "fssai:auth-required";

let memory: string | null = null;

export function apiKey(): string | null {
  try {
    return sessionStorage.getItem(KEY) ?? memory;
  } catch {
    return memory;
  }
}

export function setApiKey(value: string | null): void {
  const key = value?.trim() || null;
  memory = key;
  try {
    if (key) sessionStorage.setItem(KEY, key);
    else sessionStorage.removeItem(KEY);
  } catch {
    // memory only
  }
}

export function authHeaders(): Record<string, string> {
  const key = apiKey();
  return key ? { "X-API-Key": key } : {};
}

/** Tell the page the API refused a call for want of a valid key, so it can ask for one. */
export function signalAuthRequired(): void {
  window.dispatchEvent(new Event(AUTH_REQUIRED));
}
