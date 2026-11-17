import { describe, expect, it } from "vitest";

import { blocks, inlineSegments } from "@/lib/citations";

describe("inlineSegments", () => {
  it("splits code, bold, citations and text in order", () => {
    expect(inlineSegments("`calc_tax` in **pricing** [2] done")).toEqual([
      { kind: "code", text: "calc_tax" },
      { kind: "text", text: " in " },
      { kind: "bold", text: "pricing" },
      { kind: "text", text: " " },
      { kind: "cite", n: 2 },
      { kind: "text", text: " done" },
    ]);
  });

  it("keeps plain text whole and ignores unmatched markers", () => {
    expect(inlineSegments("just text")).toEqual([{ kind: "text", text: "just text" }]);
    expect(inlineSegments("a [x] b `open")).toEqual([{ kind: "text", text: "a [x] b `open" }]);
  });

  it("never treats text as markup", () => {
    expect(inlineSegments("<img src=x onerror=1>")).toEqual([{ kind: "text", text: "<img src=x onerror=1>" }]);
  });
});

describe("blocks", () => {
  it("separates paragraphs, lists, headings and fenced code", () => {
    const text = [
      "# Title",
      "",
      "First line",
      "second line",
      "",
      "- one",
      "- two",
      "",
      "```python",
      "x = 1",
      "```",
      "After",
    ].join("\n");
    expect(blocks(text)).toEqual([
      { kind: "heading", level: 1, text: "Title" },
      { kind: "paragraph", text: "First line second line" },
      { kind: "list", items: ["one", "two"] },
      { kind: "code", text: "x = 1", language: "python" },
      { kind: "paragraph", text: "After" },
    ]);
  });

  it("closes an unterminated fence at the end of the text", () => {
    expect(blocks("```\nprint(1)")).toEqual([{ kind: "code", text: "print(1)", language: "" }]);
  });

  it("does not parse markers inside a code block", () => {
    const [block] = blocks("```\nitems[1]\n```");
    expect(block).toEqual({ kind: "code", text: "items[1]", language: "" });
  });
});
