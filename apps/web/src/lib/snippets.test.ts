import { describe, expect, it } from "vitest";

import { askExample, curlExample } from "@/lib/snippets";

describe("snippets", () => {
  it("builds a search request against the workspace with the bearer key", () => {
    const text = curlExample("http://localhost:8190", "northwind", "cak_abc_secret");
    expect(text).toContain('"http://localhost:8190/api/v1/workspaces/northwind/search/symbols?q=Invoice"');
    expect(text).toContain("Authorization: Bearer cak_abc_secret");
  });

  it("builds an ask request with a JSON body that parses", () => {
    const text = askExample("https://api.example.com", "acme", "cak_x");
    const body = /-d '(.*)'/.exec(text)?.[1] ?? "";
    expect(JSON.parse(body)).toEqual({ question: "Where is the tax for an invoice calculated?" });
    expect(text).toContain("https://api.example.com/api/v1/workspaces/acme/ask");
  });
});
