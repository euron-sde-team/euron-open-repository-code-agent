import { expect, test } from "@playwright/test";

import { WORKSPACE, apiGet, signIn } from "../helpers";

type Run = { number: number; status: string; trigger: string };

test("test runs are listed with their trigger, result and duration", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto(`/w/${WORKSPACE}/runs`);
  const table = page.getByRole("region", { name: "Test runs" });
  await expect(table.getByRole("row")).not.toHaveCount(1);
  await expect(table).toContainText("Manual run");
  await expect(table).toContainText("Agent baseline");
  await expect(table).toContainText("Agent verification");
  await page.getByLabel("Status").selectOption("failed");
  await expect(page).toHaveURL(/status=failed/);
  await expect(table.getByText("Passed", { exact: true })).toHaveCount(0);
});

test("a run shows every test, the failing one expanded, the limits and the log", async ({ page }) => {
  await signIn(page, "viewer");
  const failed = await apiGet<{ items: Run[] }>(page, "/test-runs?status=failed&trigger=manual&limit=1");
  const run = failed.items[0]!;
  await page.goto(`/w/${WORKSPACE}/runs/${run.number}`);
  await expect(page.getByRole("heading", { name: `Test run #${run.number}`, level: 1 })).toBeVisible();
  const results = page.getByRole("region", { name: "Test results" });
  await expect(results.getByRole("row", { name: /^test_discount_applies_at_threshold/ })).toBeVisible();
  await expect(results).toContainText("assert");
  await page.getByRole("radio", { name: /Failing/ }).click();
  await expect(results.getByRole("row", { name: /test_no_discount_below_the_threshold/ })).toHaveCount(0);
  await expect(page.getByText("network: none")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Log" })).toBeVisible();
});

test("a developer starts a run on a repository and it finishes", async ({ page }) => {
  test.setTimeout(240_000);
  await signIn(page, "developer");
  await page.goto(`/w/${WORKSPACE}/runs`);
  await page.getByLabel("Repository").selectOption("ledgerkit");
  await page.getByRole("button", { name: /^Run tests/ }).click();
  await expect(page).toHaveURL(new RegExp(`/w/${WORKSPACE}/runs/\\d+$`));
  await expect(page.getByText("Failed", { exact: true }).first()).toBeVisible({ timeout: 180_000 });
});
