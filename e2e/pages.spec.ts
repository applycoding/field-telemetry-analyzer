// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import path from "node:path";
import fs from "node:fs";

const ROOT = path.resolve(__dirname, "..");
const SITE = process.env.FTA_SITE_DIR ?? path.join(ROOT, "site-out");

let server: ReturnType<typeof spawn> | null = null;

test.beforeAll(async () => {
  if (!fs.existsSync(SITE)) {
    throw new Error(`missing site dir ${SITE}`);
  }
  server = spawn(
    "npx",
    ["http-server", SITE, "-p", "8765", "-c-1"],
    { stdio: "pipe", cwd: ROOT },
  );
  await new Promise((r) => setTimeout(r, 1500));
});

test.afterAll(async () => {
  server?.kill();
});

test("sample report is synthetic and 1280x720", async ({ page }) => {
  await page.goto("http://127.0.0.1:8765/index.html");
  await expect(page).toHaveTitle(/synthetic data only/i);
  await expect(page.locator("body")).toContainText(/These are not real field logs/i);
  const shot = path.join(ROOT, "e2e", "shot.png");
  await page.screenshot({
    path: shot,
    fullPage: false,
    scale: "css",
  });
  const buf = fs.readFileSync(shot);
  const w = buf.readUInt32BE(16);
  const h = buf.readUInt32BE(20);
  expect(w).toBe(1280);
  expect(h).toBe(720);
});
