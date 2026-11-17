import { expect, test } from "@playwright/test";

import { WORKSPACE, signIn } from "../helpers";

const BASE = `/w/${WORKSPACE}`;

test("an answer is streamed with citations that open the cited lines", async ({ page }) => {
  await signIn(page, "developer");
  await page.goto(`${BASE}/ask`);
  await page.getByLabel("Your question").fill("Where is the tax for an invoice calculated?");
  await page.getByLabel("Your question").press("Enter");

  const sources = page.getByRole("region", { name: "Sources" });
  await expect(sources).toBeVisible();
  await expect(page).toHaveURL(/\/ask\/[0-9a-f-]{36}$/);
  await expect(page.getByText("Answered by").last()).toContainText("offline local answerer");
  await expect(sources).toContainText("ledgerkit/tax.py");

  // The chip in the text and the row under it both lead to the same lines.
  const chip = page.getByRole("link", { name: /^Source 1: / }).first();
  await chip.click();
  await expect(page).toHaveURL(/\/code\/.+#L\d+-L\d+$/);
  const hash = new URL(page.url()).hash;
  const first = hash.match(/#L(\d+)-L\d+/)![1];
  await expect(page.locator(`#L${first}`)).toHaveClass(/bg-code-line/);
});

test("a follow-up keeps its context, and the conversation is kept in the history", async ({ page }) => {
  await signIn(page, "developer");
  await page.goto(`${BASE}/ask`);
  await page.getByLabel("Your question").fill("What does calc_tax do?");
  await page.getByLabel("Your question").press("Enter");
  await expect(page).toHaveURL(/\/ask\/[0-9a-f-]{36}$/);
  await expect(page.getByText("Answered by")).toHaveCount(1);

  await page.getByLabel("Your question").fill("And where is it called from?");
  await page.getByLabel("Your question").press("Enter");
  await expect(page.getByText("Answered by")).toHaveCount(2);
  await expect(page.getByRole("main")).toContainText("Invoice.tax");

  const history = page.getByRole("navigation", { name: "Conversations" });
  await expect(history.getByRole("link", { name: /What does calc_tax do/ })).toBeVisible();
});

test("a question the code cannot answer says so instead of guessing", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto(`${BASE}/ask`);
  await page.getByLabel("Your question").fill("xyzzy plugh frobnicate quantum entanglement");
  await page.getByLabel("Your question").press("Enter");
  await expect(page.getByText("I could not find this in the indexed code")).toBeVisible();
  await expect(page.getByRole("region", { name: "Sources" })).toHaveCount(0);
});

test("conversations are private: another person does not see them", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto(`${BASE}/ask`);
  const history = page.getByRole("navigation", { name: "Conversations" });
  await expect(history.getByRole("link", { name: /calc_tax/ })).toHaveCount(0);
});
