import { expect, test } from "@playwright/test";

import { WORKSPACE, signIn } from "../helpers";

const BASE = `/w/${WORKSPACE}`;

test("the repositories are listed with their index status", async ({ page }) => {
  await signIn(page, "owner");
  await page.goto(`${BASE}/repos`);
  const list = page.getByRole("list").filter({ has: page.getByRole("link", { name: "ledgerkit" }) });
  for (const name of ["ledgerkit", "ratelimit", "checkout-web"]) {
    await expect(list.getByRole("link", { name })).toBeVisible();
  }
  await expect(list.getByText("Ready")).toHaveCount(3);
  await page.getByRole("link", { name: "ledgerkit" }).click();
  await expect(page.getByRole("heading", { name: "ledgerkit", level: 1 })).toBeVisible();
  await expect(page.getByText("Exact money arithmetic").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Languages" })).toBeVisible();
});

test("lines of a file are anchors: select one, extend to a range, deep-link to it", async ({ page }) => {
  await signIn(page, "owner");
  await page.goto(`${BASE}/repos/ledgerkit/code/ledgerkit/pricing.py`);
  await expect(page.getByRole("link", { name: "Line 20", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Line 20", exact: true }).click();
  await expect(page).toHaveURL(/#L20$/);
  await page.getByRole("link", { name: "Line 24", exact: true }).click({ modifiers: ["Shift"] });
  await expect(page).toHaveURL(/#L20-L24$/);
  await expect(page.locator("#L22")).toHaveClass(/bg-code-line/);
  await expect(page.locator("#L25")).not.toHaveClass(/bg-code-line/);

  await page.goto(`${BASE}/repos/ledgerkit/code/ledgerkit/pricing.py#L18-L24`);
  await expect(page.locator("#L18")).toHaveClass(/bg-code-line/);
  await expect(page.locator("#L18")).toBeInViewport();
});

test("the outline opens a symbol with its callers, callees and tests", async ({ page }) => {
  await signIn(page, "owner");
  await page.goto(`${BASE}/repos/ledgerkit/code/ledgerkit/pricing.py`);
  const aside = page.getByRole("complementary", { name: "Symbols" });
  await aside.getByRole("button", { name: /apply_discount/ }).click();
  await expect(page).toHaveURL(/#L18-L24$/);
  await aside.getByRole("tab", { name: "Symbol" }).click();
  await expect(aside.getByText("ledgerkit.pricing.apply_discount")).toBeVisible();
  await expect(aside.getByRole("region", { name: "Called by" })).toContainText("ledgerkit/invoice.py");
  await expect(aside.getByRole("region", { name: "Tests" })).toContainText("tests/test_pricing.py");
});

test("the file tree filters and opens files", async ({ page }) => {
  await signIn(page, "owner");
  await page.goto(`${BASE}/repos/checkout-web/code`);
  await expect(page.getByText("Choose a file")).toBeVisible();
  await page.getByRole("complementary", { name: "Repository files" }).getByLabel("Filter files").fill("cart");
  await page.getByRole("complementary", { name: "Repository files" }).getByRole("link", { name: "cart.ts" }).click();
  await expect(page).toHaveURL(/\/code\/src\/cart\.ts$/);
  await expect(page.getByLabel("Source of src/cart.ts")).toContainText("class Cart");
});

test("symbol search finds a definition and opens it at its lines", async ({ page }) => {
  await signIn(page, "owner");
  await page.goto(`${BASE}/search?q=apply_discount`);
  const hit = page.getByRole("link", { name: /ledgerkit\.pricing\.apply_discount/ });
  await expect(hit).toBeVisible();
  await hit.click();
  await expect(page).toHaveURL(/\/code\/ledgerkit\/pricing\.py#L18-L24$/);
});

test("text search highlights the match and supports regular expressions", async ({ page }) => {
  await signIn(page, "owner");
  await page.goto(`${BASE}/search?mode=text&q=volume_discount`);
  await expect(page.getByRole("link", { name: /ledgerkit \/ ledgerkit\/pricing\.py/ })).toBeVisible();
  await expect(page.locator("mark").first()).toHaveText("volume_discount");
  await page.getByRole("checkbox", { name: "Regular expression" }).click();
  await page.getByLabel("Search the code").fill("def (calc|rate)_\\w+");
  await expect(page.getByRole("link", { name: /ledgerkit\/tax\.py/ }).first()).toBeVisible();
  // A catastrophic pattern is refused with an explanation, not run.
  await page.getByLabel("Search the code").fill("(a+)+$");
  await expect(page.getByText("Nested quantifiers")).toBeVisible();
});

test("semantic search finds code by what it does", async ({ page }) => {
  await signIn(page, "owner");
  await page.goto(`${BASE}/search?mode=semantic&q=${encodeURIComponent("limit requests per client")}`);
  await expect(page.getByRole("link", { name: /ratelimit \/ limiter\.go/ }).first()).toBeVisible();
});
