import { expect, test } from "@playwright/test";

import { WORKSPACE, apiGet, signIn } from "../helpers";

type Task = { number: number; status: string };
type TaskPage = { items: Task[] };

test("a viewer reads everything and is offered nothing to change", async ({ page }) => {
  await signIn(page, "viewer");

  await page.goto(`/w/${WORKSPACE}/repos`);
  await expect(page.getByRole("heading", { name: "Repositories", level: 1 })).toBeVisible();
  await expect(page.getByRole("button", { name: "Connect repository" })).toHaveCount(0);

  await page.goto(`/w/${WORKSPACE}/tasks`);
  await expect(page.getByRole("button", { name: "New task" })).toHaveCount(0);

  const open = await apiGet<TaskPage>(page, "/tasks?status=awaiting_review");
  await page.goto(`/w/${WORKSPACE}/tasks/${open.items[0]!.number}`);
  await expect(page.getByText("A maintainer approves or rejects proposed patches.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Comment on / })).toHaveCount(0);

  await page.goto(`/w/${WORKSPACE}/settings`);
  await expect(page.getByRole("tab", { name: "API keys" })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Activity" })).toHaveCount(0);
});

test("a developer can ask for changes and comment, but not decide", async ({ page }) => {
  await signIn(page, "developer");
  await page.goto(`/w/${WORKSPACE}/tasks`);
  await expect(page.getByRole("button", { name: "New task" })).toBeVisible();
  const open = await apiGet<TaskPage>(page, "/tasks?status=awaiting_review");
  await page.goto(`/w/${WORKSPACE}/tasks/${open.items[0]!.number}`);
  await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Comment on / }).first()).toBeAttached();
});

test("the requester cannot approve their own task in a workspace that requires independent review", async ({
  page,
}) => {
  // The demo workspace requires it. Task 4 was asked for by Marcus, who is a maintainer.
  await signIn(page, "maintainer");
  await page.goto(`/w/${WORKSPACE}/tasks/4`);
  await expect(page.getByText("requires an independent review")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(0);

  await signIn(page, "owner");
  await page.goto(`/w/${WORKSPACE}/tasks/4`);
  await expect(page.getByRole("button", { name: "Approve" })).toBeVisible();
});
