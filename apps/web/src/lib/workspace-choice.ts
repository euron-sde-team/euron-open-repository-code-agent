import type { WorkspaceSummary } from "@/lib/types";

/**
 * Which workspace to open: the one used last if the person still belongs to it, otherwise
 * the first they own, otherwise the first they belong to. Deterministic, so a reload and a
 * second browser agree.
 */
export function pickWorkspace(workspaces: WorkspaceSummary[], last: string | null): WorkspaceSummary | null {
  if (workspaces.length === 0) return null;
  const remembered = last ? workspaces.find((w) => w.slug === last) : undefined;
  if (remembered) return remembered;
  const sorted = [...workspaces].sort((a, b) => a.name.localeCompare(b.name));
  return sorted.find((w) => w.role === "owner") ?? sorted[0] ?? null;
}
