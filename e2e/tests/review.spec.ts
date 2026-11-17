/**
 * The whole path of a change in a workspace of its own: connect a repository by uploading
 * an archive, wait for the index, ask the agent for a helper, review its diff, approve it
 * and apply it to a branch. The seeded demo workspace is never touched.
 */
import { expect, test } from "@playwright/test";

import { sampleArchive, scratchWorkspace, signIn } from "../helpers";

test.describe.configure({ mode: "serial" });
test.setTimeout(300_000);

let workspace = "";

test("a repository is connected from an archive and indexed", async ({ page }) => {
  await signIn(page, "owner");
  workspace = await scratchWorkspace(page);
  await page.goto(`/w/${workspace}/repos`);
  await page.getByRole("button", { name: "Connect repository" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Connect a repository" });
  await dialog.getByLabel("Archive").setInputFiles(sampleArchive("ledgerkit"));
  await dialog.getByRole("button", { name: "Connect and index" }).click();

  await expect(page).toHaveURL(new RegExp(`/w/${workspace}/repos/ledgerkit$`));
  await expect(page.getByRole("link", { name: "Browse code" })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByRole("heading", { name: "Languages" })).toBeVisible();
  await expect(page.getByText("Symbols", { exact: true }).first()).toBeVisible();
});

test("the repository's tests run in the sandbox and the failure is explained", async ({ page }) => {
  await signIn(page, "owner");
  await page.goto(`/w/${workspace}/repos/ledgerkit`);
  await page.getByRole("button", { name: "Run tests" }).click();
  await expect(page).toHaveURL(new RegExp(`/w/${workspace}/runs/\\d+$`));
  await expect(page.getByText("Failed", { exact: true }).first()).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("31 / 32")).toBeVisible();
  const row = page.getByRole("row", { name: /^test_discount_applies_at_threshold/ });
  await expect(row).toBeVisible();
  await expect(page.getByRole("main")).toContainText("assert");
  await expect(page.getByText("no network", { exact: false }).or(page.getByText("network: none"))).toBeVisible();
});

test("a requested helper is reviewed, approved and applied to a branch", async ({ page }) => {
  await signIn(page, "owner");
  await page.goto(`/w/${workspace}/tasks`);
  await page.getByRole("button", { name: "New task" }).first().click();
  const dialog = page.getByRole("dialog", { name: "New task" });
  await dialog.getByLabel("Title").fill("Add a clamp helper");
  await dialog.getByLabel("Description").fill("add `clamp` to ledgerkit/pricing.py");
  await dialog.getByRole("button", { name: "Create task" }).click();
  await expect(page).toHaveURL(new RegExp(`/w/${workspace}/tasks/1$`));

  await expect(page.getByText("Awaiting review", { exact: true }).first()).toBeVisible({ timeout: 180_000 });
  const diff = page.getByRole("region", { name: "Changes to ledgerkit/pricing.py" });
  await expect(diff).toContainText("def clamp(");
  await expect(page.getByRole("region", { name: "Changes to tests/test_pricing.py" })).toBeVisible();
  // The suite ran before and after the change.
  await expect(page.getByRole("link", { name: /Before/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /After/ })).toBeVisible();

  // A line comment, anchored to the added line.
  await diff
    .getByRole("button", { name: /^Comment on new line \d+ of ledgerkit\/pricing\.py/ })
    .first()
    .click({ force: true });
  await page.getByLabel(/^Comment on line \d+$/).fill("Please also cover negative bounds.");
  await diff.getByRole("button", { name: "Comment", exact: true }).click();
  await expect(diff.getByText("Please also cover negative bounds.")).toBeVisible();

  await page.getByLabel("Decision note").fill("Looks right.");
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Looks right.")).toBeVisible();
  await expect(page.getByText("Approved", { exact: true }).first()).toBeVisible();

  await page.getByRole("button", { name: "Apply to a new branch" }).click();
  await expect(page.getByText("Applied to a branch")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText(/codeagent\/1-add-a-clamp-helper/).first()).toBeVisible();

  // The export is a real download.
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: ".patch" }).click(),
  ]);
  expect(download.suggestedFilename()).toBe("codeagent-task-1-r1.patch");
});

test("a request the offline planner cannot do fails with guidance, and can be retried", async ({ page }) => {
  await signIn(page, "owner");
  await page.goto(`/w/${workspace}/tasks`);
  await page.getByRole("button", { name: "New task" }).first().click();
  const dialog = page.getByRole("dialog", { name: "New task" });
  await dialog.getByLabel("Title").fill("Make invoices prettier");
  await dialog.getByLabel("Description").fill("Improve the layout of the text export.");
  await dialog.getByRole("button", { name: "Create task" }).click();
  await expect(page.getByText("Failed", { exact: true }).first()).toBeVisible({ timeout: 120_000 });
  await expect(page.getByRole("alert").filter({ hasText: "LLM_PROVIDER" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
});
