"use client";

import { ChevronRight, FileCode2, FileText, Folder, FlaskConical } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { SearchField } from "@/components/ui/filter-bar";
import { cn } from "@/lib/cn";
import { buildTree, type TreeNode } from "@/lib/lines";
import { codePath } from "@/lib/navigation";
import type { FileEntry } from "@/lib/types";

function Node({
  node,
  depth,
  current,
  workspace,
  repo,
  openByDefault,
  forceOpen,
}: {
  node: TreeNode;
  depth: number;
  current: string | null;
  workspace: string;
  repo: string;
  openByDefault: Set<string>;
  forceOpen: boolean;
}) {
  const [toggled, setToggled] = useState<boolean | null>(null);
  const indent = { paddingLeft: `${depth * 12 + 8}px` };
  if (node.kind === "file") {
    const active = node.path === current;
    const Icon = node.file?.is_test ? FlaskConical : node.file?.indexed === false ? FileText : FileCode2;
    return (
      <li>
        <Link
          href={codePath(workspace, repo, node.path)}
          aria-current={active ? "page" : undefined}
          style={indent}
          className={cn(
            "flex items-center gap-2 rounded-md py-1 pr-2 text-[13px] transition-colors",
            active
              ? "bg-accent text-accent-foreground font-medium"
              : "text-muted-foreground hover:bg-muted hover:text-foreground",
          )}
        >
          <Icon className="size-3.5 shrink-0" aria-hidden />
          <span className="truncate">{node.name}</span>
        </Link>
      </li>
    );
  }
  const open = forceOpen || (toggled ?? openByDefault.has(node.path));
  return (
    <li>
      <button
        type="button"
        onClick={() => setToggled(!open)}
        aria-expanded={open}
        style={indent}
        className="text-foreground hover:bg-muted flex w-full items-center gap-1.5 rounded-md py-1 pr-2 text-left text-[13px] font-medium"
      >
        <ChevronRight
          className={cn("text-subtle size-3.5 shrink-0 transition-transform", open && "rotate-90")}
          aria-hidden
        />
        <Folder className="text-subtle size-3.5 shrink-0" aria-hidden />
        <span className="truncate">{node.name}</span>
      </button>
      {open ? (
        <ul>
          {node.children.map((child) => (
            <Node
              key={child.path}
              node={child}
              depth={depth + 1}
              current={current}
              workspace={workspace}
              repo={repo}
              openByDefault={openByDefault}
              forceOpen={forceOpen}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

/** The repository's folders and files, with the current file highlighted and its folders open. */
export function FileTree({
  files,
  current,
  workspace,
  repo,
}: {
  files: FileEntry[];
  current: string | null;
  workspace: string;
  repo: string;
}) {
  const [filter, setFilter] = useState("");
  const shown = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return needle ? files.filter((f) => f.path.toLowerCase().includes(needle)) : files;
  }, [files, filter]);
  const tree = useMemo(() => buildTree(shown), [shown]);
  const openByDefault = useMemo(() => {
    const open = new Set<string>();
    if (current) {
      const parts = current.split("/");
      for (let i = 1; i < parts.length; i += 1) open.add(parts.slice(0, i).join("/"));
    }
    // A small repository is easier to scan fully open.
    if (files.length <= 40)
      for (const f of files)
        f.path
          .split("/")
          .slice(0, -1)
          .forEach((_, i, a) => open.add(a.slice(0, i + 1).join("/")));
    return open;
  }, [current, files]);
  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <SearchField
        value={filter}
        onChange={setFilter}
        label="Filter files"
        placeholder="Filter files"
        className="max-w-none flex-none"
      />
      <nav aria-label="Files" className="scroll-quiet min-h-0 flex-1 overflow-y-auto">
        {tree.children.length === 0 ? (
          <p className="text-muted-foreground px-2 py-3 text-[13px]">No file matches.</p>
        ) : (
          <ul>
            {tree.children.map((node) => (
              <Node
                key={node.path}
                node={node}
                depth={0}
                current={current}
                workspace={workspace}
                repo={repo}
                openByDefault={openByDefault}
                forceOpen={filter.trim().length > 0}
              />
            ))}
          </ul>
        )}
      </nav>
    </div>
  );
}
