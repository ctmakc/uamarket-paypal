#!/usr/bin/env node
/**
 * Browser half of scripts/e2e_local.sh. Headless Chromium only.
 *
 *   node scripts/e2e/purchase.mjs buy <base> <lang> <out-dir>          -> prints {"order":"UA-…","email":"…"}
 *   node scripts/e2e/purchase.mjs second <base> <sku> <out-dir>        -> exit 0 when the second buyer is stopped
 *   node scripts/e2e/purchase.mjs status <base> <lang> <order> <email> <tracking> <out-dir>
 */
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const [mode, base, ...rest] = process.argv.slice(2);
const T = { timeout: 30000 };
// E2E_INSECURE_TLS=1: the local production rehearsal behind Caddy's internal certificate authority.
const INSECURE = process.env.E2E_INSECURE_TLS === "1";
const browser = await chromium.launch();

function log(msg) {
  process.stderr.write(`  · ${msg}\n`);
}

async function fillCheckout(page, email) {
  await page.waitForSelector("#email", T);
  await page.fill("#email", email);
  await page.fill("#name", "E2E Buyer");
  await page.fill("#street1", "1 Test Street");
  await page.fill("#city", "Kanata");
  await page.selectOption("#province", "ON");
  await page.fill("#postal", "K2K 1X1");
  await page.check("[data-accept-terms]");
}

try {
  if (mode === "buy") {
    const [lang, out] = rest;
    const prefix = lang === "uk" ? "/uk" : "";
    const email = `e2e-${lang}-${Date.now()}@example.test`;
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, ignoreHTTPSErrors: INSECURE });
    const page = await ctx.newPage();
    await page.goto(`${base}${prefix}/product/opishnia-mug`, T);
    log(`product page ${lang}`);
    const add = page.locator(".stack button.btn--red").first();
    await add.click();
    await page.waitForFunction(() => (JSON.parse(localStorage.getItem("uamarket.bag.v2") || "[]")[0] || {}).qty >= 1, null, T);
    await page.goto(`${base}${prefix}/bag`, T);
    await page.waitForSelector(".bag-line", T);
    log("bag");
    await page.goto(`${base}${prefix}/checkout`, T);
    await fillCheckout(page, email);
    await page.screenshot({ path: `${out}/checkout-${lang}-390.png` });
    const demoLine = await page.locator("[data-demo-line]").count();
    await page.locator("form button.btn--red[type=submit]").click();
    await page.waitForURL(/\/pay\/test\//, T);
    log("test payment page");
    await page.screenshot({ path: `${out}/paytest-${lang}-390.png` });
    const text = (await page.textContent("[data-test-pay-page]")) || "";
    const order = (text.match(/UA-\d{6}-[A-Z0-9]{4}/) || [])[0];
    // The checkout set this order's key in a cookie: the address carries the number only.
    await page.goto(`${base}${prefix}/order/${order}`, T);
    const demoNote = await page.locator("[data-order-demo]").count();
    await page.screenshot({ path: `${out}/order-unpaid-${lang}-390.png`, fullPage: true });
    await page.goBack();
    await page.waitForSelector("[data-test-pay]", T);
    await page.click("[data-test-pay]");
    await page.waitForURL(/\/order\/.*paid=1/, T);
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/order-paid-${lang}-390.png` });
    console.log(JSON.stringify({ order, email, demoLine, demoNote }));
    await ctx.close();
  } else if (mode === "second") {
    const [sku, out] = rest;
    const results = [];
    for (const who of ["first", "second"]) {
      const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, ignoreHTTPSErrors: INSECURE });
      const page = await ctx.newPage();
      await page.goto(`${base}/shop`, T);
      await page.evaluate((s) => localStorage.setItem("uamarket.bag.v2", JSON.stringify([{ sku: s, slug: "opishnia-mug", qty: 1 }])), sku);
      await page.goto(`${base}/checkout`, T);
      await fillCheckout(page, `e2e-${who}-${Date.now()}@example.test`);
      const button = page.locator("form button.btn--red[type=submit]");
      await page.waitForTimeout(1500); // the quote arrives
      if (await button.isDisabled()) {
        results.push({ who, reachedPayment: false });
      } else {
        await button.click();
        const reached = await page.waitForURL(/\/pay\/test\//, { timeout: 8000 }).then(() => true).catch(() => false);
        results.push({ who, reachedPayment: reached });
        if (reached) await page.goBack().catch(() => {});
      }
      await page.locator("form button.btn--red[type=submit]").scrollIntoViewIfNeeded().catch(() => {});
      await page.screenshot({ path: `${out}/stock1-${who}-390.png` });
      await ctx.close();
    }
    console.log(JSON.stringify(results));
    process.exitCode = results[0].reachedPayment && !results[1].reachedPayment ? 0 : 1;
  } else if (mode === "status") {
    const [lang, order, email, tracking, out] = rest;
    const prefix = lang === "uk" ? "/uk" : "";
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, ignoreHTTPSErrors: INSECURE });
    const page = await ctx.newPage();
    // A fresh browser: look the order up by number and email (a POST), as a customer would.
    await page.goto(`${base}${prefix}/order`, T);
    await page.fill("#number", order);
    await page.fill("#email", email);
    await page.click('form[action="/api/order/lookup"] button[type=submit]');
    await page.waitForSelector("[data-tracking]", T);
    const noEmailInUrl = !page.url().includes("@") && !page.url().includes("email=");
    const body = (await page.textContent("main")) || "";
    await page.screenshot({ path: `${out}/status-shipped-${lang}-1440.png` });
    const word = lang === "uk" ? "Відправлено" : "Shipped";
    const ok = body.includes(word) && body.includes(tracking) && noEmailInUrl;
    console.log(JSON.stringify({ lang, shippedWord: body.includes(word), tracking: body.includes(tracking), noEmailInUrl }));
    process.exitCode = ok ? 0 : 1;
    await ctx.close();
  } else {
    throw new Error(`unknown mode ${mode}`);
  }
} finally {
  await browser.close();
}
