import { expect, test } from "@playwright/test";

import { PEOPLE, WORKSPACE, requirePassword, signIn, signInWithForm } from "../helpers";

test("the owner signs in and lands on the workspace overview", async ({ page }) => {
  await signIn(page, "owner");
  await expect(page).toHaveURL(new RegExp(`/w/${WORKSPACE}$`));
  await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
  await expect(page.getByText("Awaiting review", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Workspace" }).getByRole("link")).toHaveCount(7);
});

test("a wrong password is refused with a clear message", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(PEOPLE.owner.email);
  await page.getByLabel("Password").fill(`${requirePassword()}-wrong`);
  await page.getByRole("button", { name: "Sign in" }).click();
  // Next.js keeps an empty role="alert" route announcer in every page: pick ours by its text.
  await expect(page.getByRole("alert").filter({ hasText: "Email or password is incorrect." })).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

test("signed-out visitors are sent to sign in, then back where they were going", async ({ page }) => {
  await page.goto(`/w/${WORKSPACE}/tasks`);
  await expect(page).toHaveURL(/\/login\?next=/);
  await page.getByLabel("Email").fill(PEOPLE.viewer.email);
  await page.getByLabel("Password").fill(requirePassword());
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(new RegExp(`/w/${WORKSPACE}/tasks`));
  await expect(page.getByRole("heading", { name: "Tasks", level: 1 })).toBeVisible();
});

test("signing out ends the session", async ({ page }) => {
  // Its own sign-in: signing out revokes the session, and the shared one must stay valid.
  await signInWithForm(page, "viewer");
  await page.getByRole("button", { name: `Account menu for ${PEOPLE.viewer.name}` }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto(`/w/${WORKSPACE}`);
  await expect(page).toHaveURL(/\/login\?next=/);
});

test("a workspace the person does not belong to does not exist for them", async ({ page }) => {
  await signIn(page, "viewer");
  await page.goto("/w/someone-elses-workspace");
  await expect(page.getByText("Workspace not found")).toBeVisible();
});
