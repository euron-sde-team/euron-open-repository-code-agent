import { describe, expect, it } from "vitest";

import { buildTree, inRange, lineText, symbolAt, tokenClass } from "@/lib/lines";

describe("code lines", () => {
  it("joins the tokens of a line", () => {
    expect(
      lineText([
        ["kw", "def"],
        ["plain", " f"],
      ]),
    ).toBe("def f");
  });

  it("maps highlight classes to colours and ignores unknown ones", () => {
    expect(tokenClass("kw")).toBe("text-hl-kw");
    expect(tokenClass("made-up")).toBe("");
  });

  it("knows whether a line is in the selected range", () => {
    expect(inRange(5, { start: 5, end: 7 })).toBe(true);
    expect(inRange(8, { start: 5, end: 7 })).toBe(false);
    expect(inRange(1, null)).toBe(false);
  });

  it("finds the deepest symbol around a line", () => {
    const outline = [
      { start_line: 1, end_line: 20, depth: 0, name: "Invoice" },
      { start_line: 5, end_line: 9, depth: 1, name: "add_line" },
    ];
    expect(symbolAt(outline, 6)?.name).toBe("add_line");
    expect(symbolAt(outline, 12)?.name).toBe("Invoice");
    expect(symbolAt(outline, 40)).toBeNull();
  });
});

describe("buildTree", () => {
  const file = (path: string) => ({ path, language: "Python", is_test: false, symbol_count: 0, indexed: true });

  it("nests folders, sorts folders before files and files by name", () => {
    const tree = buildTree([file("b.py"), file("pkg/z.py"), file("pkg/a.py"), file("README.md")]);
    expect(tree.children.map((n) => `${n.kind}:${n.name}`)).toEqual(["dir:pkg", "file:b.py", "file:README.md"]);
    expect(tree.children[0]?.children.map((n) => n.name)).toEqual(["a.py", "z.py"]);
    expect(tree.children[0]?.path).toBe("pkg");
  });

  it("keeps a file and a folder of the same name apart", () => {
    const tree = buildTree([file("a"), file("a/b.py")]);
    expect(tree.children).toHaveLength(2);
  });
});
