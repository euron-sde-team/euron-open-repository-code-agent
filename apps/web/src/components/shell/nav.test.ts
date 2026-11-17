import { describe, expect, it } from "vitest";

import { isNavActive, NAV_GROUPS } from "@/components/shell/nav";

describe("isNavActive", () => {
  it("matches the overview only on its own path", () => {
    expect(isNavActive("/w/acme", "acme", "")).toBe(true);
    expect(isNavActive("/w/acme/tasks", "acme", "")).toBe(false);
  });

  it("keeps a section highlighted on its detail pages", () => {
    expect(isNavActive("/w/acme/tasks/12", "acme", "tasks")).toBe(true);
    expect(isNavActive("/w/acme/repos/ledgerkit/code/a/b.py", "acme", "repos")).toBe(true);
    expect(isNavActive("/w/acme/tasks-old", "acme", "tasks")).toBe(false);
  });

  it("does not match another workspace", () => {
    expect(isNavActive("/w/other/tasks", "acme", "tasks")).toBe(false);
  });
});

describe("NAV_GROUPS", () => {
  it("has one entry per route segment", () => {
    const segments = NAV_GROUPS.flatMap((g) => g.items.map((i) => i.segment));
    expect(new Set(segments).size).toBe(segments.length);
    expect(segments).toEqual(["", "repos", "search", "ask", "tasks", "runs", "settings"]);
  });
});
