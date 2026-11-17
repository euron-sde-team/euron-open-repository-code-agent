import type { CodeLine, Token } from "@/lib/types";

/** The Tailwind text colour of each highlight class the API returns. */
export const TOKEN_CLASS: Record<string, string> = {
  kw: "text-hl-kw",
  str: "text-hl-str",
  com: "text-hl-com italic",
  num: "text-hl-num",
  fn: "text-hl-fn",
  cls: "text-hl-cls",
  op: "text-hl-op",
  bi: "text-hl-bi",
  dec: "text-hl-dec",
  var: "text-hl-var",
  punc: "text-hl-punc",
};

export function tokenClass(name: string): string {
  return TOKEN_CLASS[name] ?? "";
}

export function lineText(line: CodeLine | Token[]): string {
  return line.map(([, text]) => text).join("");
}

/** Whether `line` (1-based) is inside the highlighted range. */
export function inRange(line: number, range: { start: number; end: number } | null): boolean {
  return range !== null && line >= range.start && line <= range.end;
}

/** The deepest symbol whose range contains the line: what a gutter click opens. */
export function symbolAt<T extends { start_line: number; end_line: number; depth: number }>(
  outline: T[],
  line: number,
): T | null {
  let best: T | null = null;
  for (const symbol of outline) {
    if (line >= symbol.start_line && line <= symbol.end_line && (!best || symbol.depth >= best.depth)) {
      best = symbol;
    }
  }
  return best;
}

/** Group a flat file list into a folder tree for the sidebar. */
export type TreeNode = {
  name: string;
  path: string;
  kind: "dir" | "file";
  children: TreeNode[];
  file?: { language: string; is_test: boolean; symbol_count: number; indexed: boolean };
};

export function buildTree(
  files: { path: string; language: string; is_test: boolean; symbol_count: number; indexed: boolean }[],
): TreeNode {
  const root: TreeNode = { name: "", path: "", kind: "dir", children: [] };
  for (const file of files) {
    const parts = file.path.split("/");
    let node = root;
    parts.forEach((part, index) => {
      const path = parts.slice(0, index + 1).join("/");
      const leaf = index === parts.length - 1;
      let child = node.children.find((c) => c.name === part && c.kind === (leaf ? "file" : "dir"));
      if (!child) {
        child = leaf
          ? { name: part, path, kind: "file", children: [], file }
          : { name: part, path, kind: "dir", children: [] };
        node.children.push(child);
      }
      node = child;
    });
  }
  const sort = (node: TreeNode) => {
    node.children.sort((a, b) => (a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === "dir" ? -1 : 1));
    node.children.forEach(sort);
  };
  sort(root);
  return root;
}
