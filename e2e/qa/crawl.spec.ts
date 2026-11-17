/**
 * Exploratory QA crawl: every page at desktop and mobile widths, signed in as the demo owner,
 * and once more in the dark theme.
 *
 * A page fails on console errors, uncaught exceptions, failed or 4xx/5xx requests, sideways
 * scrolling, broken internal links and serious or critical axe violations (WCAG 2 A and AA).
 * A capture of the whole of every page lands in e2e/.qa/ for a visual review.
 */
import { mkdirSync } from "node:fs";
import path from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { WORKSPACE, apiGet, settle, signIn } from "../helpers";

const OUT = path.resolve(__dirname, "../.qa");
mkdirSync(OUT, { recursive: true });

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "mobile", width: 390, height: 844 },
] as const;

const SETTINGS_TABS = ["members", "keys", "engine", "activity", "account"];

type Crawl = { page: Page; label: string; problems: string[]; links: Set<string> };

function watch(page: Page, label: string): Crawl {
  const crawl: Crawl = { page, label, problems: [], links: new Set() };
  page.on("console", (message) => {
    if (message.type() === "error") crawl.problems.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => crawl.problems.push(`uncaught: ${error.message}`));
  page.on("requestfailed", (request) => {
    const reason = request.failure()?.errorText ?? "";
    // Aborted requests are navigations away or cancelled queries, not failures.
    if (!reason.includes("ERR_ABORTED")) crawl.problems.push(`request failed: ${request.url()} ${reason}`);
  });
  page.on("response", (response) => {
    if (response.status() >= 400) crawl.problems.push(`HTTP ${response.status()}: ${response.url()}`);
  });
  return crawl;
}

/** Capture the whole page: the app scrolls inside <main>, so grow the window to fit it. */
async function captureWhole(page: Page, file: string): Promise<void> {
  const size = page.viewportSize();
  if (!size) return;
  const needed = await page.evaluate(() => {
    const main = document.querySelector("main");
    if (!main) return 0;
    return Math.ceil(main.scrollHeight + main.getBoundingClientRect().top);
  });
  const height = Math.min(Math.max(needed, size.height), 5000);
  if (height > size.height) await page.setViewportSize({ width: size.width, height });
  await page.waitForTimeout(250);
  await page.screenshot({ path: file });
  if (height > size.height) await page.setViewportSize(size);
}

async function inspect(crawl: Crawl, name: string): Promise<void> {
  const { page } = crawl;
  await settle(page);
  // The app shell scrolls inside <main>, so sideways overflow can hide there too. Code and
  // diffs scroll inside their own containers and do not count.
  const overflow = await page.evaluate(() => {
    const outer = document.documentElement.scrollWidth - window.innerWidth;
    const main = document.querySelector("main");
    return Math.max(outer, main ? main.scrollWidth - main.clientWidth : 0);
  });
  if (overflow > 1) crawl.problems.push(`${name}: scrolls sideways by ${overflow}px`);

  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  for (const violation of axe.violations) {
    if (violation.impact !== "serious" && violation.impact !== "critical") continue;
    const nodes = violation.nodes
      .slice(0, 3)
      .map((node) => node.target.join(" "))
      .join(" | ");
    crawl.problems.push(`${name}: axe ${violation.id} (${violation.impact}) at ${nodes}`);
  }

  const hrefs = await page.$$eval('a[href^="/"]', (anchors) => anchors.map((a) => a.getAttribute("href") ?? ""));
  for (const href of hrefs) crawl.links.add(href.split("#")[0] ?? href);
  await captureWhole(page, path.join(OUT, `${crawl.label}-${name}.png`));
}

/** What shows that a page has loaded: its title (a string) or some text (`{ text }`). */
type Ready = string | { text: string };

async function visit(crawl: Crawl, name: string, url: string, ready?: Ready): Promise<void> {
  const response = await crawl.page.goto(url);
  expect(response?.status(), url).toBeLessThan(400);
  if (ready) {
    // Scoped to the page content: on phones the sidebar (and its links) is off screen.
    const main = crawl.page.getByRole("main");
    const shown =
      typeof ready === "string"
        ? main.getByRole("heading", { level: 1, name: ready })
        : main.getByText(ready.text).first();
    await expect(shown).toBeVisible();
  }
  await inspect(crawl, name);
}

type Item = { number: number; status: string; trigger?: string };

/** Every page of the web app, with the states that hide things behind a click. */
async function crawlWorkspace(page: Page, crawl: Crawl): Promise<void> {
  const base = `/w/${WORKSPACE}`;
  const review = (await apiGet<{ items: Item[] }>(page, "/tasks?status=awaiting_review")).items[0]!;
  const applied = (await apiGet<{ items: Item[] }>(page, "/tasks?status=applied")).items[0]!;
  const failed = (await apiGet<{ items: Item[] }>(page, "/tasks?status=failed")).items[0]!;
  const run = (await apiGet<{ items: Item[] }>(page, "/test-runs?status=failed&trigger=manual&limit=1")).items[0]!;

  await visit(crawl, "overview", base, "Overview");
  await visit(crawl, "repos", `${base}/repos`, "Repositories");
  await visit(crawl, "repo", `${base}/repos/ledgerkit`, "ledgerkit");
  await visit(crawl, "repo-go", `${base}/repos/ratelimit`, "ratelimit");
  await visit(crawl, "code-index", `${base}/repos/ledgerkit/code`, { text: "Choose a file" });
  await visit(crawl, "code-file", `${base}/repos/ledgerkit/code/ledgerkit/pricing.py#L18-L24`, {
    text: "ledgerkit / pricing.py",
  });
  await visit(crawl, "code-typescript", `${base}/repos/checkout-web/code/src/cart.ts`, { text: "cart.ts" });

  await visit(crawl, "search-symbols", `${base}/search?q=discount`, "Search");
  await expect(page.getByRole("link", { name: /apply_discount/ }).first()).toBeVisible();
  await inspect(crawl, "search-symbols-results");
  await visit(crawl, "search-text", `${base}/search?mode=text&q=Decimal`, "Search");
  await expect(page.locator("mark").first()).toBeVisible();
  await inspect(crawl, "search-text-results");
  await visit(
    crawl,
    "search-semantic",
    `${base}/search?mode=semantic&q=${encodeURIComponent("calculate tax")}`,
    "Search",
  );
  await expect(page.getByRole("link", { name: /ledgerkit\/tax\.py/ }).first()).toBeVisible();
  await inspect(crawl, "search-semantic-results");

  await visit(crawl, "ask", `${base}/ask`, { text: "Ask about your code" });
  await page.getByLabel("Your question").fill("What does apply_discount do and which tests cover it?");
  await page.getByLabel("Your question").press("Enter");
  await expect(page.getByRole("region", { name: "Sources" })).toBeVisible();
  await inspect(crawl, "ask-answer");

  await visit(crawl, "tasks", `${base}/tasks`, "Tasks");
  await visit(crawl, "tasks-review", `${base}/tasks?status=awaiting_review`, "Tasks");
  await visit(crawl, "task-review", `${base}/tasks/${review.number}`, { text: "Agent trace" });
  await expect(page.getByRole("region", { name: /^Changes to / }).first()).toBeVisible();
  await inspect(crawl, "task-review-loaded");
  await visit(crawl, "task-applied", `${base}/tasks/${applied.number}`, { text: "Applied to a branch" });
  await visit(crawl, "task-failed", `${base}/tasks/${failed.number}`, { text: "Agent trace" });
  await page.goto(`${base}/tasks`);
  await page.getByRole("button", { name: "New task" }).click();
  await expect(page.getByRole("dialog", { name: "New task" })).toBeVisible();
  await inspect(crawl, "task-new-dialog");
  await page.keyboard.press("Escape");

  await visit(crawl, "runs", `${base}/runs`, "Test runs");
  await visit(crawl, "run", `${base}/runs/${run.number}`, `Test run #${run.number}`);

  await visit(crawl, "settings", `${base}/settings`, "Settings");
  for (const tab of SETTINGS_TABS) {
    await visit(crawl, `settings-${tab}`, `${base}/settings?tab=${tab}`, "Settings");
  }
}

for (const viewport of VIEWPORTS) {
  test.describe(`${viewport.name} ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });
    test.setTimeout(600_000);

    test("signed-out pages", async ({ page }) => {
      const crawl = watch(page, viewport.name);
      await visit(crawl, "sign-in", "/login", { text: "Welcome back" });
      expect(crawl.problems).toEqual([]);
    });

    test("every workspace page", async ({ page }) => {
      await signIn(page, "owner");
      const crawl = watch(page, viewport.name);
      await crawlWorkspace(page, crawl);
      expect(crawl.problems, crawl.problems.join("\n")).toEqual([]);

      // Every internal link the crawl saw leads somewhere that exists.
      const broken: string[] = [];
      for (const href of crawl.links) {
        if (href.startsWith("/api/") || href === "") continue;
        const response = await page.request.get(href.startsWith("http") ? href : new URL(href, page.url()).toString());
        if (response.status() >= 400) broken.push(`${response.status()} ${href}`);
      }
      expect(broken, "broken internal links").toEqual([]);
    });
  });
}

test.describe("dark theme", () => {
  test.use({ viewport: { width: 1440, height: 900 }, colorScheme: "dark" });
  test.setTimeout(600_000);

  test("every workspace page", async ({ page }) => {
    await signIn(page, "owner");
    await page.evaluate(() => localStorage.setItem("codeagent-theme", "dark"));
    const crawl = watch(page, "dark");
    await crawlWorkspace(page, crawl);
    expect(crawl.problems, crawl.problems.join("\n")).toEqual([]);
  });
});
