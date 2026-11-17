import {
  FlaskConical,
  FolderGit2,
  GitPullRequestArrow,
  LayoutDashboard,
  MessageSquareCode,
  Search,
  Settings,
  type LucideIcon,
} from "lucide-react";

import { wsPath } from "@/lib/navigation";

export type NavItem = {
  /** The path segment under /w/[workspace]; "" is the overview. */
  segment: string;
  label: string;
  icon: LucideIcon;
};

export type NavGroup = { label: string | null; items: NavItem[] };

/** The sidebar, in the order of the dashboard route map. */
export const NAV_GROUPS: NavGroup[] = [
  { label: null, items: [{ segment: "", label: "Overview", icon: LayoutDashboard }] },
  {
    label: "Code",
    items: [
      { segment: "repos", label: "Repositories", icon: FolderGit2 },
      { segment: "search", label: "Search", icon: Search },
      { segment: "ask", label: "Ask", icon: MessageSquareCode },
    ],
  },
  {
    label: "Changes",
    items: [
      { segment: "tasks", label: "Tasks", icon: GitPullRequestArrow },
      { segment: "runs", label: "Test runs", icon: FlaskConical },
    ],
  },
  { label: null, items: [{ segment: "settings", label: "Settings", icon: Settings }] },
];

/** Whether a nav item covers the current path (detail pages keep their section highlighted). */
export function isNavActive(pathname: string, workspace: string, segment: string): boolean {
  const href = segment ? wsPath(workspace, segment) : wsPath(workspace);
  return segment ? pathname === href || pathname.startsWith(`${href}/`) : pathname === href;
}
