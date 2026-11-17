/**
 * README screenshots (1440x900 at 2x) and tour frames, from the seeded demo workspace.
 * Every image shows the real stack: nothing here is mocked.
 */
import { mkdirSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { WORKSPACE, apiGet, settle, signIn } from "../helpers";

const SHOTS = path.resolve(__dirname, "../../docs/assets/screenshots");
const FRAMES = path.resolve(__dirname, "../.capture/frames");
mkdirSync(SHOTS, { recursive: true });
mkdirSync(FRAMES, { recursive: true });

const BASE = `/w/${WORKSPACE}`;
let frame = 0;

async function shot(page: Page, name: string): Promise<void> {
  await settle(page);
  // The clicked control keeps a keyboard focus ring: the picture is of the page.
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
}

async function tourFrame(page: Page, holdMs = 1800): Promise<void> {
  frame += 1;
  const file = path.join(FRAMES, `${String(frame).padStart(3, "0")}-${holdMs}.png`);
  await page.screenshot({ path: file, scale: "css" });
}

/** Scroll the app's own scroll area (the page itself never scrolls). */
async function scrollMain(page: Page, to: number): Promise<void> {
  await page.evaluate((top) => document.querySelector("main")?.scrollTo(0, top), to);
  await page.waitForTimeout(250);
}

type Item = { number: number };

test.describe.configure({ mode: "serial" });
// Captures run on a busy laptop as often as on CI: allow slow answers rather than flake.
test.setTimeout(300_000);

test("sign-in page", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByText("Understand your code. Change it with review.")).toBeVisible();
  await shot(page, "00-sign-in");
  await tourFrame(page, 1600);
});

test("the web app, page by page", async ({ page }) => {
  await signIn(page, "owner");
  const review = (await apiGet<{ items: Item[] }>(page, "/tasks?status=awaiting_review")).items[0]!;
  const applied = (await apiGet<{ items: Item[] }>(page, "/tasks?status=applied")).items[0]!;
  const run = (await apiGet<{ items: Item[] }>(page, "/test-runs?status=failed&trigger=manual&limit=1")).items[0]!;

  await page.goto(BASE);
  await expect(page.locator(".recharts-bar-rectangle, .recharts-area").first()).toBeVisible();
  await expect(page.getByText("Recent work")).toBeVisible();
  await shot(page, "01-overview");
  await tourFrame(page, 2400);

  await page.goto(`${BASE}/repos`);
  await expect(page.getByText("Ready").first()).toBeVisible();
  await shot(page, "02-repositories");
  await tourFrame(page, 2200);

  await page.goto(`${BASE}/repos/ledgerkit`);
  await expect(page.getByRole("heading", { name: "Languages" })).toBeVisible();
  await expect(page.getByText("Recent test runs")).toBeVisible();
  await shot(page, "03-repository");

  await page.goto(`${BASE}/repos/ledgerkit/code/ledgerkit/pricing.py#L18-L24`);
  const aside = page.getByRole("complementary", { name: "Symbols" });
  await aside.getByRole("button", { name: /apply_discount/ }).click();
  await aside.getByRole("tab", { name: "Symbol" }).click();
  await expect(aside.getByRole("region", { name: "Called by" })).toBeVisible();
  await shot(page, "04-code-browser");
  await tourFrame(page, 2800);

  await page.goto(`${BASE}/search?q=discount`);
  await expect(page.getByRole("link", { name: /apply_discount/ }).first()).toBeVisible();
  await shot(page, "05-search-symbols");
  await tourFrame(page, 2000);

  await page.goto(`${BASE}/search?mode=text&q=Decimal`);
  await expect(page.locator("mark").first()).toBeVisible();
  await shot(page, "06-search-text");

  await page.goto(`${BASE}/ask`);
  await page.getByLabel("Your question").fill("What does apply_discount do and which tests cover it?");
  await page.getByLabel("Your question").press("Enter");
  await expect(page.getByRole("region", { name: "Sources" })).toBeVisible();
  await page.getByRole("region", { name: "Sources" }).getByRole("button").first().click();
  await expect(page.getByText("Answered by").last()).toBeVisible();
  await shot(page, "07-ask");
  await tourFrame(page, 3200);

  await page.goto(`${BASE}/tasks`);
  await expect(page.getByRole("list", { name: "Tasks" }).getByRole("listitem")).not.toHaveCount(0);
  await shot(page, "08-tasks");
  await tourFrame(page, 2200);

  await page.goto(`${BASE}/tasks/${review.number}`);
  await expect(page.getByRole("region", { name: /^Changes to / }).first()).toBeVisible();
  await shot(page, "09-review-diff");
  await tourFrame(page, 3000);
  await scrollMain(page, 700);
  await shot(page, "10-review-discussion");

  await page.goto(`${BASE}/tasks/${applied.number}`);
  await expect(page.getByText("Applied to a branch")).toBeVisible();
  await shot(page, "11-task-applied");

  await page.goto(`${BASE}/runs`);
  await expect(page.getByRole("region", { name: "Test runs" })).toBeVisible();
  await shot(page, "12-test-runs");
  await tourFrame(page, 2000);

  await page.goto(`${BASE}/runs/${run.number}`);
  await expect(page.getByRole("region", { name: "Test results" })).toBeVisible();
  await shot(page, "13-test-run");
  await tourFrame(page, 2600);

  await page.goto(`${BASE}/settings?tab=keys`);
  await expect(page.getByRole("region", { name: "API keys" })).toBeVisible();
  await shot(page, "14-api-keys");

  await page.goto(`${BASE}/settings?tab=engine`);
  await expect(page.getByText("Sandbox")).toBeVisible();
  await shot(page, "15-engine");
});

test("the dark theme", async ({ page }) => {
  await signIn(page, "owner");
  await page.evaluate(() => localStorage.setItem("codeagent-theme", "dark"));
  const review = (await apiGet<{ items: Item[] }>(page, "/tasks?status=awaiting_review")).items[0]!;
  await page.goto(`${BASE}/tasks/${review.number}`);
  await expect(page.getByRole("region", { name: /^Changes to / }).first()).toBeVisible();
  await shot(page, "16-review-dark");
  await tourFrame(page, 2400);
  await page.evaluate(() => localStorage.removeItem("codeagent-theme"));
});
