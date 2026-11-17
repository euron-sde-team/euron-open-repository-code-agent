import Link from "next/link";

import { RunStatusBadge } from "@/components/domain/status-badge";
import { formatDuration } from "@/lib/format";
import { wsPath } from "@/lib/navigation";
import type { RunSummary } from "@/lib/types";

function Cell({ label, run, workspace }: { label: string; run: RunSummary | null; workspace: string }) {
  if (!run) {
    return (
      <div className="border-border rounded-lg border p-3">
        <p className="text-muted-foreground text-[12px] font-medium tracking-wider uppercase">{label}</p>
        <p className="text-muted-foreground mt-2 text-[13px]">Not run.</p>
      </div>
    );
  }
  return (
    <Link
      href={wsPath(workspace, "runs", String(run.number))}
      className="border-border hover:bg-muted block rounded-lg border p-3 transition-colors"
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-muted-foreground text-[12px] font-medium tracking-wider uppercase">{label}</p>
        <RunStatusBadge status={run.status} />
      </div>
      <p className="tabular mt-2 text-[22px] leading-none font-semibold">
        {run.passed}
        <span className="text-muted-foreground text-[14px] font-normal"> / {run.total} passed</span>
      </p>
      <p className="text-muted-foreground mt-1.5 text-[12px]">
        {run.failed + run.errors > 0 ? (
          <span className="text-danger">{run.failed + run.errors} failing</span>
        ) : (
          "No failures"
        )}
        {run.duration_ms ? `, ${formatDuration(run.duration_ms)}` : ""}
      </p>
    </Link>
  );
}

/** The suite before the change and after it: the evidence a reviewer reads first. */
export function TestComparison({
  baseline,
  verify,
  workspace,
}: {
  baseline: RunSummary | null;
  verify: RunSummary | null;
  workspace: string;
}) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <Cell label="Before" run={baseline} workspace={workspace} />
      <Cell label="After" run={verify} workspace={workspace} />
    </div>
  );
}
