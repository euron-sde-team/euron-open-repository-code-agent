import { describe, expect, it } from "vitest";

import { codePath, encodePath, parseLineHash, safeNext, wsPath } from "@/lib/navigation";

describe("safeNext", () => {
  it("keeps same-origin paths and refuses everything else", () => {
    expect(safeNext("/w/acme/tasks?status=open")).toBe("/w/acme/tasks?status=open");
    for (const bad of [
      "//evil.example",
      "https://evil.example",
      "javascript:alert(1)",
      "/\\evil",
      "",
      null,
      undefined,
    ]) {
      expect(safeNext(bad)).toBe("/");
    }
  });
});

describe("paths", () => {
  it("builds workspace paths with encoded slugs", () => {
    expect(wsPath("acme")).toBe("/w/acme");
    expect(wsPath("acme", "tasks", "12")).toBe("/w/acme/tasks/12");
    expect(wsPath("a b", "")).toBe("/w/a%20b");
  });

  it("encodes each file path segment and keeps the slashes", () => {
    expect(encodePath("src/my file#1.py")).toBe("src/my%20file%231.py");
  });

  it("links to a file at a line or a range", () => {
    expect(codePath("acme", "ledgerkit", "ledgerkit/pricing.py")).toBe(
      "/w/acme/repos/ledgerkit/code/ledgerkit/pricing.py",
    );
    expect(codePath("acme", "ledgerkit", "a.py", 12)).toBe("/w/acme/repos/ledgerkit/code/a.py#L12");
    expect(codePath("acme", "ledgerkit", "a.py", 12, 30)).toBe("/w/acme/repos/ledgerkit/code/a.py#L12-L30");
    expect(codePath("acme", "ledgerkit", "a.py", 12, 12)).toBe("/w/acme/repos/ledgerkit/code/a.py#L12");
  });
});

describe("parseLineHash", () => {
  it("reads single lines and ranges, in either order", () => {
    expect(parseLineHash("#L12")).toEqual({ start: 12, end: 12 });
    expect(parseLineHash("#L12-L30")).toEqual({ start: 12, end: 30 });
    expect(parseLineHash("L30-L12")).toEqual({ start: 12, end: 30 });
  });

  it("ignores anything else", () => {
    for (const bad of ["", "#", "#top", "#L0", "#Lx", "#L1-"]) expect(parseLineHash(bad)).toBeNull();
  });
});
