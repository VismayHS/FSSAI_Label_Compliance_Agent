import { useEffect, useState } from "react";

import { listRuns } from "../api/client";
import type { RunSummary } from "../api/types";
import { shortId, time } from "../lib/format";
import { Mark } from "./Mark";

export function RecentRuns() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const abort = new AbortController();
    listRuns(50, abort.signal).then(setRuns, (err: Error) => {
      if (!abort.signal.aborted) setError(err.message);
    });
    return () => abort.abort();
  }, []);

  return (
    <section className="panel runs" aria-labelledby="runs-title">
      <h2 id="runs-title">Recent runs</h2>
      {error && <p className="banner" data-tone="error" role="alert">Could not load runs. {error}</p>}
      {!error && !runs && <p className="empty" aria-busy="true">Loading…</p>}
      {runs && runs.length === 0 && (
        <p className="empty">No runs yet. <a href="#/">Check a label</a> and it will appear here.</p>
      )}
      {runs && runs.length > 0 && (
        <div className="table-wrap">
          <table className="runs__table">
            <thead>
              <tr><th scope="col">Route</th><th scope="col">Product</th><th scope="col">State</th><th scope="col">Submitted</th><th scope="col">Run</th></tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.run_id}>
                  <td className="runs__route">
                    {r.route ? <><Mark kind={r.route} /><span>{r.route}</span></> : <><Mark kind={r.state === "failed" ? "error" : "running"} /><span>{r.state}</span></>}
                  </td>
                  <td><a href={`#/runs/${r.run_id}`}>{r.product_name ?? "Untitled label"}</a></td>
                  <td>{r.state}{r.complete === false ? ", incomplete" : ""}</td>
                  <td className="num">{time(r.submitted_at)}</td>
                  <td><code>{shortId(r.run_id)}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
