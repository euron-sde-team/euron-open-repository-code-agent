import type { DiffLine, PatchFile, ReviewComment } from "@/lib/types";

/** Which side of the diff a line belongs to: removed lines are the old side, the rest the new. */
export function lineSide(line: DiffLine): "old" | "new" {
  return line.kind === "del" ? "old" : "new";
}

/** The number a comment on this line is anchored to. */
export function lineNumber(line: DiffLine): number | null {
  return line.kind === "del" ? line.old_line : line.new_line;
}

export function lineKey(path: string, side: "old" | "new", line: number): string {
  return `${path}\u0000${side}\u0000${line}`;
}

/** Comments grouped by the diff line they are anchored to; the rest are general. */
export function groupComments(comments: ReviewComment[]): {
  byLine: Map<string, ReviewComment[]>;
  byFile: Map<string, ReviewComment[]>;
  general: ReviewComment[];
} {
  const byLine = new Map<string, ReviewComment[]>();
  const byFile = new Map<string, ReviewComment[]>();
  const general: ReviewComment[] = [];
  for (const comment of comments) {
    if (comment.path && comment.line && comment.side) {
      const key = lineKey(comment.path, comment.side, comment.line);
      byLine.set(key, [...(byLine.get(key) ?? []), comment]);
    } else if (comment.path) {
      byFile.set(comment.path, [...(byFile.get(comment.path) ?? []), comment]);
    } else {
      general.push(comment);
    }
  }
  return { byLine, byFile, general };
}

/** Comments whose line is not in any hunk of the patch (the diff moved on): shown by file. */
export function orphaned(files: PatchFile[], comments: ReviewComment[]): ReviewComment[] {
  const present = new Set<string>();
  for (const file of files) {
    for (const hunk of file.hunks) {
      for (const line of hunk.lines) {
        const number = lineNumber(line);
        if (number !== null) present.add(lineKey(file.path, lineSide(line), number));
      }
    }
  }
  return comments.filter((c) => c.path && c.line && c.side && !present.has(lineKey(c.path, c.side, c.line)));
}

export const CHANGE_LABEL: Record<string, string> = {
  added: "New file",
  deleted: "Deleted",
  modified: "Modified",
};
