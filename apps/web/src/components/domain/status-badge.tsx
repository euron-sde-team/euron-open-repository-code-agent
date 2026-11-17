import { Badge } from "@/components/ui/badge";
import { INDEX_STATUS, PATCH_STATUS, RUN_STATUS, TASK_STATUS, type Tone } from "@/lib/labels";
import type { IndexStatus, PatchStatus, RunStatus, TaskStatus } from "@/lib/types";

function Pill({ label, tone, live }: { label: string; tone: Tone; live?: boolean }) {
  return (
    <Badge tone={tone}>
      {live ? <span className="animate-pulse-dot size-1.5 rounded-full bg-current" aria-hidden /> : null}
      {label}
    </Badge>
  );
}

export function TaskStatusBadge({ status }: { status: TaskStatus }) {
  const { label, tone } = TASK_STATUS[status];
  return <Pill label={label} tone={tone} live={status === "running" || status === "applying"} />;
}

export function PatchStatusBadge({ status }: { status: PatchStatus }) {
  const { label, tone } = PATCH_STATUS[status];
  return <Pill label={label} tone={tone} live={status === "applying"} />;
}

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const { label, tone } = RUN_STATUS[status];
  return <Pill label={label} tone={tone} live={status === "running"} />;
}

export function IndexStatusBadge({ status }: { status: IndexStatus }) {
  const { label, tone } = INDEX_STATUS[status];
  return <Pill label={label} tone={tone} live={status === "indexing"} />;
}

/** The outcome of one test case in a run's results. */
export function CaseStatusBadge({ status }: { status: string }) {
  const tone: Tone = status === "passed" ? "success" : status === "failed" || status === "error" ? "danger" : "neutral";
  return <Badge tone={tone}>{status}</Badge>;
}
