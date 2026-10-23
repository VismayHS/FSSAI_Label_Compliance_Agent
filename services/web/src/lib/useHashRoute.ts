import { useEffect, useState } from "react";

export type View = { name: "check"; runId: string | null } | { name: "runs" };

const RUN = /^#\/runs\/([0-9a-f]{32})$/;

export function parse(hash: string): View {
  if (hash === "#/runs") return { name: "runs" };
  const match = RUN.exec(hash);
  return { name: "check", runId: match?.[1] ?? null };
}

export const hrefFor = (view: View) => (view.name === "runs" ? "#/runs" : view.runId ? `#/runs/${view.runId}` : "#/");

/** Deep links (#/runs/<id>) let the demo open any run's result and trace directly. */
export function useHashRoute(): [View, (view: View) => void] {
  const [view, setView] = useState(() => parse(window.location.hash));
  useEffect(() => {
    const onChange = () => setView(parse(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return [view, (next) => { window.location.hash = hrefFor(next); }];
}
