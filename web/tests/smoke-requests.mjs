#!/usr/bin/env node
/**
 * Idle request counter: a page that has finished loading must go quiet.
 *
 * Opens each page at 1440x900, waits for load, then counts every request the page makes
 * during 10 seconds of doing nothing. A prefetch that redirects to itself shows up here as
 * hundreds of requests. Fails when any page makes more than MAX_IDLE_REQUESTS.
 *
 *   NODE_PATH=$(npm root -g) node web/tests/smoke-requests.mjs http://localhost:3000
 *
 * Needs the `playwright` package (global install is fine) and its Chromium.
 */
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE = (process.argv[2] || process.env.WEB_URL || "http://localhost:3000").replace(/\/$/, "");
const PAGES = (process.env.SMOKE_PAGES || "/,/faq,/uk/faq,/shop").split(",");
const IDLE_MS = Number(process.env.SMOKE_IDLE_MS || 10000);
const MAX_IDLE_REQUESTS = Number(process.env.MAX_IDLE_REQUESTS || 60);

const browser = await chromium.launch();
let failed = false;
try {
  for (const path of PAGES) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    let counting = false;
    let idle = 0;
    const redirects = [];
    page.on("request", (req) => {
      if (!counting) return;
      idle += 1;
      const from = req.redirectedFrom();
      if (from) redirects.push(from.url());
    });
    const res = await page.goto(BASE + path, { waitUntil: "load", timeout: 30000 });
    await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
    counting = true;
    await page.waitForTimeout(IDLE_MS);
    counting = false;
    const ok = res && res.status() < 400 && idle <= MAX_IDLE_REQUESTS;
    if (!ok) failed = true;
    console.log(`${ok ? "PASS" : "FAIL"} ${path} status=${res ? res.status() : "none"} idle_requests=${idle} (max ${MAX_IDLE_REQUESTS})${redirects.length ? ` redirects=${redirects.length} e.g. ${redirects[0]}` : ""}`);
    await context.close();
  }
} finally {
  await browser.close();
}
process.exit(failed ? 1 : 0);
