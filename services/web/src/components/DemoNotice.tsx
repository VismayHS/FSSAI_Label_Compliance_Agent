import type { Readiness } from "../api/types";
import { standIns } from "../lib/useReadiness";

/** Says plainly when parts of the check are the contracts' stand-ins, so nobody mistakes a demo run for a
 * real compliance answer. Disappears by itself as teammates switch their real parts on (IMPL_*). */
export function DemoNotice({ ready }: { ready: Readiness | null | undefined }) {
  const parts = standIns(ready);
  if (parts.length === 0) return null;
  const list = parts.length === 1 ? parts[0] : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
  return (
    <div className="banner demo-notice" data-tone="warn" role="note">
      <p className="banner__title">Demo mode: some parts of the check are stand-ins</p>
      <p>
        The {list} {parts.length === 1 ? "is a placeholder" : "are placeholders"} while the team builds the real{" "}
        {parts.length === 1 ? "one" : "ones"}. A run shows how the system works, but its findings are not real
        compliance answers yet.
      </p>
    </div>
  );
}
