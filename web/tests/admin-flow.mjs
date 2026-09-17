#!/usr/bin/env node
/**
 * The owner's /admin, driven only through a headless browser. Prints PASS/FAIL per check.
 *
 *   ADMIN_PASSWORD=… [ADMIN_API_KEY=… OPERATOR_API_KEY=…] [ADMIN_LOGIN_LOCK_SECONDS=20] \
 *   NODE_PATH=$(npm root -g) node web/tests/admin-flow.mjs <web base> <out dir> [mailpit base] [template csv]
 *
 * The API keys are passed only so the network log can be searched for them: nothing here
 * sends them anywhere. Needs a shop with the placeholder catalogue seeded, fake card payments,
 * and a sign-in lock short enough to wait out (ADMIN_LOGIN_LOCK_SECONDS).
 */
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const [base, out, mailpit = "http://127.0.0.1:18025", templatePath = new URL("../../docs/catalogue-import-template.csv", import.meta.url).pathname] = process.argv.slice(2);
const PASSWORD = process.env.ADMIN_PASSWORD || "";
const SECRETS = [process.env.ADMIN_API_KEY, process.env.OPERATOR_API_KEY].filter((s) => s && s.length > 8);
const LOCK = Number(process.env.ADMIN_LOGIN_LOCK_SECONDS || "20");
const T = { timeout: 30000 };
const RUN = Date.now().toString(36).slice(-5);
let fails = 0;

function check(name, ok, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${!ok && detail ? ` — ${detail}` : ""}`);
  if (!ok) fails += 1;
  return ok;
}
const shot = (page, name) => page.screenshot({ path: `${out}/${name}.png` });

const browser = await chromium.launch();
const leaks = [];

/** Record every request and response on /admin pages and look for an API key in any of them. */
function watchForKeys(page) {
  page.on("request", (req) => {
    const hay = [req.url(), JSON.stringify(req.headers()), req.postData() || ""].join("\n");
    for (const s of SECRETS) if (hay.includes(s)) leaks.push(`request ${req.url()}`);
  });
  page.on("response", async (res) => {
    try {
      const headers = JSON.stringify(await res.allHeaders());
      const type = res.headers()["content-type"] || "";
      const body = /json|text|javascript|html|x-component/.test(type) ? await res.text() : "";
      for (const s of SECRETS) if (headers.includes(s) || body.includes(s)) leaks.push(`response ${res.url()}`);
    } catch {
      /* redirects and aborted requests have no body */
    }
  });
}

async function jpegFile(page, name, colour, w = 1200, h = 1500) {
  const b64 = await page.evaluate(([c, width, height]) => {
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const g = canvas.getContext("2d");
    g.fillStyle = c;
    g.fillRect(0, 0, width, height);
    g.fillStyle = "#2A2320";
    for (let y = 0; y < height; y += 60) for (let x = (y / 60) % 2 ? 30 : 0; x < width; x += 60) g.fillRect(x, y, 24, 24);
    return canvas.toDataURL("image/jpeg", 0.9).split(",")[1];
  }, [colour, w, h]);
  return { name, mimeType: "image/jpeg", buffer: Buffer.from(b64, "base64") };
}

async function signIn(page) {
  await page.goto(`${base}/admin/login`, T);
  await page.fill("input[type=password]", PASSWORD);
  await Promise.all([page.waitForURL(`${base}/admin`, T), page.click("button[type=submit]")]);
}

try {
  // ---------------------------------------------------------------- sign-in, both widths
  const desk = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await desk.newPage();
  watchForKeys(page);
  await page.goto(`${base}/admin`, T);
  check("1440: /admin without a session redirects to the sign-in page", page.url() === `${base}/admin/login`, page.url());
  const robotsMeta = await page.locator('meta[name="robots"]').getAttribute("content");
  check("/admin/login carries noindex", /noindex/.test(robotsMeta || ""), robotsMeta || "none");
  await shot(page, "admin-login-1440");

  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const mob = await phone.newPage();
  watchForKeys(mob);
  await mob.goto(`${base}/admin/products`, T);
  check("390: /admin/products without a session redirects to sign-in", mob.url() === `${base}/admin/login`, mob.url());
  await shot(mob, "admin-login-390");

  const statuses = [];
  for (let i = 1; i <= 5; i += 1) {
    await page.fill("input[type=password]", `wrong-password-${i}`);
    const [res] = await Promise.all([page.waitForResponse((r) => r.url().endsWith("/admin/api/login"), T), page.click("button[type=submit]")]);
    statuses.push(res.status());
    await page.waitForTimeout(150);
  }
  const lockText = (await page.textContent("#login-error")) || "";
  check("5 wrong passwords: 401×4 then 429 with a lock message", statuses.slice(0, 4).every((s) => s === 401) && statuses[4] === 429 && /lock|заблок/i.test(lockText), `${statuses} ${lockText}`);
  await shot(page, "admin-login-locked-1440");
  await page.fill("input[type=password]", PASSWORD);
  const [lockedRes] = await Promise.all([page.waitForResponse((r) => r.url().endsWith("/admin/api/login"), T), page.click("button[type=submit]")]);
  check("while locked even the right password is refused (429)", lockedRes.status() === 429, String(lockedRes.status()));
  await page.waitForTimeout((LOCK + 1) * 1000);
  await page.fill("input[type=password]", PASSWORD);
  await Promise.all([page.waitForURL(`${base}/admin`, T), page.click("button[type=submit]")]);
  await page.waitForSelector(".adm-tabs", T);
  check("the right password lands on the order queue (1440)", page.url() === `${base}/admin` && (await page.locator(".adm-tabs").count()) === 1);
  const cookies = await desk.cookies();
  const session = cookies.find((c) => c.name === "uam_admin");
  check("session cookie is HttpOnly, SameSite=Strict, path /admin", Boolean(session?.httpOnly && session.sameSite === "Strict" && session.path === "/admin"), JSON.stringify(session && { h: session.httpOnly, s: session.sameSite, p: session.path }));
  await shot(page, "admin-queue-1440");
  await signIn(mob);
  await mob.waitForSelector(".adm-tabs", T);
  check("the right password lands on the order queue (390)", mob.url() === `${base}/admin`);
  await shot(mob, "admin-queue-390");

  const csrfLess = await page.evaluate(async () => (await fetch("/admin/api/v1/admin/makers", { method: "POST", headers: { "content-type": "application/json" }, body: "{}" })).status);
  check("a write without the CSRF token is refused (403)", csrfLess === 403, String(csrfLess));

  const traversal = await page.evaluate(async () => {
    const out = {};
    for (const path of ["v1/admin/%252e%252e/%252e%252e/openapi.json", "v1/admin/%2e%2e/%2e%2e/openapi.json", "v1/admin/..%252f..%252fopenapi.json", "v1/admin/%5c..%5c..%5copenapi.json"]) {
      out[path] = (await fetch(`/admin/api/${path}`)).status;
    }
    return out;
  });
  check("encoded ../ through /admin/api never leaves the allowlist (404)", Object.values(traversal).every((s) => s === 404), JSON.stringify(traversal));

  await page.goto(`${base}/admin/locker`, T);
  const lockerOk = (await page.locator("[data-testid=locker-pickup]").count()) === 1 && (await page.locator("h1").textContent())?.includes("Locker");
  check("locker overview opens from the nav", Boolean(lockerOk));
  await shot(page, "admin-locker-1440");
  await mob.goto(`${base}/admin/locker`, T);
  await shot(mob, "admin-locker-390");
  await page.goto(`${base}/admin`, T);

  // ---------------------------------------------------------------- maker and product
  const makerName = `Flow Workshop ${RUN}`;
  await page.goto(`${base}/admin/makers/new`, T);
  await page.fill('[data-testid=maker-form] input[name=name]', makerName);
  await page.fill('[data-testid=maker-form] input[name=name_uk]', `Майстерня ${RUN}`);
  await page.fill('[data-testid=maker-form] input[name=region]', "Lviv");
  await page.fill('[data-testid=maker-form] input[name=region_uk]', "Львів");
  await Promise.all([page.waitForURL(/\/admin\/makers\/[0-9a-f-]{36}$/, T), page.click("[data-testid=save-maker]")]);
  check("maker created through the form", (await page.textContent("h1"))?.includes(makerName) === true);

  const title = `Flow linen runner ${RUN}`;
  const titleUk = `Лляна доріжка ${RUN}`;
  await page.goto(`${base}/admin/products/new`, T);
  const form = page.locator("[data-testid=product-form]");
  await form.locator("input[name=title]").fill(title);
  await form.locator("input[name=title_uk]").fill(titleUk);
  await form.locator("input[name=subtitle]").fill("Made for a long table");
  await form.locator("input[name=subtitle_uk]").fill("Для довгого столу");
  await form.locator("textarea[name=description]").fill("A linen runner used in the admin flow test.");
  await form.locator("textarea[name=description_uk]").fill("Лляна доріжка з перевірки адмінки.");
  await form.locator("select[name=category]").selectOption("home");
  await form.locator("select[name=collection]").selectOption("home");
  await form.locator("select[name=maker_id]").selectOption({ label: `${makerName}` });
  await Promise.all([page.waitForURL(/\/admin\/products\/[0-9a-f-]{36}$/, T), page.click("[data-testid=save-product]")]);
  const productUrl = page.url();
  const slug = ((await page.textContent(".adm-head .mono")) || "").trim();
  check("product created with EN/UK copy", slug.startsWith("flow-linen-runner"), slug);

  for (const [en, uk, price, weight] of [["40 × 140 cm", "40 × 140 см", "64.00", "300"], ["40 × 200 cm", "40 × 200 см", "84.00", "420"]]) {
    const add = page.locator("[data-testid=add-variant]");
    await add.locator("input[name=option_label]").fill(en);
    await add.locator("input[name=option_label_uk]").fill(uk);
    await add.locator("input[name=price_cad]").fill(price);
    await add.locator("input[name=weight_g]").fill(weight);
    await add.locator("button[type=submit]").click();
    await page.waitForSelector(`[data-testid=variants] tr[data-sku] >> text=${en}`, T);
  }
  const skus = await page.locator("[data-testid=variants] tr[data-sku]").evaluateAll((rows) => rows.map((r) => r.getAttribute("data-sku")));
  check("two variants with UK labels", skus.length === 2 && (await page.locator("[data-testid=variants] td[lang=uk]").allTextContents()).join("|") === "40 × 140 см|40 × 200 см", skus.join(","));

  // refusals first: client-side messages, then the server itself
  const input = page.locator("[data-testid=photo-input]");
  await input.setInputFiles({ name: "huge.jpg", mimeType: "image/jpeg", buffer: Buffer.alloc(30 * 1024 * 1024, 1) });
  await page.waitForSelector("[data-testid=photo-error]", T);
  const tooBig = (await page.locator("[data-testid=photo-error]").allTextContents()).join(" ");
  check("30 MB photo refused in the page with a clear message", /30\.0 MB; the limit is 15 MB/.test(tooBig), tooBig);
  await input.setInputFiles({ name: "logo.svg", mimeType: "image/svg+xml", buffer: Buffer.from("<svg xmlns='http://www.w3.org/2000/svg'/>") });
  await page.waitForTimeout(300);
  const badType = (await page.locator("[data-testid=photo-error]").allTextContents()).join(" ");
  check(".svg refused in the page with a clear message", /not a photo the shop accepts/.test(badType), badType);
  await shot(page, "admin-upload-refused-1440");
  const productId = productUrl.split("/").pop();
  const server = await page.evaluate(async (id) => {
    const csrf = document.querySelector('meta[name="admin-csrf"]').getAttribute("content");
    const send = async (name, type, size, text) => {
      const fd = new FormData();
      fd.append("file", new Blob([text ?? new Uint8Array(size)], { type }), name);
      const r = await fetch(`/admin/api/v1/admin/products/${id}/images`, { method: "POST", headers: { "x-csrf-token": csrf }, body: fd });
      return { status: r.status, body: await r.text() };
    };
    return {
      big: await send("huge.jpg", "image/jpeg", 30 * 1024 * 1024),
      svg: await send("x.svg", "image/svg+xml", 0, "<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"),
      html: await send("x.html", "text/html", 0, "<html><script>alert(1)</script></html>"),
    };
  }, productId);
  check("server refuses a 30 MB upload with 413 and a message", server.big.status === 413 && /limit is 15 MB/.test(server.big.body), `${server.big.status} ${server.big.body.slice(0, 120)}`);
  check("server refuses .svg and .html with 415 and a message", server.svg.status === 415 && server.html.status === 415 && /JPEG, PNG or WebP/.test(server.svg.body), `${server.svg.status} ${server.html.status}`);

  const files = [await jpegFile(page, "runner-1.jpg", "#A11D2B"), await jpegFile(page, "runner-2.jpg", "#D9D2C1"), await jpegFile(page, "runner-3.jpg", "#245A32", 1800, 1200)];
  await input.setInputFiles(files);
  await page.waitForFunction(() => document.querySelectorAll("[data-testid=photo-row]").length === 3, null, T);
  const rows = page.locator("[data-testid=photo-row]");
  for (let i = 0; i < 3; i += 1) {
    const row = rows.nth(i);
    await row.locator("input[name=alt_en]").fill(`Linen runner, photo ${i + 1}`);
    await row.locator("input[name=alt_uk]").fill(`Лляна доріжка, фото ${i + 1}`);
    await row.locator("button[type=submit]").click();
    await page.waitForTimeout(400);
  }
  await page.reload();
  const alts = await page.locator("[data-testid=photo-row] input[name=alt_uk]").evaluateAll((els) => els.map((e) => e.value));
  check("3 photos uploaded with alt text in both languages", alts.length === 3 && alts.every((a) => a.startsWith("Лляна доріжка")), alts.join("|"));
  check("photos keep the order they were uploaded in", alts.join("|") === "Лляна доріжка, фото 1|Лляна доріжка, фото 2|Лляна доріжка, фото 3", alts.join("|"));

  const firstSrc = await page.locator("[data-testid=photo-row] img").first().getAttribute("src");
  const srcset = await page.locator("[data-testid=photo-row] img").first().getAttribute("srcset");
  const media = await page.evaluate(async (src) => { const r = await fetch(src); return { status: r.status, type: r.headers.get("content-type"), cache: r.headers.get("cache-control") }; }, firstSrc);
  check("photos served as image/webp with resized widths", media.status === 200 && media.type === "image/webp" && /480w/.test(srcset || "") && /960w/.test(srcset || ""), `${JSON.stringify(media)} ${srcset}`);

  // stock 2 on the first variant, from the editor
  await page.locator(`[data-testid=variants] tr[data-sku="${skus[0]}"] button:has-text("Edit")`).click();
  await page.fill("[data-testid=receive-qty]", "2");
  await page.locator("[data-testid=receive-qty]").locator("xpath=ancestor::form").locator("button[type=submit]").click();
  await page.waitForFunction((sku) => document.querySelector(`[data-testid=variants] tr[data-sku="${sku}"] [data-testid=variant-stock]`)?.textContent?.trim() === "2 / 2", skus[0], T);
  check("received stock 2", true);
  const barcode = ((await page.locator(`[data-testid=variants] tr[data-sku="${skus[0]}"] td.mono span`).textContent()) || "").trim();

  await page.click("[data-testid=put-on-sale]");
  await page.waitForFunction(() => document.querySelector("[data-testid=product-status]")?.textContent?.includes("On sale"), null, T);
  check("product activated", true);
  await shot(page, "admin-product-editor-1440");
  await page.screenshot({ path: `${out}/admin-product-editor-1440-full.png`, fullPage: true });
  await mob.goto(productUrl, T);
  await mob.waitForSelector("[data-testid=photos]", T);
  await mob.screenshot({ path: `${out}/admin-product-editor-390-full.png`, fullPage: true });

  // ---------------------------------------------------------------- the storefront shows it
  const shopper = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const sp = await shopper.newPage();
  for (const prefix of ["", "/uk"]) {
    await sp.goto(`${base}${prefix}/shop?q=${encodeURIComponent(RUN)}`, T);
    const tile = sp.locator(`a.tile[href$="/product/${slug}"]`);
    const img = await tile.locator("img.tile__photo").getAttribute("src").catch(() => null);
    const demo = await sp.locator("[data-demo-strip]").count();
    check(`${prefix || "/"}shop shows the product with its photo, demo line present`, Boolean(img && img.startsWith("/media/")) && demo === 1, `img=${img} demo=${demo}`);
    await sp.screenshot({ path: `${out}/shop${prefix.replace("/", "-")}-new-product-1440.png` });
  }
  await sp.goto(`${base}/uk/product/${slug}`, T);
  const ukBody = (await sp.textContent("main")) || "";
  check("UK variant label on /uk/product", ukBody.includes("40 × 140 см") && ukBody.includes(titleUk), ukBody.slice(0, 200));
  check("demo strip still on the product page", (await sp.locator("[data-demo-strip]").count()) === 1);
  const edited = await page.evaluate(async ({ id, t }) => {
    const csrf = document.querySelector('meta[name="admin-csrf"]').getAttribute("content");
    const r = await fetch(`/admin/api/v1/admin/products/${id}`, { method: "PATCH", headers: { "x-csrf-token": csrf, "content-type": "application/json" }, body: JSON.stringify({ subtitle_uk: t }) });
    return r.status;
  }, { id: productId, t: `Щойно змінено ${RUN}` });
  await sp.goto(`${base}/uk/product/${slug}`, T);
  const afterEdit = (await sp.textContent("main")) || "";
  check("a product edit shows on the storefront at once (no 30 s cache)", edited === 200 && afterEdit.includes(`Щойно змінено ${RUN}`), `${edited}`);
  await sp.screenshot({ path: `${out}/uk-product-new-1440.png` });

  // ---------------------------------------------------------------- import
  const template = readFileSync(templatePath, "utf-8");
  const templateRows = template.trim().split("\n").length - 1;
  await page.goto(`${base}/admin/import`, T);
  await page.setInputFiles("[data-testid=import-file]", { name: "template.csv", mimeType: "text/csv", buffer: Buffer.from(template) });
  await page.click("[data-testid=import-check]");
  await page.waitForSelector("[data-testid=import-report]", T);
  const dry = (await page.textContent("[data-testid=import-summary]")) || "";
  const dryErrors = await page.getAttribute("[data-testid=import-report]", "data-errors");
  check(`template dry run: ${templateRows} variant creates, 0 errors`, dryErrors === "0" && dry.includes(`Variants: ${templateRows} new`), dry);
  await shot(page, "admin-import-dry-1440");
  await page.click("[data-testid=import-apply]");
  await page.waitForSelector('[data-testid=import-report][data-applied="true"]', T);
  await page.goto(`${base}/admin/products?q=example`, T);
  const afterApply = await page.locator("[data-testid=product-table] tbody tr").count();
  check("apply creates the template products", afterApply === 2, String(afterApply));
  const changed = template.replace(",100.00,", ",123.45,");
  await page.goto(`${base}/admin/import`, T);
  await page.setInputFiles("[data-testid=import-file]", { name: "template.csv", mimeType: "text/csv", buffer: Buffer.from(changed) });
  await page.click("[data-testid=import-check]");
  await page.waitForSelector("[data-testid=import-report]", T);
  await page.click("[data-testid=import-apply]");
  await page.waitForSelector('[data-testid=import-report][data-applied="true"]', T);
  const second = (await page.textContent("[data-testid=import-summary]")) || "";
  await page.goto(`${base}/admin/products?q=example`, T);
  const afterSecond = await page.locator("[data-testid=product-table] tbody tr").count();
  const priceCell = (await page.locator("[data-testid=product-table] tbody").textContent()) || "";
  check("re-apply with a changed price updates, no duplicates", afterSecond === 2 && second.includes("Variants: 0 new") && priceCell.includes("123.45"), `${afterSecond} ${second} ${priceCell.slice(0, 160)}`);
  await shot(page, "admin-products-after-import-1440");

  // ---------------------------------------------------------------- a real storefront order, worked in the admin
  const buyer = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const bp = await buyer.newPage();
  const email = `flow-${RUN}@example.test`;
  await bp.goto(`${base}/product/${slug}`, T);
  await bp.locator(".stack button.btn--red").first().click();
  await bp.waitForFunction(() => (JSON.parse(localStorage.getItem("uamarket.bag.v2") || "[]")[0] || {}).qty >= 1, null, T);
  await bp.goto(`${base}/checkout`, T);
  await bp.waitForSelector("#email", T);
  await bp.fill("#email", email);
  await bp.fill("#name", "Flow Buyer");
  await bp.fill("#street1", "1 Test Street");
  await bp.fill("#city", "Kanata");
  await bp.selectOption("#province", "ON");
  await bp.fill("#postal", "K2K 1X1");
  await bp.check("[data-accept-terms]");
  await bp.locator("form button.btn--red[type=submit]").click();
  await bp.waitForURL(/\/pay\/test\//, T);
  const payText = (await bp.textContent("[data-test-pay-page]")) || "";
  const orderNumber = (payText.match(/UA-\d{6}-[A-Z0-9]{4}/) || [])[0];
  await bp.click("[data-test-pay]");
  await bp.waitForURL(/\/order\/.*paid=1/, T);
  check("storefront order placed and paid with the test card", Boolean(orderNumber), payText.slice(0, 100));

  await page.goto(`${base}/admin?queue=to_pack`, T);
  const row = page.locator(`a.adm-row[data-order="${orderNumber}"]`);
  check("the paid order appears under “To pack”", (await row.count()) === 1);
  await shot(page, "flow-1-queue-to-pack-1440");
  await row.click();
  await page.waitForSelector("[data-testid=scan-input]", T);
  await shot(page, "flow-2-order-scan-1440");
  await page.fill("[data-testid=scan-input]", "0000000000000");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => /not an item waiting/.test(document.querySelector("[data-testid=scan-result]")?.textContent || ""), null, T);
  const focused = await page.evaluate(() => document.activeElement?.getAttribute("data-testid"));
  check("a wrong barcode shows the error and keeps the scanner focused", focused === "scan-input", focused || "");
  await page.waitForSelector('.adm-exc[data-kind="WRONG_SKU"][data-state="OPEN"]', T);
  check("the wrong scan is logged as a problem on the order", true);
  await shot(page, "flow-3-wrong-barcode-1440");
  const shownBarcodes = await page.locator("[data-testid=line-barcode]").allTextContents();
  check("each item on the order page shows its barcode", shownBarcodes.includes(barcode), shownBarcodes.join(","));
  await page.fill("[data-testid=scan-input]", skus[0].toLowerCase());
  await page.keyboard.press("Enter");
  await page.waitForSelector("[data-testid=weight-input]", T);
  check("typing the SKU (no scanner) moves the order to packing", (await page.getAttribute(".adm-order", "data-next")) === "pack");
  const resolved = await page.locator('.adm-exc[data-kind="WRONG_SKU"][data-state="RESOLVED"]').count();
  check("the wrong-scan problem closes itself after the right scan", resolved === 1, String(resolved));
  await shot(page, "flow-4-pack-1440");
  await page.fill("[data-testid=weight-input]", "520");
  await page.locator("[data-testid=weight-input]").locator("xpath=ancestor::form").locator("button[type=submit]").click();
  await page.waitForSelector("[data-testid=tracking-input]", T);
  const carrierPrefill = await page.inputValue("[data-testid=carrier-input]");
  check("the carrier field opens empty after packing (the weight is not carried over)", carrierPrefill === "", JSON.stringify(carrierPrefill));
  await shot(page, "flow-5-ship-1440");
  const orderUrl = page.url();
  await mob.goto(orderUrl, T);
  await mob.waitForSelector("[data-testid=tracking-input]", T);
  await mob.screenshot({ path: `${out}/flow-5-ship-390-full.png`, fullPage: true });
  await shot(mob, "flow-5-ship-390");
  const tracking = `FLOW${RUN.toUpperCase()}CA`;
  await page.fill("[data-testid=carrier-input]", "Canada Post");
  await page.fill("[data-testid=tracking-input]", tracking);
  await page.locator("[data-testid=tracking-input]").locator("xpath=ancestor::form").locator("button[type=submit]").click();
  await page.waitForSelector("[data-testid=shipped-tracking]", T);
  check("mark shipped: the order page shows the tracking", ((await page.textContent("[data-testid=shipped-tracking]")) || "").includes(tracking));
  await page.waitForTimeout(800);
  await page.reload();
  await shot(page, "flow-6-shipped-1440");
  await page.screenshot({ path: `${out}/flow-6-shipped-1440-full.png`, fullPage: true });

  const mail = await browser.newContext();
  const mp = await mail.newPage();
  let subjects = [];
  for (let i = 0; i < 10 && !subjects.some((s) => /shipped/i.test(s)); i += 1) {
    await mp.goto(`${mailpit}/api/v1/messages?limit=200`, T);
    const data = JSON.parse((await mp.textContent("body")) || "{}");
    subjects = (data.messages || []).map((m) => m.Subject).filter((s) => s.includes(orderNumber));
    if (!subjects.some((s) => /shipped/i.test(s))) await mp.waitForTimeout(1000);
  }
  check("Mailpit received the shipped email", subjects.some((s) => /shipped/i.test(s)), subjects.join(" | "));
  // The buyer's browser holds the order's key in a cookie since checkout: no email in the address.
  await bp.goto(`${base}/order/${orderNumber}`, T);
  await bp.waitForSelector("[data-tracking]", T);
  const statusBody = (await bp.textContent("main")) || "";
  check("the customer page shows Shipped and the tracking", statusBody.includes("Shipped") && statusBody.includes(tracking));
  await bp.screenshot({ path: `${out}/flow-7-customer-status-390.png`, fullPage: true });

  // ---------------------------------------------------------------- UK screens and the key audit
  await page.goto(`${base}/admin/api/lang?to=uk&back=/admin`, T);
  await page.waitForSelector(".adm-tabs", T);
  check("admin switches to Ukrainian", ((await page.textContent(".adm-tabs")) || "").includes("Пакувати"));
  await shot(page, "admin-queue-uk-1440");
  await mob.goto(`${base}/admin/api/lang?to=uk&back=${encodeURIComponent(new URL(orderUrl).pathname)}`, T);
  await mob.waitForSelector("[data-testid=next-slab]", T);
  await mob.screenshot({ path: `${out}/admin-order-uk-390-full.png`, fullPage: true });
  await page.goto(`${base}/admin/stock?q=${encodeURIComponent(skus[0])}`, T);
  await shot(page, "admin-stock-uk-1440");
  await page.goto(`${base}/admin/api/lang?to=en&back=/admin`, T);

  const robots = await page.goto(`${base}/robots.txt`, T).then((r) => r.text());
  check("robots.txt disallows /admin", /Disallow: \/admin/.test(robots), robots);
  const sitemap = await page.goto(`${base}/sitemap.xml`, T).then((r) => r.text());
  check("sitemap has no /admin URL", !sitemap.includes("/admin"), sitemap.slice(0, 120));
  check(`no API key in any request or response on /admin pages (${SECRETS.length} keys searched)`, SECRETS.length > 0 && leaks.length === 0, leaks.slice(0, 3).join("; ") || "no keys given");
} catch (err) {
  check("flow ran to the end", false, String(err && err.stack ? err.stack.split("\n").slice(0, 3).join(" ") : err));
} finally {
  await browser.close();
}
console.log(fails ? `${fails} FAILED` : "ALL PASS");
process.exitCode = fails ? 1 : 0;
