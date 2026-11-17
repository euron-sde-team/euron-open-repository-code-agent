import { describe, expect, it } from "vitest";

import {
  formatAge,
  formatBytes,
  formatCompact,
  formatDate,
  formatDateTime,
  formatDay,
  formatDuration,
  formatPercent,
  formatRelative,
  humanize,
  initials,
  pluralize,
  truncate,
} from "@/lib/format";

const now = new Date("2026-10-23T12:00:00Z");

describe("numbers", () => {
  it("formats sizes, ratios and durations", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(50 * 1024 * 1024)).toBe("50 MB");
    expect(formatPercent(0.7512)).toBe("75%");
    expect(formatPercent(0.7512, 1)).toBe("75.1%");
    expect(formatDuration(420)).toBe("420 ms");
    expect(formatDuration(1380)).toBe("1.4 s");
    expect(formatDuration(12_400)).toBe("12 s");
    expect(formatCompact(4754)).toBe("4,754");
    expect(formatCompact(125_000)).toBe("125K");
  });

  it("pluralizes with the count", () => {
    expect(pluralize(1, "file")).toBe("1 file");
    expect(pluralize(2, "repository", "repositories")).toBe("2 repositories");
    expect(pluralize(1200, "user")).toBe("1,200 users");
  });
});

describe("time", () => {
  it("formats relative times", () => {
    expect(formatRelative("2026-10-23T11:59:30Z", now)).toBe("just now");
    expect(formatRelative("2026-10-23T09:00:00Z", now)).toBe("3 hours ago");
    expect(formatRelative("2026-10-20T12:00:00Z", now)).toBe("3 days ago");
    expect(formatRelative("2026-10-25T12:00:00Z", now)).toBe("in 2 days");
  });

  it("formats compact ages for dense tables", () => {
    expect(formatAge("2026-10-23T11:59:50Z", now)).toBe("now");
    expect(formatAge("2026-10-23T11:25:00Z", now)).toBe("35m");
    expect(formatAge("2026-10-23T07:00:00Z", now)).toBe("5h");
    expect(formatAge("2026-10-14T12:00:00Z", now)).toBe("9d");
    expect(formatAge("2026-09-11T12:00:00Z", now)).toBe("6w");
    expect(formatAge("2026-06-23T12:00:00Z", now)).toBe("4mo");
    expect(formatAge("2024-10-01T12:00:00Z", now)).toBe("2y");
    expect(formatAge("2026-10-26T12:00:00Z", now)).toBe("in 3d");
  });

  it("formats dates in a given zone", () => {
    expect(formatDate("2026-10-23T23:30:00Z", { timeZone: "UTC" })).toBe("Oct 23, 2026");
    expect(formatDateTime("2026-10-23T15:04:00Z", { timeZone: "UTC" })).toBe("Oct 23, 2026, 3:04 PM");
    expect(formatDay("2026-10-23")).toBe("Oct 23");
  });
});

describe("text", () => {
  it("builds initials", () => {
    expect(initials("Maya Chen")).toBe("MC");
    expect(initials("leo")).toBe("L");
    expect(initials("  ")).toBe("?");
  });

  it("truncates and humanizes", () => {
    expect(truncate("short", 10)).toBe("short");
    expect(truncate("a long sentence about travel", 12)).toBe("a long se...");
    expect(humanize("user_request")).toBe("User request");
    expect(humanize("patch.approved")).toBe("Patch approved");
  });
});
