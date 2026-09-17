# UA Market: polish plan, 17.09.2026

Base: branch `storefront/kanva`, HEAD `207382d` (09.09.2026), clean tree.
Sources: three audits run on 17.09 (shopper, operator and backend, business readiness), plus
`README.md`, `web/DESIGN.md`, `docs/OWNER-ACTIONS.md`, `docs/GEO.md`, `docker-compose.yml`,
`.github/workflows/ci.yml`.

Goal: every part of launch that needs no owner decision is finished and verified. The owner
should be left with a short list of answers to give and one runbook to follow.

## Rules for every wave

- Work only inside `/data/projects/uamarket`. Before editing, note `git rev-parse HEAD`.
  Make small logical commits whose messages end with
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.
  No force-push and no history rewrite.
- UI work starts by loading the `design-engine` skill. The direction is «КАНВА»
  (`web/DESIGN.md`). The operator screens extend it, and a new section in DESIGN.md
  describes them. There is no new direction and no new ledger row unless a wave says so.
- A green test proves nothing about a page. Every user-facing change gets opened in
  headless Playwright (node playwright with `NODE_PATH=$(npm root -g)`, or `mcp__playwright__*`)
  with a timeout, at 1440x900 and 390x844, EN and UK. Screenshots go to the session
  scratchpad and must be read before calling the work done. Never the owner's Chrome, never
  browser-harness.
- The honesty rules in README.md are law. The demo-catalogue line stays. No invented
  products, prices, delivery times, reviews, stock counts, partners or facts. Copy has no
  "не X, а Y" / "not X but Y" constructions.
- No secrets in code, commits or reports. `uamarket.com` belongs to someone else and must
  not appear anywhere.
- Each wave ends with the project working: `docker compose config -q` passes, `pytest` is
  green, `web` passes typecheck and build, and the wave's browser checks are recorded.

---

## Wave 1: it runs, it is honest, and an order completes end to end in docker

**Goal.** `docker compose up --build` brings up the whole shop from `.env`. A test purchase
goes browse, bag, checkout, fake payment, confirmation email (caught locally), operator
fulfilment through the API, marked shipped with tracking, and customer status. It works with
no locker hardware, and the shop cannot take real money for demo goods. A fast test suite
makes the next two waves possible.

### Tasks

1. **Test speed first.** Tests use in-memory SQLite (`StaticPool`) or, where a file is
   required, `PRAGMA synchronous=OFF` and `journal_mode=MEMORY`. Set
   `LOCKER_PIN_KDF_ITERATIONS` low in `tests/conftest.py`. Where it helps, share a seeded
   template DB. Pin `requirements.txt` with a lock file (`requirements.lock` via pip-tools
   or `pip freeze`).
2. **Compose that starts.** Merge the duplicate `depends_on` in `web`. Give `app` a
   `depends_on: db (service_healthy)` and a `/health` healthcheck, and have `web` wait for
   app healthy. Add `env_file: .env` to `app` and `web`, keeping explicit overrides only
   for internal values (`DATABASE_URL`, `API_URL`). Set `ENV HOSTNAME=0.0.0.0` in
   `web/Dockerfile`. Add a root `.dockerignore` and `web/.dockerignore` (.venv, *.db,
   node_modules, .next, .git). Sync `.env.example` defaults with the code
   (`ORDER_MAIL_MAX_AGE_DAYS`, `EDGE_CREDENTIAL_RECHECK_SECONDS`, `WEB_BASE_URL` port).
   Add `tools/check_env.py`, which compares every `os.getenv` / `process.env` name in
   `app/`, `edge/` and `web/` against `.env.example` and fails on a missing one.
3. **Dev services.** Add a `mailpit` service (dev profile or default in the dev compose),
   and document `SMTP_HOST=mailpit SMTP_PORT=1025 SMTP_SECURITY=none` in `.env.example`
   as the local mail setup.
4. **Prefetch loop and redirects.** Fix `web/proxy.ts` so RSC/prefetch requests for
   English URLs never redirect to themselves. For example, rewrite without touching
   `_rsc`, pass requests carrying `RSC` / `Next-Router-Prefetch` headers straight to the
   rewrite, or move EN to a default-locale segment. Confirm the standalone server returns
   200 when started with `HOSTNAME=0.0.0.0` behind any Host header.
5. **Honesty in the API, not only in web.** Add one `is_routable_email()` helper in
   `app/`, used by `payment_methods()`, `etransfer_email`, `contact_email` and "mailer
   enabled". A `.local/.test/.invalid/example.*` address counts as unset.
   - When the API has no payable method, the storefront hides Place order and shows one
     plain "the shop is not taking orders yet" state. Terms-page wording reads from the
     same config.
   - While `SHOP_CATALOGUE_STATUS` is not `live`, orders are created with a `demo` flag.
     The checkout shows the demo line next to Place order. The order page payment block
     says no money should be sent, and e-Transfer / Stripe instructions are withheld.
   - Add a slim demo strip at the top of every page while placeholder. The existing
     footer-area line stays.
   - Hero, tagline, footer and llms.txt take the origin city from the same setting the
     shipping page uses (`SHOP_BASE_PLACE`). When it is unset they say "Shipped across
     Canada" with no city.
6. **Fake payment provider for local testing.** `PAYMENT_PROVIDER=fake` is refused at
   startup when `WEB_INDEXABLE=true` or `SHOP_CATALOGUE_STATUS=live`. It shows a local
   "Pay (test)" page that posts a signed fake webhook through the same code path as
   Stripe `checkout.session.completed`. Stripe is offered only when both
   `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` are set. The webhook checks
   `amount_total == round(gross*100)` and `currency == cad`. Handle
   `checkout.session.expired` and add a "retry payment" route that creates a new session.
7. **Stock that cannot be sold twice.** A paid order reserves automatically inside
   `mark_paid` and the payment webhook. Placement takes a time-limited hold
   (`ORDER_HOLD_MINUTES`, a software default, released by the sweep). Reservation may split
   a line across sellable locations, using the same location filter as availability.
   Refuse a card session when stock is gone. When a paid order still ends up
   `OUT_OF_STOCK`, raise an operator exception naming the refund.
8. **Quote tells the bag what is wrong.** Type `QuoteIn` with pydantic, reusing
   `WebOrderLineIn` / `WebShipToIn`, so malformed input returns 422 and never 500. Each
   quote line returns `status: ok|reduce|sold_out` and `max_qty`, with no stock count
   exposed. The bag clamps quantity and says "Fewer available; we set it to the most we can
   send". The product-page picker caps the same way. The checkout error names the line.
9. **Ship without the locker.** Add `POST /v1/orders/{id}/ship` (operator), which takes a
   carrier and tracking code. It stores a `ShipmentRecord` with `source=manual`, moves the
   order and package to `HANDOFF_COMPLETE`, and sends the handoff email with tracking. The
   customer order page shows the tracking. The locker path stays and is only used when
   `PICKUP_ADDRESS` is set.
10. **Email preview and content.** Add operator-only
    `GET /v1/orders/{id}/mail/{kind}/preview` (HTML and text). The "placed" email is
    rendered from the order's placement state, so a retry never says "Nothing is owed".
11. **Scheduler.** Add a small `scheduler` service in compose (or an in-app interval task
    behind a setting) that calls the mail and hold-release sweep every 5 minutes.
12. **Schema truth.** Add a migration making `ix_shipments_package_id` unique, with a dedupe
    step first. Import `app.edge_models` in `migrations/env.py`. `create_app()` builds the
    schema only when `ALLOW_INSECURE_DEV` is set. `/health` runs `SELECT 1`. Remove the
    tracked stray `*.db` files from the repo root if they are tracked, and add them to
    `.gitignore`.
13. **CI.** `.github/workflows/ci.yml` exists. Add `alembic check`,
    `docker compose config -q` and `tools/check_env.py`.
14. **End-to-end script.** Add `scripts/e2e_local.sh`, which uses `docker compose up`, the
    seed, receipts, and a Playwright purchase in EN and UK with fake payment. It then runs
    operator mark-paid (or the fake webhook), reserve, scan, pack, weigh, ship with manual
    tracking, checks the Mailpit messages and the customer status page, and prints PASS/FAIL
    per step.

### Acceptance criteria

- `docker compose config -q` exits 0. `docker compose up --build -d` brings db, app, web,
  mailpit and scheduler to healthy/running within 3 minutes on a clean checkout with
  `cp .env.example .env`.
- `pytest -q` passes in under 5 minutes locally (record the time). `alembic upgrade head`
  followed by `alembic check` reports no differences on SQLite and on postgres:16.
  `tools/check_env.py` exits 0.
- Playwright request counter: 10 s idle after load at 1440x900 on `/`, `/faq`, `/uk/faq`,
  `/shop` makes at most 60 requests per page. Committed as `web/tests/smoke-requests.*`
  and run by the e2e script.
- `curl -H 'RSC: 1' -H 'Next-Router-Prefetch: 1' 'http://localhost:3000/faq?_rsc=abc'`
  returns 200 with no `location` header.
- `scripts/e2e_local.sh` prints PASS for every step. Mailpit holds the placed, paid and
  shipped emails for the order. The customer status page (screenshot, EN and UK) shows
  "Shipped" and the tracking code.
- With `ETRANSFER_EMAIL=pay@uamarket.local`, `GET /v1/storefront/config` has no
  `ETRANSFER` in `payment_methods`, and checkout (screenshot) shows the "not taking orders
  yet" state with no Place order button.
- With the placeholder catalogue and fake payment on, the checkout screenshot shows the demo
  line next to Place order at 390 px, the order page tells the buyer not to send money, and
  a demo strip is visible in the first viewport of `/`, `/shop` and a product page.
- With `SHOP_BASE_PLACE` unset, `grep -ri ottawa` on the rendered HTML of `/`, `/uk` and
  `/llms.txt` finds nothing.
- Two orders for a stock-1 SKU: the second cannot reach payment (quote `sold_out` or order
  refused), verified by a pytest and by one Playwright run.
- Bag at qty 20 for a stock-limited item (screenshot) shows the clamp message and quantity
  set to `max_qty`. `POST /v1/storefront/quote` with `{"lines":["x"]}` returns 422.
- A Stripe webhook with a wrong `amount_total` is rejected (pytest).

---

## Wave 2: the owner runs the shop without a programmer

**Goal.** At `/admin` on the storefront, the owner signs in from a laptop or phone. They
can add makers, products, variants, photos, prices and stock, import a sourcing sheet, and
work the order queue from "awaiting payment" to "shipped" with one obvious button per step.
The screens use the КАНВА design and are available in Ukrainian and English.

### Tasks

1. **Design first.** Load `design-engine`. Extend `web/DESIGN.md` with an "Operator"
   section: same tokens, denser tables, big touch targets for the packing bench,
   USB-scanner-friendly input. Draw the order page and product editor before coding.
2. **Auth.** Web `/admin` has a login with `ADMIN_PASSWORD_HASH` (argon2/bcrypt, plus a
   helper script to generate it), a signed HttpOnly SameSite=Strict session cookie
   (`ADMIN_SESSION_SECRET`), CSRF on every POST, and a login rate limit. Server-side
   calls to the API carry `OPERATOR_API_KEY` / `ADMIN_API_KEY`, which never reach the
   browser. `/admin` is `noindex`, disallowed in robots and absent from the sitemap. The
   API also accepts a session for the legacy dashboard, or the dashboard is retired in
   favour of `/admin` with a README note.
3. **Catalogue model additions** (migration and API): `option_label_uk` on variants;
   `alt_en` / `alt_uk` per image; a size chart (JSON per product, optional shop-wide
   default); `fibre_content`, `country_of_origin` and `hs_code` per variant; parcel
   dimensions; `cost_cad`; and `weight_g`, required for activation. Money moves to
   `Numeric(10,2)` / Decimal (migration with a data check). Categories and collections
   become data tables with the current lists as seed.
4. **Admin API:** CRUD for makers, products and variants (EN/UK fields), with auto-generated
   barcodes and retire/unretire. Add image upload to a `media` volume (size and type
   limits, EXIF strip, resized derivatives), served at `/media/...` with cache headers.
   Add a stock receipt by SKU picker and quantity, plus an adjustment with a reason (ledger
   entries only). Activation validation: once `SHOP_CATALOGUE_STATUS=live`, a product
   cannot go active without price, weight, at least one photo with alt text, stock and,
   for garments, a size chart.
5. **CSV import** with a documented template (`docs/catalogue-import-template.csv`). It
   runs a dry-run report first (rows created, updated, errors per row), then applies. The
   importer updates existing rows by slug/SKU. The seed stays insert-only and demo-only.
6. **Admin screens:** makers list and editor; product list (search, active/retired filter)
   and editor with variants table, photo drop zone with reorder, alt text and a live preview
   link; stock screen by product with coarse availability as the shopper sees it plus the
   operator's real quantities; import screen.
7. **Order queue and order page:** tabs for awaiting payment, to pack, ready to ship, shipped
   and exceptions. The order page shows customer, ship-to, items with photos, payment
   method, note and timeline. The next action is one button: mark e-Transfer received;
   reserve; scan (autofocus input that accepts a USB scanner, with a wrong barcode shown in
   red and logged as an exception); pack and weight; enter tracking or buy an EasyPost label
   when configured; mark shipped (wave 1 endpoint); cancel/refund note; resolve exception
   with a note. There is an email preview link per message.
8. **Dashboard numbers:** money with 2 decimals. Gross counts only orders PAID or later.
   Inventory shows product names.
9. **Tests:** API tests for CRUD, upload limits, import dry-run and apply, and activation
   validation. Playwright admin flow script `web/tests/admin-flow.*`.

### Acceptance criteria

- Playwright, 1440x900 and 390x844, `/admin` without a session redirects to login. A wrong
  password 5 times triggers the rate limit (429 or lock message). The correct password lands
  on the queue. Screenshots are read.
- Scripted in Playwright with no curl: create a maker, create a product with EN/UK copy, two
  variants with UK labels, upload 3 photos with alt text, receive stock 2, activate. The
  product then appears on `/shop` and `/uk/shop` with the photo, the UK variant label shows
  on `/uk/product/...`, and the demo line is still present.
- Import of the template CSV: the dry run shows N creates / 0 errors. Apply, and the
  products appear. A second apply with a changed price updates the price and creates no
  duplicates.
- Full order through the admin UI only: a storefront order (fake payment) appears under "to
  pack". Reserve, scan the correct barcode (a wrong one first shows the error), pack with
  weight, enter tracking, mark shipped. Mailpit receives the shipped email, and the customer
  page shows the tracking. Screenshots of each step.
- Upload of a 30 MB file or a `.svg`/`.html` is refused with a clear message. Images are
  served with `Content-Type` image/* and resized variants exist.
- `curl http://localhost:3000/robots.txt` disallows `/admin`, and `/sitemap.xml` has no
  `/admin` URL. The browser network log on `/admin` pages shows no API key in any request
  or response.
- `alembic check` is clean after the new migrations. The pytest suite stays under 6 minutes.

---

## Wave 3: storefront people want to buy from, legal basics, production deploy, owner list

**Goal.** The storefront feels finished on a phone and in Ukrainian. Taxes and the basic
Canadian consumer rules are handled in software. A production compose with TLS, backups and
correct client IPs is ready. `docs/LAUNCH-RUNBOOK.md` is one page, and
`docs/OWNER-ACTIONS.md` is the true short list.

### Tasks

1. **Design pass** (`design-engine`, КАНВА, minimum two screenshot iterations per changed
   page).
2. **UK localisation:** the bag stores SKU and slug only, and resolves label, maker and title
   at render time for the current language (`option_label_uk` from wave 2). Order lines and
   emails carry the UK label. The bag header uses `plural()` ("2 товари") and is renamed
   "Your bag · N items" / "Кошик · N товари" in place of "Cut list / Розкрій".
3. **Search:** a synonym and transliteration table for EN/UK (вишиванка/вишиванки/vyshyvanka/
   vyshyvanky/embroidered shirt/blouse/сорочка; рушник/rushnyk/towel; мотанка/motanka/doll;
   кераміка/ceramics/Опішня/Opishnia, and more). Match on category and collection names too,
   with case-, accent- and plural-insensitive prefix matching. An empty result offers the
   closest category.
4. **Phone layout:** on home, "The shop's pick" comes before collections, collections become
   a compact row or 2-column small tiles, and the hero motif is smaller. On `/shop`, filters
   collapse into a "Filter · Sort" drawer with active chips shown. Add a search icon in the
   phone header.
5. **Product page:** thumbnails are buttons that swap the main image (keyboard accessible),
   with swipe on phone and a full-screen view. Images get width/height, priority for the
   first, and `srcset/sizes` from the wave 2 derivatives. The SKU moves into the
   specification table. The sticky bar appears only after the panel has scrolled above the
   viewport. Add-to-bag shows a short toast or drawer near the header.
6. **Checkout and order page:** field errors clear on input. Add terms and privacy links
   with explicit acceptance next to Place order. SHIP orders use Placed · Paid · Packed ·
   Shipped steps, and the locker steps stay for PICKUP. Steps stack vertically below
   420 px. The email leaves the URL: lookup is a POST and the order page uses a short-lived
   signed HttpOnly cookie or an opaque per-order token.
7. **API down:** catalogue loaders tell a fetch failure apart from an empty result, and
   return a 503 page, "The shop is catching up, try again in a minute", in both languages.
8. **Copy for buyers:** rewrite policy text that talks about software ("software default",
   "configuration") into one per-page line: "We'll confirm this before the shop opens.
   Questions: <contact>". Replace "goes to the frame / іде на п'яльця" with plain "then we
   pack it / потім ми його пакуємо". The honesty rule stays intact: unconfirmed values are
   still marked.
9. **Tax:** a Canada-wide preset table (GST, HST, QST, PST components as named lines)
   selected by `SHOP_TAX_MODE=unregistered|gst_hst_registered|custom`, where custom keeps
   `TAX_RATES_JSON`. `SHOP_GST_NUMBER` is printed on the order page and emails when set.
   Rates are cited in code comments with a source link and are marked as needing
   accountant confirmation in OWNER-ACTIONS.
10. **Legal basics in software:** `SHOP_SHIP_EXCLUDE_PROVINCES`, default `QC` until French
    exists, stated on the shipping page and enforced at checkout and quote. Add a business
    identity block (legal name, address, contact, privacy contact) on terms, privacy and
    contact pages from settings, which says "not published yet" when empty. The privacy
    page's processor list is generated from what is configured (SMTP host, Stripe,
    EasyPost, hosting). The confirmation email carries a link to the terms version in force.
    Wording about the business model is limited to "shop" until the owner chooses a
    marketplace model.
11. **Brand assets and SEO basics:** favicon, apple-touch-icon and a 512 px logo generated
    from the existing cross-stitch wordmark. A proposed SEO title and description with
    search words, behind a setting, off by default and listed for owner approval. Fix the
    `docs/GEO.md` placeholder paragraph to match `web/lib/geo.ts`.
12. **Order email layout:** a simple КАНВА-styled HTML template (linen ground, mono prices,
    no images required) in EN/UK, checked in Mailpit.
13. **Production deploy config:** `docker-compose.prod.yml` with restart policies and no
    public port on app or db. Caddy reverse proxy with automatic TLS for `SHOP_DOMAIN`
    routes `/` to web and only `/webhooks/stripe` to app. The Postgres password comes from
    env. Nightly `pg_dump` to a backup volume with 14-day rotation, plus a restore
    command. The scheduler service is included.
14. **Client IP and rate limits:** web forwards the IP from Caddy's `X-Real-IP` with an
    internal shared header (`INTERNAL_PROXY_SECRET`) that the API requires before trusting
    it. Uvicorn gets explicit `--forwarded-allow-ips`. The order page passes the IP.
    Validation failures count in their own bucket. Remove `TRUSTED_PROXY_IPS` from the owner
    list.
15. **Docs:** `docs/LAUNCH-RUNBOOK.md` is one page: env checklist and secrets generation,
    DNS, prod compose up, migrations, admin password hash, import catalogue, switch
    `SHOP_CATALOGUE_STATUS=live` and `WEB_INDEXABLE=true` deliberately, one real test order
    and refund, backups check, rollback. Rewrite `docs/OWNER-ACTIONS.md` as a one-page
    "Before opening" list of real decisions, each with the setting it fills and what happens
    while it is empty. Move confirmed defaults into an appendix table (setting, default,
    where printed). Move locker-only items to `docs/locker-owner-actions.md`. Resolve the
    listed contradictions (sitemap, carrier, retention, dispatch setting, mail max age, edge
    recheck default). Update README run instructions for the new services and `/admin`.

### Acceptance criteria

- `/uk` purchase flow at 390x844 (screenshots of product, sticky bar, bag, checkout, order)
  shows no English variant labels. The bag header reads "2 товари" for two items. Switching
  language with a full bag re-renders labels in the new language.
- Search: `вишиванка`, `vyshyvanka`, `blouse`, `рушник`, `motanka` each return at least one
  product on the demo catalogue (Playwright assertions). A nonsense query shows a category
  suggestion.
- Phone metrics (Playwright `getBoundingClientRect`): first product tile top at most 1.2
  screens (≤1013 px) on `/` and within the first screen (≤844 px) on `/shop` and `/uk/shop`.
  A search control is visible in the phone header.
- Product with 3 photos: clicking or pressing Enter on thumbnail 2 changes the main image
  src, swipe works in Playwright touch emulation, full-screen opens and closes with Esc.
  Lighthouse (or a Playwright PerformanceObserver) LCP ≤ 2.5 s on `/uk/shop` and a product
  page at 390 px with a 4x CPU throttle. CLS ≤ 0.1.
- The order page URL after checkout contains no `@` and no `email=`. Lookup by number and
  email still works.
- With the API stopped, `/uk/shop` returns HTTP 503 and the "catching up" message
  (screenshot), and a product page shows the same.
- An Alberta address in `gst_hst_registered` mode shows a 5% GST line, Ontario shows 13% HST
  and Quebec is refused at checkout with the stated reason (pytest plus screenshot).
- `grep -rn "software default\|configuration" web/lib/i18n*.ts` finds no shopper-facing
  string. The demo line and "not published yet" markers are still rendered (screenshot of
  `/shipping`).
- Checkout Place order stays disabled until terms are accepted (Playwright). Terms and
  privacy show the business block.
- `docker compose -f docker-compose.yml -f docker-compose.prod.yml config -q` passes. A
  local prod-mode run behind Caddy with an internal CA serves the shop over https. The app
  port is unreachable from the host. Backup produces a dump file, and restore into a scratch
  database succeeds.
- Rate limit: 12 orders with forged `X-Forwarded-For` through web get 429 after the limit.
  Two real distinct client IPs through Caddy are counted separately (pytest or script).
- `docs/OWNER-ACTIONS.md` is at most about 120 lines, has no contradictions from the audit
  list and contains only decisions. `docs/LAUNCH-RUNBOOK.md` fits one printed page. A fresh
  agent following the runbook on a clean checkout reaches a placed test order.
- Favicon and apple-touch-icon return 200 and appear in the head. `/og` still renders.

---

## Deferred (not in these waves)

Owner decisions, which go into the rewritten OWNER-ACTIONS:
- Two real monitored mailboxes (contact and e-Transfer) and the SMTP provider.
- The domain (`uamarket.com` is taken) and `WEB_BASE_URL`.
- Registered legal name, business address, privacy contact, GST/HST registration status
  and BN (with the accountant).
- Payment method: a Stripe account and keys, or an e-Transfer address.
- The real catalogue: makers, products, photos, prices, stock, per-size measurements
  (sizing source).
- Return policy values, postage prices and the free-shipping threshold, carrier name,
  dispatch times.
- Whether Quebec is served, and whether French translation is funded.
- Business model toward makers: buy-and-resell, consignment or commission marketplace.
- Lawyer review of the terms and privacy pages.
- Locker address and hours (optional at launch), social accounts, approval of the proposed
  SEO title and logo.
- Which extra emails customers get (cancellation, stock-out delay, refund) and who answers
  replies.

Out of scope for this workflow:
- A French (fr-CA) storefront.
- Maker onboarding, maker portal, commission/payout accounting.
- Real deployment to a host, DNS and live Stripe/EasyPost switch-on, which wait on the
  domain and accounts.
- S3-compatible photo storage (local volume only now), Google Merchant feed, US or
  international shipping, customs documents.
- Locker hardware installation and the edge daemon on real Modbus devices.
- Shopify channel work.
- Reviews, ratings or stock counts, which the honesty rules forbid.
