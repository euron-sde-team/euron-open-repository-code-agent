import { describe, expect, it } from "vitest";

import { ApiError, errorFrom, toQuery, ws } from "@/lib/api";

describe("errorFrom", () => {
  it("reads the server's error envelope", () => {
    const error = errorFrom(404, {
      error: { code: "not_found", message: "Repository not found.", request_id: "req-1" },
    });
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 404,
      code: "not_found",
      message: "Repository not found.",
      requestId: "req-1",
    });
  });

  it("keeps the details of a validation failure", () => {
    const error = errorFrom(422, {
      error: { code: "validation_failed", message: "Invalid.", details: [{ loc: ["body"] }] },
    });
    expect(error.details).toEqual([{ loc: ["body"] }]);
  });

  it("falls back to the response header, then to generic codes, when the body is not an envelope", () => {
    expect(errorFrom(502, "<html>bad gateway</html>")).toMatchObject({ code: "server_error" });
    expect(errorFrom(400, null)).toMatchObject({ code: "request_failed" });
    expect(errorFrom(500, null, "req-header").requestId).toBe("req-header");
  });

  it("tells a network failure from an HTTP failure", () => {
    expect(new ApiError(0, "network_error", "down").isNetwork).toBe(true);
    expect(new ApiError(503, "service_unavailable", "down").isNetwork).toBe(false);
  });
});

describe("toQuery", () => {
  it("skips empty values and repeats arrays", () => {
    expect(
      toQuery({
        repository: "ledgerkit",
        q: "",
        pinned: false,
        category: ["fact", "event"],
        offset: 0,
        kind: undefined,
        path: null,
      }),
    ).toBe("?repository=ledgerkit&pinned=false&category=fact&category=event&offset=0");
  });

  it("returns an empty string without parameters", () => {
    expect(toQuery({})).toBe("");
    expect(toQuery({ q: undefined })).toBe("");
  });

  it("encodes values", () => {
    expect(toQuery({ q: "a b&c" })).toBe("?q=a+b%26c");
  });
});

describe("ws", () => {
  it("builds workspace paths from a slug or an id, encoded", () => {
    expect(ws("northwind-engineering")).toBe("/api/v1/workspaces/northwind-engineering");
    expect(ws("a b/c")).toBe("/api/v1/workspaces/a%20b%2Fc");
  });
});
