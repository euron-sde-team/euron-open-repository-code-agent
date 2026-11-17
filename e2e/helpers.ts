import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { expect, type Page } from "@playwright/test";

export const API_URL = process.env.API_URL ?? "http://localhost:8190";
export const WEB_URL = process.env.WEB_URL ?? "http://localhost:3190";
export const PASSWORD = process.env.DEMO_PASSWORD ?? "";
export const WORKSPACE = "northwind-engineering";

export const PEOPLE = {
  owner: { email: "priya.raman@example.com", name: "Priya Raman" },
  maintainer: { email: "marcus.lee@example.com", name: "Marcus Lee" },
  developer: { email: "sofia.alvarez@example.com", name: "Sofia Alvarez" },
  viewer: { email: "tom.becker@example.com", name: "Tom Becker" },
} as const;

export type Person = keyof typeof PEOPLE;

export function requirePassword(): string {
  if (!PASSWORD) throw new Error("Set DEMO_PASSWORD (make e2e reads it from deploy/compose/.env)");
  return PASSWORD;
}

const SESSIONS = path.resolve(__dirname, ".auth");

/** Sign in through the form, exactly as a person does. */
export async function signInWithForm(page: Page, who: Person = "owner"): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(PEOPLE[who].email);
  await page.getByLabel("Password").fill(requirePassword());
  await page.getByRole("button", { name: "Sign in" }).click();
  // The home page opens the person's first workspace, which is not always the demo one
  // (earlier runs leave scratch workspaces behind): go to the demo workspace explicitly.
  await expect(page).not.toHaveURL(/\/login/);
  await page.goto(`/w/${WORKSPACE}`);
  await expect(page).toHaveURL(new RegExp(`/w/${WORKSPACE}`));
}

/**
 * A signed-in page for one demo person. The session cookie from the first form sign-in is
 * saved per role and reused by later tests: the API allows ten sign-ins a minute per
 * address, and the suites would otherwise trip that limit themselves. A stale cookie (after
 * `make down`) falls back to the form.
 */
export async function signIn(page: Page, who: Person = "owner"): Promise<void> {
  const saved = path.join(SESSIONS, `${who}.json`);
  if (existsSync(saved)) {
    await page.context().addCookies(JSON.parse(readFileSync(saved, "utf8")));
    // Ask the API, not the page: a stale cookie only shows as a redirect after the page loads.
    const session = await page.request.get(`${API_URL}/api/v1/auth/me`);
    if (session.ok()) {
      await page.goto(`/w/${WORKSPACE}`);
      return;
    }
    await page.context().clearCookies();
  }
  await signInWithForm(page, who);
  mkdirSync(SESSIONS, { recursive: true });
  writeFileSync(saved, JSON.stringify(await page.context().cookies()));
}

const base = (workspace: string) => `${API_URL}/api/v1/workspaces/${workspace}`;

/** GET a workspace API path with the page's session; returns the parsed body. */
export async function apiGet<T>(page: Page, apiPath: string, workspace = WORKSPACE): Promise<T> {
  const response = await page.request.get(`${base(workspace)}${apiPath}`);
  expect(response.ok(), apiPath).toBeTruthy();
  return (await response.json()) as T;
}

/**
 * Send a request to the API as the signed-in person. Unsafe methods must come from the
 * web app's own origin (the API's CSRF check), so the origin header is set the way the
 * browser would set it.
 */
export async function apiSend<T>(
  page: Page,
  method: "POST" | "PATCH" | "PUT" | "DELETE",
  apiPath: string,
  data?: unknown,
  workspace = WORKSPACE,
): Promise<T> {
  const response = await page.request.fetch(`${base(workspace)}${apiPath}`, {
    method,
    data,
    headers: { origin: WEB_URL },
  });
  expect(response.ok(), `${method} ${apiPath}: ${await response.text()}`).toBeTruthy();
  return (response.status() === 204 ? undefined : await response.json()) as T;
}

/** A name for throwaway data that no other run or demo person shares. */
export function unique(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

/** A gzip tarball of one of the bundled sample repositories, for the upload dialog. */
export function sampleArchive(name: "ledgerkit" | "ratelimit" | "checkout-web"): string {
  const root = path.resolve(__dirname, "../apps/api/src/codeagent/demo/repos");
  const out = path.join(mkdtempSync(path.join(os.tmpdir(), "codeagent-e2e-")), `${name}.tar.gz`);
  execFileSync("tar", ["-czf", out, "--exclude", "__pycache__", "-C", root, name]);
  return out;
}

/** A workspace of its own, so specs that change data never touch what the screenshots show. */
export async function scratchWorkspace(page: Page): Promise<string> {
  const response = await page.request.fetch(`${API_URL}/api/v1/workspaces`, {
    method: "POST",
    data: { name: unique("E2E workspace") },
    headers: { origin: WEB_URL },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  return ((await response.json()) as { slug: string }).slug;
}

/** Wait until the page has settled: no pending network, fonts ready, transitions finished. */
export async function settle(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle");
  await page.evaluate(async () => {
    await document.fonts.ready;
    // Spinners and pulsing dots repeat forever; only wait for animations that end.
    const finite = document
      .getAnimations()
      .filter((animation) => animation.effect?.getTiming().iterations !== Infinity);
    await Promise.all(finite.map((animation) => animation.finished.catch(() => undefined)));
  });
}
