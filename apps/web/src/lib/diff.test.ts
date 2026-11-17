import { describe, expect, it } from "vitest";

import { groupComments, lineKey, lineNumber, lineSide, orphaned } from "@/lib/diff";
import type { DiffLine, PatchFile, ReviewComment } from "@/lib/types";

const line = (kind: DiffLine["kind"], old_line: number | null, new_line: number | null): DiffLine => ({
  kind,
  old_line,
  new_line,
  tokens: [],
});

const comment = (id: string, over: Partial<ReviewComment>): ReviewComment => ({
  id,
  author: "A",
  author_id: "u",
  body: id,
  path: null,
  line: null,
  side: null,
  resolved: false,
  created_at: "2026-11-01T00:00:00Z",
  ...over,
});

const file: PatchFile = {
  path: "a.py",
  change_type: "modified",
  language: "Python",
  additions: 1,
  deletions: 1,
  hunks: [
    {
      old_start: 1,
      old_count: 2,
      new_start: 1,
      new_count: 2,
      section: "",
      lines: [line("context", 1, 1), line("del", 2, null), line("add", null, 2)],
    },
  ],
};

describe("diff lines", () => {
  it("anchors removed lines to the old side and the rest to the new", () => {
    expect(lineSide(line("del", 2, null))).toBe("old");
    expect(lineNumber(line("del", 2, null))).toBe(2);
    expect(lineSide(line("add", null, 2))).toBe("new");
    expect(lineNumber(line("context", 1, 1))).toBe(1);
  });
});

describe("groupComments", () => {
  it("separates line, file and general comments", () => {
    const grouped = groupComments([
      comment("line", { path: "a.py", line: 2, side: "new" }),
      comment("file", { path: "a.py" }),
      comment("general", {}),
    ]);
    expect(grouped.byLine.get(lineKey("a.py", "new", 2))?.map((c) => c.id)).toEqual(["line"]);
    expect(grouped.byFile.get("a.py")?.map((c) => c.id)).toEqual(["file"]);
    expect(grouped.general.map((c) => c.id)).toEqual(["general"]);
  });
});

describe("orphaned", () => {
  it("finds comments whose line is no longer in the diff", () => {
    const found = orphaned(
      [file],
      [comment("ok", { path: "a.py", line: 2, side: "new" }), comment("gone", { path: "a.py", line: 40, side: "new" })],
    );
    expect(found.map((c) => c.id)).toEqual(["gone"]);
  });
});
