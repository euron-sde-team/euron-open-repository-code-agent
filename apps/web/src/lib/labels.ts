import type { IndexStatus, PatchStatus, RunStatus, TaskStatus } from "@/lib/types";

export type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "primary";

export const TASK_STATUS: Record<TaskStatus, { label: string; tone: Tone }> = {
  queued: { label: "Queued", tone: "neutral" },
  running: { label: "Running", tone: "info" },
  awaiting_review: { label: "Awaiting review", tone: "warning" },
  approved: { label: "Approved", tone: "primary" },
  applying: { label: "Applying", tone: "info" },
  applied: { label: "Applied", tone: "success" },
  rejected: { label: "Rejected", tone: "danger" },
  failed: { label: "Failed", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};

export const PATCH_STATUS: Record<PatchStatus, { label: string; tone: Tone }> = {
  proposed: { label: "Proposed", tone: "warning" },
  approved: { label: "Approved", tone: "primary" },
  rejected: { label: "Rejected", tone: "danger" },
  superseded: { label: "Superseded", tone: "neutral" },
  applying: { label: "Applying", tone: "info" },
  applied: { label: "Applied", tone: "success" },
};

export const RUN_STATUS: Record<RunStatus, { label: string; tone: Tone }> = {
  queued: { label: "Queued", tone: "neutral" },
  running: { label: "Running", tone: "info" },
  passed: { label: "Passed", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  error: { label: "Error", tone: "danger" },
  timed_out: { label: "Timed out", tone: "warning" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};

export const INDEX_STATUS: Record<IndexStatus, { label: string; tone: Tone }> = {
  queued: { label: "Queued", tone: "neutral" },
  indexing: { label: "Indexing", tone: "info" },
  ready: { label: "Ready", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
};

export const RUN_TRIGGER: Record<string, string> = {
  manual: "Manual run",
  agent_baseline: "Agent baseline",
  agent_verify: "Agent verification",
  patch: "Patch check",
};

export const SKILL_LABEL: Record<string, string> = {
  rename: "Rename",
  fix_test: "Fix a failing test",
  add_function: "Add a function",
  model: "Model edit",
};

export const SYMBOL_KIND_LABEL: Record<string, string> = {
  class: "class",
  function: "function",
  method: "method",
  constant: "constant",
  interface: "interface",
  type: "type",
  enum: "enum",
  struct: "struct",
  module: "module",
};

/** Statuses that are still moving: the UI polls while any list item is in one. */
export const ACTIVE_TASK: ReadonlySet<TaskStatus> = new Set(["queued", "running", "applying"]);
export const ACTIVE_RUN: ReadonlySet<RunStatus> = new Set(["queued", "running"]);
export const ACTIVE_INDEX: ReadonlySet<IndexStatus> = new Set(["queued", "indexing"]);
