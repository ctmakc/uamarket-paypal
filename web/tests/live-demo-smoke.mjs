#!/usr/bin/env node
/**
 * End-to-end smoke of the hosted demo, through its public address only. Prints PASS/FAIL per check.
 *
 *   ADMIN_PASSWORD=… NODE_PATH=$(npm root -g) node web/tests/live-demo-smoke.mjs \
 *     https://market.agintent.com <out dir> [mailpit base, e.g. http://127.0.0.1:18425]
 *
 * browse → bag → checkout with the test card → the order in /admin → pack → ship → the buyer's
 * status page. It places one demo order (buyer smoke-…@example.test) and never enters a wrong
 * password, so the sign-in lock is not touched.
 */
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const [baseArg, out = ".", mailpit = ""] = process.argv.slice(2);
const base = (baseArg || "").replace(/\/$/, "");
const PASSWORD = process.env.ADMIN_PASSWORD || "";
const T = { timeout: 45000 };
const RUN = Date.now().toString(36).slice(-5);
let fails = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${!ok && detail ? ` — ${detail}` : ""}`);
  if (!ok) fails += 1;
  return ok;
};

const browser = await chromium.launch();
const errors = [];
try {
  // ------------------------------------------------------------------ public pages
  const buyer = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const bp = await buyer.newPage();
  bp.on("console", (m) => m.type() === "error" && errors.push(`${bp.url()}: ${m.text()}`));
  const home = await bp.goto(`${base}/`, T);
  check("home answers 200 over HTTPS", home.status() === 200 && base.startsWith("https://"), String(home.status()));
  check("home carries the demo strip", (await bp.locator("[data-demo-strip]").count()) === 1);
  check("home carries meta robots noindex", /noindex/.test((await bp.locator('meta[name="robots"]').getAttribute("content")) || ""));
  check("X-Robots-Tag noindex header", /noindex/.test(home.headers()["x-robots-tag"] || ""), home.headers()["x-robots-tag"]);
  const robots = await (await buyer.request.get(`${base}/robots.txt`)).text();
  check("robots.txt disallows everything", /Disallow: \/\s/.test(robots + "\n"), robots.slice(0, 80));
  const api = await buyer.request.get(`${base}/v1/storefront/config`);
  check("the API is not reachable from outside (404)", api.status() === 404, String(api.status()));
  await bp.screenshot({ path: `${out}/live-1-home-390.png` });

  await bp.goto(`${base}/shop`, T);
  const tile = bp.locator("a.tile").first();
  const href = await tile.getAttribute("href");
  check("the shop lists products", Boolean(href), href || "");
  await bp.goto(`${base}${href}`, T);
  await bp.screenshot({ path: `${out}/live-2-product-390.png` });
  await bp.locator(".stack button.btn--red").first().click();
  await bp.waitForFunction(() => (JSON.parse(localStorage.getItem("uamarket.bag.v2") || "[]")[0] || {}).qty >= 1, null, T);
  check("add to bag", true);

  await bp.goto(`${base}/checkout`, T);
  await bp.waitForSelector("#email", T);
  const checkoutText = (await bp.textContent("main")) || "";
  check("checkout promises no email in the demo", /sends no email/i.test(checkoutText), checkoutText.slice(0, 200));
  await bp.fill("#email", `smoke-${RUN}@example.test`);
  await bp.fill("#name", "Demo Smoke");
  await bp.fill("#street1", "1 Test Street");
  await bp.fill("#city", "Kanata");
  await bp.selectOption("#province", "ON");
  await bp.fill("#postal", "K2K 1X1");
  await bp.check("[data-accept-terms]");
  await bp.screenshot({ path: `${out}/live-3-checkout-390.png`, fullPage: true });
  await bp.locator("form button.btn--red[type=submit]").click();
  await bp.waitForURL(/\/pay\/test\//, T);
  const payText = (await bp.textContent("[data-test-pay-page]")) || "";
  const orderNumber = (payText.match(/UA-\d{6}-[A-Z0-9]{4}/) || [])[0];
  await bp.screenshot({ path: `${out}/live-4-test-pay-390.png`, fullPage: true });
  await bp.click("[data-test-pay]");
  await bp.waitForURL(/\/order\/.*paid=1/, T);
  check("order placed and paid with the test card", Boolean(orderNumber), payText.slice(0, 120));
  await bp.screenshot({ path: `${out}/live-5-order-paid-390.png`, fullPage: true });

  // ------------------------------------------------------------------ the owner's admin
  const owner = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await owner.newPage();
  page.on("console", (m) => m.type() === "error" && errors.push(`${page.url()}: ${m.text()}`));
  await page.goto(`${base}/admin/login`, T);
  await page.fill("input[type=password]", PASSWORD);
  await Promise.all([page.waitForURL(`${base}/admin`, T), page.click("button[type=submit]")]);
  check("admin sign-in", page.url() === `${base}/admin`, page.url());
  await page.goto(`${base}/admin?queue=to_pack`, T);
  const row = page.locator(`a.adm-row[data-order="${orderNumber}"]`);
  check("the paid order is in the admin queue under To pack", (await row.count()) === 1);
  await page.screenshot({ path: `${out}/live-6-admin-queue-1440.png` });
  await row.click();
  await page.waitForSelector("[data-testid=scan-input]", T);
  const barcodes = (await page.locator("[data-testid=line-barcode]").allTextContents()).map((s) => s.trim()).filter(Boolean);
  for (const code of barcodes) {
    await page.fill("[data-testid=scan-input]", code);
    await page.keyboard.press("Enter");
    await page.waitForTimeout(1200);
  }
  await page.waitForSelector("[data-testid=weight-input]", T);
  check("scanning the item moves the order to packing", (await page.getAttribute(".adm-order", "data-next")) === "pack");
  await page.fill("[data-testid=weight-input]", "480");
  await page.locator("[data-testid=weight-input]").locator("xpath=ancestor::form").locator("button[type=submit]").click();
  await page.waitForSelector("[data-testid=tracking-input]", T);
  const tracking = `DEMO${RUN.toUpperCase()}CA`;
  await page.fill("[data-testid=carrier-input]", "Canada Post");
  await page.fill("[data-testid=tracking-input]", tracking);
  await page.locator("[data-testid=tracking-input]").locator("xpath=ancestor::form").locator("button[type=submit]").click();
  await page.waitForSelector("[data-testid=shipped-tracking]", T);
  check("marked shipped with tracking in the admin", ((await page.textContent("[data-testid=shipped-tracking]")) || "").includes(tracking));
  await page.waitForTimeout(800);
  await page.reload();
  await page.screenshot({ path: `${out}/live-7-admin-shipped-1440.png`, fullPage: true });

  // ------------------------------------------------------------------ the buyer sees the status
  await bp.goto(`${base}/order/${orderNumber}`, T);
  await bp.waitForSelector("[data-tracking]", T);
  const statusBody = (await bp.textContent("main")) || "";
  check("the buyer's order page shows Shipped and the tracking", statusBody.includes("Shipped") && statusBody.includes(tracking));
  await bp.screenshot({ path: `${out}/live-8-buyer-status-390.png`, fullPage: true });

  if (mailpit) {
    const mp = await browser.newPage();
    let subjects = [];
    for (let i = 0; i < 15 && !subjects.some((s) => /shipped/i.test(s)); i += 1) {
      const res = await mp.request.get(`${mailpit}/api/v1/messages?limit=200`);
      subjects = ((await res.json()).messages || []).map((m) => m.Subject).filter((s) => s.includes(orderNumber));
      if (!subjects.some((s) => /shipped/i.test(s))) await mp.waitForTimeout(1000);
    }
    check("the internal Mailpit caught the order emails (nothing leaves the machine)", subjects.some((s) => /shipped/i.test(s)), subjects.join(" | "));
  }
  check("no console errors on the pages walked", errors.length === 0, errors.slice(0, 3).join(" || "));
  console.log(`order ${orderNumber}`);
} catch (e) {
  check("flow finished without an exception", false, String(e).slice(0, 400));
} finally {
  await browser.close();
}
console.log(fails ? `${fails} FAILED` : "ALL PASS");
process.exit(fails ? 1 : 0);
