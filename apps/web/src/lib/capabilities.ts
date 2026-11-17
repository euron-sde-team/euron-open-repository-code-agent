import type { Role } from "@/lib/types";

const RANK: Record<Role, number> = { viewer: 1, developer: 2, maintainer: 3, owner: 4 };

export function atLeast(role: Role | null | undefined, required: Role): boolean {
  return role ? RANK[role] >= RANK[required] : false;
}

/** What each role may do, in the words the UI uses; the API enforces the same rules. */
export const ROLE_SUMMARY: Record<Role, string> = {
  viewer: "Browse code, search, ask and read tasks, patches and test runs.",
  developer: "Everything a viewer can, plus describe tasks, comment on patches and run tests.",
  maintainer: "Everything a developer can, plus connect repositories and approve or apply patches.",
  owner: "Everything, plus members, API keys and workspace settings.",
};

export const ROLES: Role[] = ["owner", "maintainer", "developer", "viewer"];
