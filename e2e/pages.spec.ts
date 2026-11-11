// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
import http from "node:http";

const ROOT = path.resolve(__dirname, "..");
const SITE = process.env.FTA_SITE_DIR ?? path.join(ROOT, "site-out");

const IMAGE_NAMES = [
  "imu.png",
  "pose_path.png",
  "pose_time.png",
  "actuator.png",
  "clock_offset.png",
  "flags.png",
];

let server: ChildProcess | null = null;

async function waitForServer(port: number, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const ok = await new Promise<boolean>((resolve) => {
      const req = http.get(`http://127.0.0.1:${port}/index.html`, (res) => {
        res.resume();
        resolve(res.statusCode === 200);
      });
      req.on("error", () => resolve(false));
      req.setTimeout(2000, () => {
        req.destroy();
        resolve(false);
      });
    });
    if (ok) {
      return;
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error("http-server did not become ready");
}

test.beforeAll(async () => {
  if (!fs.existsSync(SITE)) {
    throw new Error(`missing site dir ${SITE}`);
  }
  server = spawn(
    "npx",
    ["http-server", SITE, "-p", "8765", "-c-1"],
    { stdio: "pipe", cwd: ROOT },
  );
  await waitForServer(8765, 15000);
});

test.afterAll(async () => {
  server?.kill();
});

test("sample report is synthetic and 1280x720", async ({ page }) => {
  await page.goto("http://127.0.0.1:8765/index.html", { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  await expect(page).toHaveTitle(/synthetic data only/i);
  await expect(page.locator("body")).toContainText(/These are not real field logs/i);
  for (const name of IMAGE_NAMES) {
    const img = page.locator(`img[src="${name}"]`);
    await expect(img).toHaveCount(1);
    await page.waitForFunction(
      (sel) => {
        const el = document.querySelector(sel) as HTMLImageElement | null;
        return Boolean(el && el.complete && el.naturalWidth > 0);
      },
      `img[src="${name}"]`,
    );
  }
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
