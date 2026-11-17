"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";

import { atLeast } from "@/lib/capabilities";
import type { Me, Role, Workspace, WorkspaceSummary } from "@/lib/types";

/** The workspace a page under `/w/[workspace]` belongs to, and what the caller may do in it. */
export type ActiveWorkspace = {
  slug: string;
  id: string;
  name: string;
  role: Role;
  workspace: Workspace;
  summary: WorkspaceSummary;
  me: Me;
  can: (role: Role) => boolean;
};

const Context = createContext<ActiveWorkspace | null>(null);

export function WorkspaceProvider({
  workspace,
  summary,
  me,
  children,
}: {
  workspace: Workspace;
  summary: WorkspaceSummary;
  me: Me;
  children: ReactNode;
}) {
  const value = useMemo<ActiveWorkspace>(
    () => ({
      slug: workspace.slug,
      id: workspace.id,
      name: workspace.name,
      role: workspace.role,
      workspace,
      summary,
      me,
      can: (required) => atLeast(workspace.role, required),
    }),
    [workspace, summary, me],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

/** Only valid under `app/w/[workspace]`: the shell renders the page after the workspace loads. */
export function useActiveWorkspace(): ActiveWorkspace {
  const value = useContext(Context);
  if (!value) throw new Error("useActiveWorkspace must be used inside the workspace shell");
  return value;
}

/** Whether the caller holds at least `role` in the active workspace. */
export function useCan(role: Role): boolean {
  return useActiveWorkspace().can(role);
}
