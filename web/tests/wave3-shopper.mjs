/**
 * Wave 3 shopper checks in a real browser, with a PASS/FAIL line per check.
 *
 *   NODE_PATH=$(npm root -g) node web/tests/wave3-shopper.mjs <web> <api> <admin-key> <out-dir> [--tax] [--perf]
 *
 * <api> and <admin-key> are used only to prepare data a shopper cannot make: three test
 * photos on the demo table runner and stock for the purchase. Everything checked is done
 * through the storefront in Chromium at 390x844 (and 1440x900 where noted), with
 * screenshots in <out-dir>.
 *
 * --tax   the API runs with SHOP_TAX_MODE=gst_hst_registered: Alberta shows GST 5%, Ontario HST 13%
 * --perf  LCP and CLS on /uk/shop and a product page at 390px with a 4x CPU throttle
 */
import { createRequire } from "node:module";
import { mkdirSync, writeFileSync } from "node:fs";

// ESM ignores NODE_PATH; require() honours it, which is how the global playwright is found.
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const [base, api, adminKey, out] = process.argv.slice(2, 6);
const flags = new Set(process.argv.slice(6));
if (!base || !api || !out) {
  console.error("usage: wave3-shopper.mjs <web> <api> <admin-key> <out-dir> [--tax] [--perf]");
  process.exit(2);
}
mkdirSync(out, { recursive: true });
const T = { timeout: 45000 };
const PHONE = { width: 390, height: 844 };
let fails = 0;
const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${String(detail).slice(0, 300)}` : ""}`);
  if (!ok) fails += 1;
}
const shot = (page, name, full = false) => page.screenshot({ path: `${out}/${name}.png`, fullPage: full });
const adminHeaders = { "x-api-key": adminKey };

async function apiJson(path, init = {}) {
  const res = await fetch(`${api}${path}`, init);
  const text = await res.text();
  try { return { status: res.status, body: JSON.parse(text) }; } catch { return { status: res.status, body: text }; }
}

/** A clearly marked test image: a counted grid and "TEST PHOTO n", never mistaken for a product photo. */
async function testPhoto(page, n, w, h) {
  const b64 = await page.evaluate(({ n, w, h }) => {
    const c = document.createElement("canvas");
    c.width = w; c.height = h;
    const x = c.getContext("2d");
    x.fillStyle = ["#E8E3D6", "#CBC3B0", "#D9D2C1"][n % 3]; x.fillRect(0, 0, w, h);
    x.strokeStyle = "rgba(42,35,32,0.18)"; x.lineWidth = 2;
    for (let i = 0; i < w; i += 40) { x.beginPath(); x.moveTo(i, 0); x.lineTo(i, h); x.stroke(); }
    for (let i = 0; i < h; i += 40) { x.beginPath(); x.moveTo(0, i); x.lineTo(w, i); x.stroke(); }
    x.strokeStyle = n % 2 ? "#A11D2B" : "#2A2320"; x.lineWidth = 10;
    for (let i = 0; i < 12; i++) { const cx = 120 + i * 80, cy = h / 2; x.beginPath(); x.moveTo(cx - 25, cy - 25); x.lineTo(cx + 25, cy + 25); x.moveTo(cx + 25, cy - 25); x.lineTo(cx - 25, cy + 25); x.stroke(); }
    x.fillStyle = "#221E1B"; x.font = "bold 72px sans-serif"; x.fillText(`TEST PHOTO ${n}`, 60, 140);
    return c.toDataURL("image/jpeg", 0.85).split(",")[1];
  }, { n, w, h });
  return new Blob([Buffer.from(b64, "base64")], { type: "image/jpeg" });
}

async function prepare(browser) {
  const page = await browser.newPage();
  await page.goto("about:blank");
  // Three photos on the demo table runner (single variant), unless they are there already.
  const found = await apiJson("/v1/admin/products?q=table-runner-red", { headers: adminHeaders });
  const product = (found.body.items || []).find((p) => p.slug === "table-runner-red");
  if (!product) throw new Error(`table-runner-red not found: ${JSON.stringify(found.body).slice(0, 200)}`);
  const detail = await apiJson(`/v1/admin/products/${product.id}`, { headers: adminHeaders });
  const have = (detail.body.images || detail.body.photos || []).length;
  for (let n = have + 1; n <= 3; n++) {
    const form = new FormData();
    form.append("file", await testPhoto(page, n, 1400, n === 3 ? 1000 : 1750), `test-${n}.jpg`);
    form.append("alt_en", `Test photo ${n} of the demo table runner`);
    form.append("alt_uk", `Тестове фото ${n} демонстраційної доріжки`);
    const up = await apiJson(`/v1/admin/products/${product.id}/images`, { method: "POST", headers: adminHeaders, body: form });
    if (up.status !== 201) throw new Error(`photo upload ${up.status}: ${JSON.stringify(up.body).slice(0, 200)}`);
  }
  // Stock for the purchases and the rate-limit run. A stack seeded without stock (the e2e run)
  // has none for the blouse, so every one of its variants gets some.
  const blouse = (await apiJson("/v1/catalog/products/kosiv-nyzynka-blouse")).body;
  const stock = [["TABLE-RUNNER-RED-01", 40], ...(blouse.variants || []).filter((v) => !v.availability.in_stock).map((v) => [v.sku, 5])];
  for (const [sku, qty] of stock) {
    await apiJson("/v1/admin/stock/receive", { method: "POST", headers: { ...adminHeaders, "content-type": "application/json" }, body: JSON.stringify({ sku, qty, reason: "wave 3 browser check", location_id: "A-LANE-01" }) });
  }
  await page.close();
}

async function labelsFor(slug) {
  const p = (await apiJson(`/v1/catalog/products/${slug}`)).body;
  return p.variants.map((v) => ({ sku: v.sku, en: v.label, uk: v.label_uk }));
}

(async () => {
  const browser = await chromium.launch();
  try {
    await prepare(browser);
    const phone = await browser.newContext({ viewport: PHONE, hasTouch: true, isMobile: true, deviceScaleFactor: 2 });
    const page = await phone.newPage();

    /* ------------------------------------------------------------ search */
    for (const q of ["вишиванка", "vyshyvanka", "blouse", "рушник", "motanka"]) {
      await page.goto(`${base}/shop?q=${encodeURIComponent(q)}`, T);
      const n = await page.locator("a.tile").count();
      check(`search "${q}" returns products`, n >= 1, `${n} tiles`);
    }
    await page.goto(`${base}/uk/shop?q=${encodeURIComponent("кваквзлфж")}`, T);
    const shelf = page.locator("[data-shelf-suggestion]");
    check("nonsense search shows the closest category", (await shelf.count()) === 1 && (await shelf.isVisible()), await shelf.textContent().catch(() => ""));
    await shot(page, "search-nonsense-uk-390");

    /* ------------------------------------------------------------ phone metrics */
    for (const [path, limit] of [["/", 1013], ["/shop", 844], ["/uk/shop", 844]]) {
      await page.goto(`${base}${path}`, { ...T, waitUntil: "networkidle" });
      const m = await page.evaluate(() => {
        const tile = document.querySelector("a.tile:not(.col-tile)");
        const btn = document.querySelector("[data-phone-search]");
        const r = btn?.getBoundingClientRect();
        return {
          top: tile ? tile.getBoundingClientRect().top + window.scrollY : null,
          search: Boolean(btn && r && r.width > 0 && r.top >= 0 && r.bottom <= 120 && getComputedStyle(btn).visibility !== "hidden"),
          overflow: document.documentElement.scrollWidth > window.innerWidth,
        };
      });
      check(`${path}: first product tile top ${Math.round(m.top)} px <= ${limit}`, m.top !== null && m.top <= limit);
      check(`${path}: search control visible in the phone header`, m.search);
      check(`${path}: no sideways scroll at 390`, !m.overflow);
    }
    await page.goto(`${base}/uk/shop`, T);
    await shot(page, "shop-uk-390");
    await page.click("[data-filter-open]");
    await page.waitForSelector('.fdrawer[data-open="true"]', T);
    await page.waitForTimeout(300);
    await shot(page, "shop-uk-390-drawer");
    await page.click('.fdrawer a.chip:has-text("Кераміка")');
    await page.waitForURL(/category=ceramics/, T);
    const chips = await page.locator(".fbar__chips .chip").allTextContents();
    check("filter drawer applies a filter and shows it as an active chip", chips.some((c) => c.includes("Кераміка")), chips.join("|"));
    await shot(page, "shop-uk-390-chips");
    await page.click("[data-phone-search]");
    await page.waitForTimeout(150);
    await shot(page, "header-search-open-390");

    /* ------------------------------------------------------------ gallery */
    await page.goto(`${base}/uk/product/table-runner-red`, { ...T, waitUntil: "networkidle" });
    const mainSrc = () => page.locator("[data-gallery-main] img").first().getAttribute("src");
    const thumbs = await page.locator("[data-gallery-thumb]").count();
    check("product with 3 photos shows 3 thumbnail buttons", thumbs === 3, `${thumbs}`);
    const first = await mainSrc();
    const img = page.locator("[data-gallery-main] img").first();
    const attrs = await img.evaluate((el) => ({ w: el.getAttribute("width"), h: el.getAttribute("height"), srcset: el.getAttribute("srcset"), pr: el.getAttribute("fetchpriority") }));
    check("main photo has width, height, srcset and fetchpriority=high", Boolean(attrs.w && attrs.h && attrs.srcset && attrs.pr === "high"), JSON.stringify(attrs));
    await page.locator('[data-gallery-thumb="1"]').click();
    const afterClick = await mainSrc();
    check("clicking thumbnail 2 changes the main image", afterClick !== first, `${first} -> ${afterClick}`);
    await page.locator('[data-gallery-thumb="2"]').focus();
    await page.keyboard.press("Enter");
    const afterEnter = await mainSrc();
    check("Enter on thumbnail 3 changes the main image", afterEnter !== afterClick, afterEnter);
    await shot(page, "gallery-thumb3-uk-390");
    const beforeSwipe = await mainSrc();
    await page.locator("[data-gallery-main]").evaluate((el) => {
      const r = el.getBoundingClientRect();
      const y = r.top + r.height / 2;
      const touch = (x) => new Touch({ identifier: 1, target: el, clientX: x, clientY: y });
      el.dispatchEvent(new TouchEvent("touchstart", { bubbles: true, cancelable: true, touches: [touch(r.left + 300)], changedTouches: [touch(r.left + 300)] }));
      el.dispatchEvent(new TouchEvent("touchend", { bubbles: true, cancelable: true, touches: [], changedTouches: [touch(r.left + 60)] }));
    });
    await page.waitForTimeout(100);
    const afterSwipe = await mainSrc();
    check("a left swipe on the main photo moves to another photo", afterSwipe !== beforeSwipe, `${beforeSwipe} -> ${afterSwipe}`);
    await page.click("[data-gallery-open]");
    const openFull = await page.locator("dialog[data-lightbox]").evaluate((d) => d.open);
    await shot(page, "gallery-fullscreen-uk-390");
    await page.keyboard.press("Escape");
    await page.waitForTimeout(150);
    const closedFull = await page.locator("dialog[data-lightbox]").evaluate((d) => !d.open);
    check("full-screen view opens and closes with Esc", openFull && closedFull);
    const specSku = await page.locator("[data-spec-sku]").textContent();
    check("SKU is printed in the specification table", /TABLE-RUNNER-RED/.test(specSku || ""), specSku);

    /* ------------------------------------------------------------ UK purchase at 390x844 */
    await page.goto(`${base}/uk/product/kosiv-nyzynka-blouse`, { ...T, waitUntil: "networkidle" });
    await shot(page, "product-uk-390");
    check("sticky bar is down while the buy panel is below the fold", (await page.locator(".pd-bar").count()) === 0);
    await page.evaluate(() => {
      const panel = document.querySelector(".pd-buy");
      window.scrollTo(0, (panel?.getBoundingClientRect().bottom ?? 2000) + window.scrollY + 40);
    });
    await page.waitForSelector(".pd-bar", T);
    check("sticky bar appears once the buy panel has scrolled above the screen", true);
    const barText = await page.locator(".pd-bar").textContent();
    const blouseLabels = await labelsFor("kosiv-nyzynka-blouse");
    const englishInBar = blouseLabels.filter((l) => l.en !== l.uk && barText.includes(l.en));
    check("sticky bar shows no English variant label", englishInBar.length === 0, barText);
    await shot(page, "product-sticky-uk-390");
    await page.locator(".pd-bar button").click();
    await page.waitForSelector("[data-bag-toast]", T);
    const toast = await page.locator("[data-bag-toast]").textContent();
    check("add to bag shows a toast under the header", /Додано до кошика/.test(toast || ""), toast);
    await page.waitForTimeout(400);
    await shot(page, "toast-uk-390");

    await page.goto(`${base}/uk/product/table-runner-red`, { ...T, waitUntil: "networkidle" });
    await page.locator(".pd-buy .btn--red").first().click();
    await page.waitForSelector("[data-bag-toast]", T);
    await page.locator("[data-bag-toast] a[href$='/bag']").click();
    await page.waitForURL(/\/uk\/bag$/, T);
    await page.waitForSelector("[data-bag-label]", T);
    await page.waitForTimeout(500);
    const toastAfterLink = await page.locator("[data-bag-toast]").count();
    await page.waitForTimeout(7000);
    check("the toast closes when its own “view bag” link is tapped and stays closed", toastAfterLink === 0 && (await page.locator("[data-bag-toast]").count()) === 0, String(toastAfterLink));
    await shot(page, "toast-closed-on-bag-uk-390");
    await page.waitForTimeout(400);
    const head = await page.locator("h1").first().textContent();
    check('bag header reads "Кошик · 2 товари"', /Кошик\s*·\s*2 товари/.test(head || ""), head);
    const ukLabels = (await page.locator("[data-bag-label]").allTextContents()).join(" | ");
    const allLabels = [...blouseLabels, ...(await labelsFor("table-runner-red"))];
    const englishInBag = allLabels.filter((l) => l.en && l.en !== l.uk && l.en !== "One size" && ukLabels.includes(l.en));
    check("UK bag shows no English variant labels", englishInBag.length === 0 && !/One size/.test(ukLabels), ukLabels);
    await shot(page, "bag-uk-390");

    await page.goto(`${base}/bag`, { ...T, waitUntil: "networkidle" });
    await page.waitForSelector("[data-bag-label]", T);
    await page.waitForTimeout(400);
    const enHead = await page.locator("h1").first().textContent();
    const enLabels = (await page.locator("[data-bag-label]").allTextContents()).join(" | ");
    check('switching to English re-renders the bag ("Your bag · 2 items", English labels)', /Your bag\s*·\s*2 items/.test(enHead || "") && blouseLabels.some((l) => enLabels.includes(l.en)), `${enHead} :: ${enLabels}`);
    await shot(page, "bag-en-390");
    await page.goto(`${base}/uk/bag`, { ...T, waitUntil: "networkidle" });
    await page.waitForSelector("[data-bag-label]", T);
    await page.waitForTimeout(300);
    const backLabels = (await page.locator("[data-bag-label]").allTextContents()).join(" | ");
    check("switching back to Ukrainian re-renders the labels in Ukrainian", backLabels === ukLabels, backLabels);

    await page.goto(`${base}/uk/checkout`, { ...T, waitUntil: "networkidle" });
    await page.waitForSelector("[data-place-order]", T);
    check("Place order is disabled before the terms are accepted", await page.locator("[data-place-order]").isDisabled());
    const summary = (await page.locator("[data-summary-line]").allTextContents()).join(" | ");
    check("checkout summary shows no English variant labels", !allLabels.some((l) => l.en && l.en !== l.uk && summary.includes(l.en)) && !/One size/.test(summary), summary);
    await page.fill("#email", "buyer.w3@example.test");
    await page.fill("#name", "Олена Тест");
    await page.fill("#street1", "1 Main St");
    await page.fill("#city", "Calgary");
    await page.fill("#postal", "T2P 1J9");
    await page.selectOption("#province", "QC");
    await page.waitForSelector("[data-province-blocked]", T);
    const qcReason = await page.locator("[data-province-blocked]").textContent();
    await page.check("[data-accept-terms]");
    check("Quebec is refused at checkout with the stated reason", /Квебек/.test(qcReason || "") && (await page.locator("[data-place-order]").isDisabled()), qcReason);
    await shot(page, "checkout-qc-uk-390");
    await page.selectOption("#province", "AB");
    await page.waitForTimeout(700);
    if (flags.has("--tax")) {
      const gst = await page.locator('[data-tax-line="GST"]').textContent().catch(() => "");
      check("Alberta shows a 5% GST line", /GST \(5%\)/.test(gst || ""), gst);
      await page.locator('[data-tax-line="GST"]').scrollIntoViewIfNeeded();
      await shot(page, "checkout-tax-ab-uk-390");
      await page.selectOption("#province", "ON");
      await page.waitForTimeout(700);
      const hst = await page.locator('[data-tax-line="HST"]').textContent().catch(() => "");
      check("Ontario shows a 13% HST line", /HST \(13%\)/.test(hst || ""), hst);
      await page.locator('[data-tax-line="HST"]').scrollIntoViewIfNeeded();
      await shot(page, "checkout-tax-on-uk-390");
      await page.selectOption("#province", "AB");
      await page.waitForTimeout(500);
    }
    check("Place order is enabled once the terms are ticked", await page.locator("[data-place-order]").isEnabled());
    await page.fill("#email", "not-an-email");
    await page.click("[data-place-order]");
    await page.waitForSelector('[data-field-error="email"]', T);
    await page.fill("#email", "buyer.w3@example.test");
    check("a field error clears as soon as the field is edited", (await page.locator('[data-field-error="email"]').count()) === 0);
    await shot(page, "checkout-uk-390", true);
    await page.click("[data-place-order]");
    await page.waitForURL(/\/pay\/test\/|\/order\//, T);
    if (/\/pay\/test\//.test(page.url())) {
      await page.click("[data-test-pay]");
      await page.waitForURL(/\/order\//, T);
    }
    await page.waitForSelector("[data-steps]", T);
    const orderUrl = page.url();
    check("order page URL carries no '@' and no 'email='", !orderUrl.includes("@") && !orderUrl.includes("email=") && !orderUrl.includes("%40"), orderUrl);
    const orderNumber = decodeURIComponent(orderUrl.split("/order/")[1].split("?")[0]);
    const orderLabels = (await page.locator("[data-order-label]").allTextContents()).join(" | ");
    check("order page shows Ukrainian variant labels", !allLabels.some((l) => l.en && l.en !== l.uk && orderLabels.includes(l.en)) && !/One size/.test(orderLabels), orderLabels);
    const steps = await page.locator("[data-steps] li").allTextContents();
    check("shipped order shows four steps: Оформлено · Оплачено · Спаковано · Відправлено", steps.length === 4 && /Відправлено/.test(steps[3]), steps.join(" · "));
    await shot(page, "order-uk-390", true);
    await page.setViewportSize({ width: 1440, height: 900 });
    await shot(page, "order-uk-1440");

    /* ------------------------------------------------------------ lookup without the email in a URL */
    const fresh = await browser.newContext({ viewport: PHONE });
    const lp = await fresh.newPage();
    await lp.goto(`${base}/uk/order`, T);
    await lp.fill("#number", orderNumber);
    await lp.fill("#email", "buyer.w3@example.test");
    await lp.click('form[action="/api/order/lookup"] button[type=submit]');
    await lp.waitForSelector("[data-steps]", T);
    check("lookup by number and email opens the order, with no email in the URL", !lp.url().includes("@") && !lp.url().includes("email="), lp.url());
    await lp.goto(`${base}/order`, T);
    await lp.fill("#number", orderNumber);
    await lp.fill("#email", "someone.else@example.test");
    await lp.click('form[action="/api/order/lookup"] button[type=submit]');
    await lp.waitForSelector("#lookup-error", T);
    check("lookup with the wrong email is refused", /No order/.test(await lp.locator("#lookup-error").textContent()));
    await fresh.close();

    /* ------------------------------------------------------------ policy pages */
    for (const path of ["/terms", "/uk/privacy"]) {
      await page.setViewportSize(PHONE);
      await page.goto(`${base}${path}`, T);
      check(`${path} shows the seller block`, (await page.locator("[data-seller-block]").count()) === 1);
      await shot(page, `${path.replace(/\//g, "_")}-390`);
    }
    await page.goto(`${base}/shipping`, T);
    const shippingText = await page.locator("main").textContent();
    check("/shipping still shows the demo strip and the not-published / not-confirmed markers",
      (await page.locator("[data-demo-strip]").count()) === 1 && /not published yet|Not published yet|not confirmed yet/.test(shippingText || ""), "");
    check("/shipping states that Quebec is not shipped to", /Quebec/.test(shippingText || ""));
    await shot(page, "shipping-en-390", true);

    /* ------------------------------------------------------------ icons */
    await page.goto(`${base}/`, T);
    const icons = await page.evaluate(() => [...document.querySelectorAll('link[rel="icon"], link[rel="apple-touch-icon"]')].map((l) => ({ rel: l.rel, href: l.getAttribute("href") })));
    const touch = icons.find((i) => i.rel === "apple-touch-icon");
    const fav = icons.find((i) => i.rel === "icon");
    const status = async (href) => (await fetch(new URL(href, base))).status;
    check("favicon and apple-touch-icon are in the head and return 200", Boolean(fav && touch) && (await status(fav.href)) === 200 && (await status(touch.href)) === 200 && (await status("/favicon.ico")) === 200, JSON.stringify(icons));
    check("/og still renders", (await status("/og?title=UA%20Market")) === 200);

    /* ------------------------------------------------------------ forged X-Forwarded-For */
    const codes = [];
    for (let i = 0; i < 12; i++) {
      const res = await fetch(`${base}/api/order`, {
        method: "POST",
        headers: { "content-type": "application/json", "x-forwarded-for": `198.51.100.${i}`, "x-real-ip": `198.51.100.${i}`, "x-client-ip": `198.51.100.${i}` },
        body: JSON.stringify({
          idempotency_key: `w3-rl-${Date.now()}-${i}`, email: "rate@example.test", name: "Rate Test", locale: "en", fulfillment_method: "SHIP",
          ship_to: { street1: "1 Main St", city: "Ottawa", province: "ON", postal_code: "K1A 0B1" }, lines: [{ sku: "TABLE-RUNNER-RED-01", qty: 1 }], terms_accepted: true,
        }),
      });
      codes.push(res.status);
    }
    const firstBlocked = codes.indexOf(429);
    // Without Caddy and the internal secret every storefront order counts under the web server's
    // own address, so orders placed earlier in the same run may already have used part of the ten.
    check("12 orders with forged forwarding headers through web hit 429 after the limit", firstBlocked >= 0 && firstBlocked <= 10 && codes.slice(firstBlocked).every((c) => c === 429), codes.join(","));

    /* ------------------------------------------------------------ LCP / CLS */
    if (flags.has("--perf")) {
      const perfCtx = await browser.newContext({ viewport: PHONE, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
      for (const path of ["/uk/shop", "/uk/product/table-runner-red"]) {
        const p = await perfCtx.newPage();
        const cdp = await perfCtx.newCDPSession(p);
        await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
        await p.addInitScript(() => {
          window.__lcp = 0; window.__cls = 0;
          new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__lcp = e.startTime; }).observe({ type: "largest-contentful-paint", buffered: true });
          new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({ type: "layout-shift", buffered: true });
        });
        // Warm the server render first so the number measures the page, not a cold cache.
        await fetch(`${base}${path}`);
        await p.goto(`${base}${path}`, { ...T, waitUntil: "load" });
        await p.waitForTimeout(3000);
        const m = await p.evaluate(() => ({ lcp: Math.round(window.__lcp), cls: Number(window.__cls.toFixed(4)) }));
        check(`${path}: LCP ${m.lcp} ms <= 2500 at 390px, 4x CPU`, m.lcp > 0 && m.lcp <= 2500);
        check(`${path}: CLS ${m.cls} <= 0.1`, m.cls <= 0.1);
        await p.close();
      }
      await perfCtx.close();
    }
  } catch (e) {
    check("script ran to the end", false, e.stack || e.message);
  } finally {
    await browser.close();
    writeFileSync(`${out}/wave3-shopper.json`, JSON.stringify(results, null, 2));
    console.log(fails ? `FAILED ${fails}` : `ALL PASS (${results.length})`);
    process.exit(fails ? 1 : 0);
  }
})();
