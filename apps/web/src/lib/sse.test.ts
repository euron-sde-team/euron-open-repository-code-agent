import { describe, expect, it } from "vitest";

import { parseSse } from "@/lib/sse";

describe("parseSse", () => {
  it("parses complete events and keeps the unfinished tail", () => {
    const { events, rest } = parseSse(
      'event: sources\ndata: {"sources":[]}\n\nevent: delta\ndata: {"text":"Hel"}\n\nevent: delta\ndata: {"te',
    );
    expect(events).toEqual([
      { event: "sources", data: { sources: [] } },
      { event: "delta", data: { text: "Hel" } },
    ]);
    expect(rest).toBe('event: delta\ndata: {"te');
  });

  it("skips malformed frames and frames without data", () => {
    const { events } = parseSse('event: delta\ndata: {nope\n\n: comment\n\nevent: done\ndata: {"ok":true}\n\n');
    expect(events).toEqual([{ event: "done", data: { ok: true } }]);
  });

  it("joins multi-line data and defaults the event name", () => {
    const { events } = parseSse('data: {"a":\ndata: 1}\n\n');
    expect(events).toEqual([{ event: "message", data: { a: 1 } }]);
  });
});
