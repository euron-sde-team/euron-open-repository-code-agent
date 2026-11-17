import { expect, test } from "@playwright/test";

import { API_URL, WORKSPACE, scratchWorkspace, signIn, unique } from "../helpers";

test.setTimeout(180_000);

test("an API key is created, used from a script, and revoked", async ({ page, request }) => {
  await signIn(page, "owner");
  const workspace = await scratchWorkspace(page);
  await page.goto(`/w/${workspace}/settings?tab=keys`);
  await page.getByRole("button", { name: "Create key" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Create an API key" });
  await dialog.getByLabel("Name").fill("CI search");
  await dialog.getByLabel("Access").selectOption("viewer");
  await dialog.getByRole("button", { name: "Create key" }).click();

  const shown = page.getByRole("dialog", { name: "Your new API key" });
  const key = (await shown.getByLabel("API key").textContent())!.trim();
  expect(key).toMatch(/^cak_[a-z2-7]{10}_/);
  // The example in the dialog runs as written: this is the same request, from a script.
  await expect(shown.getByLabel("Search example")).toContainText(`Authorization: Bearer ${key}`);
  const ok = await request.get(`${API_URL}/api/v1/workspaces/${workspace}/repositories`, {
    headers: { authorization: `Bearer ${key}` },
  });
  expect(ok.status()).toBe(200);
  await shown.getByRole("button", { name: "I have copied it" }).click();

  const row = page.getByRole("row", { name: /CI search/ });
  await expect(row).toContainText("Active");
  await row.getByRole("button", { name: "Revoke" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Revoke key" }).click();
  await expect(row).toContainText("Revoked");
  const refused = await request.get(`${API_URL}/api/v1/workspaces/${workspace}/repositories`, {
    headers: { authorization: `Bearer ${key}` },
  });
  expect(refused.status()).toBe(401);
});

test("an owner adds a person, hands over a temporary password once, and removes them again", async ({ page }) => {
  await signIn(page, "owner");
  const workspace = await scratchWorkspace(page);
  const email = `${unique("e2e.member")}@example.com`;
  await page.goto(`/w/${workspace}/settings?tab=members`);
  await page.getByRole("button", { name: "Add person" }).click();
  const dialog = page.getByRole("dialog", { name: "Add a person" });
  await dialog.getByLabel("Email").fill(email);
  await dialog.getByLabel("Name").fill("E2E Member");
  await dialog.getByLabel("Role").selectOption("viewer");
  await dialog.getByRole("button", { name: "Add person" }).click();

  const handover = page.getByRole("dialog", { name: "Share the temporary password" });
  await expect(handover.getByLabel("Temporary password")).not.toBeEmpty();
  await handover.getByRole("button", { name: "Done" }).click();

  const row = page.getByRole("row", { name: new RegExp(email) });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "Remove E2E Member" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Remove" }).click();
  await expect(page.getByRole("row", { name: new RegExp(email) })).toHaveCount(0);
});

test("the engine page says what runs offline and how the sandbox is limited", async ({ page }) => {
  await signIn(page, "owner");
  await page.goto(`/w/${WORKSPACE}/settings?tab=engine`);
  await expect(page.getByText("Offline, no model calls")).toBeVisible();
  await expect(page.getByText("the run has no route out")).toBeVisible();
  await expect(page.getByText("code-hash-384")).toBeVisible();
});

test("the audit trail shows who did what", async ({ page }) => {
  await signIn(page, "owner");
  await page.goto(`/w/${WORKSPACE}/settings?tab=activity`);
  const table = page.getByRole("table", { name: "Audit trail" });
  await expect(table).toContainText("Patch approved");
  await expect(table).toContainText("Marcus Lee");
});
