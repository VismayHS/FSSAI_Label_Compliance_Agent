const KEY = "fssai.clientId";

/** A stable per-browser id for X-Client-Id (rate limiting is per client). Storage may be unavailable
 * (private mode, blocked site data): then a per-session id is used. */
export function clientId(): string {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved && /^[A-Za-z0-9._:-]{1,64}$/.test(saved)) return saved;
    const fresh = newId();
    localStorage.setItem(KEY, fresh);
    return fresh;
  } catch {
    return (sessionId ??= newId());
  }
}

let sessionId: string | undefined;

function newId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(4));
  return `web-${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")}`;
}
