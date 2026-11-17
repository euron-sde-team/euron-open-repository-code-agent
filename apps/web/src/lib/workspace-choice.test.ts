import { describe, expect, it } from "vitest";

import type { WorkspaceSummary } from "@/lib/types";
import { pickWorkspace } from "@/lib/workspace-choice";

const ws = (slug: string, role: WorkspaceSummary["role"]): WorkspaceSummary => ({
  id: slug,
  slug,
  name: slug.toUpperCase(),
  role,
  repository_count: 0,
  member_count: 1,
});

describe("pickWorkspace", () => {
  it("returns null when there is nothing to open", () => {
    expect(pickWorkspace([], "a")).toBeNull();
  });

  it("prefers the workspace used last", () => {
    expect(pickWorkspace([ws("b", "owner"), ws("a", "viewer")], "a")?.slug).toBe("a");
  });

  it("ignores a remembered workspace the person no longer belongs to", () => {
    expect(pickWorkspace([ws("b", "viewer"), ws("c", "owner")], "gone")?.slug).toBe("c");
  });

  it("falls back to the first by name when none is owned", () => {
    expect(pickWorkspace([ws("z", "viewer"), ws("m", "developer")], null)?.slug).toBe("m");
  });
});
