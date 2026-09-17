# UA Market polish report, 17.09.2026

Plan: `docs/POLISH-PLAN-2026-09-17.md`. Branch `storefront/kanva`, from `64cc7c7` to `83c0ac2`
(20 commits, 171 files, about +13.2k / -1.5k lines), pushed to origin.

## Deploy: not deployed. Runbook plus local docker verification

The shop is **not** online anywhere. No private staging preview was made, no live payment keys, no
real domain and no real email sending were connected. The project has no domain of its own
(`uamarket.com` belongs to someone else), and a preview would have meant leaving a stack running on
the workstation behind a tunnel nobody asked for. Deployment is written down in
`docs/LAUNCH-RUNBOOK.md` (one page) and `docker-compose.prod.yml` is rehearsed locally with
`scripts/prod_local_check.sh`.

Final check on HEAD `83c0ac2`, 17.09:

- `scripts/e2e_local.sh` on a fresh docker compose stack (PostgreSQL, Mailpit, scheduler): **ALL PASS**,
  stack healthy in 20 s, full run 3 min 35 s.
- Headless Chromium against that stack at 1440x900 and 390x844: `/`, `/uk/shop`, a product page and
  `/admin` returned 200, no console errors, no 4xx/5xx, no sideways scroll, `noindex` on every page,
  demo strip present on every storefront page. Screenshots read (home, UK shop at 390, product at 390,
  admin sign-in). The stack was then stopped with its volumes removed.

## What changed

### Wave 1: it runs, it is honest, an order completes in docker
- Tests from about 20 min to under 1 min (SQLite syncing and PIN hashing cost under pytest); `requirements.lock`.
- Compose starts cleanly from `.env.example`: healthchecks, Mailpit, a scheduler, `tools/check_env.py`, CI gates
  (alembic check on SQLite and PostgreSQL, compose config, env check).
- Honest checkout: no payable method means "not taking orders yet" and no Place order button; placeholder-catalogue
  orders are marked demo and say not to send money; a slim demo strip on every page.
- `PAYMENT_PROVIDER=fake` test payments through the Stripe webhook path (refused in live or indexable mode); amount
  and currency checked; expired sessions release stock; retry payment.
- No overselling: placement holds, reservation on payment, split reservations, sold-out lines named at checkout.
- Manual shipping with carrier and tracking, shown on the customer page; email previews for the operator.
- The prefetch storm on `/uk` pages (up to 1814 requests idle) is gone; no city named unless `SHOP_BASE_PLACE` is set.

### Wave 2: the owner runs the shop at /admin
- Password sign-in (scrypt hash helper), signed cookie, CSRF, login lock; API keys never reach the browser.
- Makers, products, variants with UK labels, photos (limits, EXIF strip, WebP sizes), stock receipts and
  adjustments as ledger entries, activation rules, CSV import with dry run.
- Order queue with one next step per order: e-Transfer received, reserve, scan, pack, ship, cancel, problems.
- Money stored as NUMERIC(10,2); dashboard counts only paid orders.

### Wave 3: storefront, legal basics, production
- Ukrainian bag, order lines and emails; `Кошик · 2 товари`.
- Two-language search with transliteration and synonyms (вишиванка / vyshyvanka / blouse).
- Phone layout, filter drawer, gallery with swipe and full screen, add-to-bag message, fast pages (LCP well under 2.5 s locally).
- Checkout: field errors, explicit terms acceptance, no email address in URLs, 503 "catching up" page when the API is down.
- Canadian tax modes with named GST/HST/QST/PST lines; Quebec excluded by default with the reason stated;
  seller block on terms and privacy; КАНВА HTML order email in EN and UK.
- `docker-compose.prod.yml`: Caddy with TLS, no public app/db/web ports, restarts, nightly backups with restore, correct client IPs.
- `docs/OWNER-ACTIONS.md` rewritten as 23 decisions (82 lines); `docs/LAUNCH-RUNBOOK.md` one page; locker items in `docs/locker-owner-actions.md`.

### Fixes after the independent audit
- The add-to-bag message no longer covers the checkout.
- The ship form no longer pre-fills the carrier with the packed weight.
- Packing without a scanner: the order page shows barcodes, scan accepts the SKU, and a line can be confirmed by hand (noted in history).

## Checks
- pytest: 226 passed, 1 skipped (53–94 s depending on machine load).
- alembic upgrade/check/downgrade/upgrade clean on SQLite and postgres:16; PostgreSQL race test passes.
- `tsc --noEmit`, `next build` pass; `web/tests/smoke-requests.mjs` 0 idle requests.
- `scripts/e2e_local.sh`: ALL PASS (includes admin flow 43 checks, shopper wave 3 49 checks).
- `scripts/prod_local_check.sh --down`: ALL PASS (wave 3 run).
- A fresh clone set up by a separate audit agent from `.env.example` reached a paid, packed and shipped order in EN and UK.

## Not done, and why
- **Real deploy**: blocked on the owner's domain, mailboxes, payment accounts. Only localhost Caddy with its internal CA was tested.
- **Open review findings (minor, not fixed in this run)**:
  1. Uploaded photos all get position 0, so the order of photos is not kept.
  2. A signed-in admin session can get around the `/admin/api` path allowlist with a double-encoded `..`. Only the owner can sign in, but this should be closed before opening.
  3. The login lock is shared by all visitors, so anyone can lock the owner out for the lock period.
  4. The storefront shows an edited product up to 30 s late (page cache).
  5. The test-payment return breaks when `WEB_BASE_URL` has a different host from the one being browsed.
  6. Unused imports left in a few files.
  7. On a phone, a product with no photo pushes the title and price below the first screen.
- EasyPost label buying is written but never run (no key); locker pickup has no admin screen; cancelling sends the buyer no email.
- The admin order history is in English on the UK admin page; a hand check is recorded as "admin" (single owner login).
- Tax rates were written from knowledge of CRA pages and need the accountant's confirmation.
- Speed was measured locally without network latency, not with Lighthouse.
- The plain dev compose counts all order rate limits under one address; only the production compose counts per visitor.

## Decisions only the owner can make
Full list with settings and what happens while empty: `docs/OWNER-ACTIONS.md`. The blocking ones:
domain; contact mailbox; email provider; payment method (Stripe and/or e-Transfer); registered seller
name and address; GST/HST registration with the accountant; the real catalogue; the business model
toward makers. Then policy values (returns, postage, carrier, dispatch days, Quebec, retention,
lawyer review, hosting provider) and search/brand approvals.

## 17.09 — рішення виконано

Власник 17.09: "вирішуй сам, швидше". Рішення записані в `docs/DECISIONS-2026-09-17.md`.

- **Публічне демо:** https://market.agintent.com. Смуга демо-каталогу, оплата тільки тестова (`PAYMENT_PROVIDER=fake`), `noindex` у заголовку і мета, robots `Disallow: /`, API і Mailpit ззовні дають 404.
- **Хостинг:** docker-2 замалий (48 МБ вільної пам'яті, 1,9 ГБ диска), тому стек на воркстейшні за іменованим тунелем Cloudflare `uamarket-demo`. Оновлення: `scripts/demo_deploy.sh`; опис: `docs/DEMO-DEPLOY.md`.
- **Бекапи:** щоночі 07:00 UTC, 14 днів; перший бекап відновлено в `restore_check` (orders=1, products=21).
- **Виправлено:** порядок фото; обхід шляху в admin-проксі; блокування входу (тепер по адресі, акаунт тільки сповільнюється); зміни товару видно одразу; лист про скасування EN/UK; екран шафи `/admin/locker`; історія замовлення українською; сторінки більше не згадують Stripe і "напишіть нам", адмінка показує листи як "перехоплено (демо, не доставлено)".
- **Податки:** ставки звірені з CRA, BC, MB, SK і Revenu Québec; усі збіглися, джерела в DECISIONS.
- **Перевірки:** pytest 230 passed, 1 skipped; tsc і next build чисті; e2e ALL PASS; живий smoke (17 перевірок) ALL PASS; обхід 60 публічних сторінок без помилок; скриншоти 1440 і 390 переглянуті.
- **Тестові дані:** QA-товар `qa-order-test-cushion-f9ir` знято з продажу; тестові замовлення UA-260917-… лишаються в адмінці як приклади демо.
- **Відкрите (дрібне):** прогрес-бар замовлення підсвічує наступний крок червоним; тексти проблем у UK-адмінці англійською; паралельні спроби входу обходять лічильник; лист "скасовано" піде старим скасуванням при запуску на тих самих даних; бекапи лежать на тій самій машині; вузьке поле сканування на телефоні; дубль "On sale" у картці товару.
- **Шлях до справжнього магазину:** `docs/LAUNCH-RUNBOOK.md`, розділ "From the public demo to a real shop".
