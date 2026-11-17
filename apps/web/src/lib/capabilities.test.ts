import { describe, expect, it } from "vitest";

import { atLeast, ROLES } from "@/lib/capabilities";
import { ACTIVE_RUN, ACTIVE_TASK, RUN_STATUS, TASK_STATUS } from "@/lib/labels";

describe("atLeast", () => {
  it("orders the roles", () => {
    expect(atLeast("owner", "maintainer")).toBe(true);
    expect(atLeast("maintainer", "maintainer")).toBe(true);
    expect(atLeast("developer", "maintainer")).toBe(false);
    expect(atLeast("viewer", "viewer")).toBe(true);
    expect(atLeast(null, "viewer")).toBe(false);
  });

  it("lists every role once, most powerful first", () => {
    expect(ROLES).toEqual(["owner", "maintainer", "developer", "viewer"]);
  });
});

describe("status labels", () => {
  it("labels every task and run status", () => {
    expect(Object.keys(TASK_STATUS)).toHaveLength(9);
    expect(Object.keys(RUN_STATUS)).toHaveLength(7);
  });

  it("polls only while work is moving", () => {
    expect(ACTIVE_TASK.has("running")).toBe(true);
    expect(ACTIVE_TASK.has("awaiting_review")).toBe(false);
    expect(ACTIVE_RUN.has("queued")).toBe(true);
    expect(ACTIVE_RUN.has("passed")).toBe(false);
  });
});
