# UA Market

One repository, two halves of the same shop.

| part | what it is | stack |
|---|---|---|
| `web/` | **Storefront** — the shop people buy from: catalogue, collections, product pages, makers, bag, checkout, order status, policy pages. English at `/`, Ukrainian at `/uk`. Design system «КАНВА» is written down in `web/DESIGN.md`. | Next.js 16, TypeScript, self-hosted Fixel + Fira Mono |
| `app/`, `edge/` | **Fulfillment core** — WMS/OMS with an append-only inventory ledger, anti-oversell reservations, barcode picking, packing, EasyPost labels, order email, and the courier locker in the garage driven over Modbus by an edge daemon with an exactly-once journal. It also serves the public catalogue and order API the storefront reads. | FastAPI, SQLAlchemy, Alembic, SQLite → PostgreSQL |

## PayPal + AI (PayPal AI Hackathon, October–November 2026)

- **PayPal checkout**: PayPal JS SDK v6 button on checkout, order page and in the concierge; Orders v2 on the server (priced from the database, capture checked to the cent, verified webhooks, tracking sent to PayPal after shipping, refunds for cancelled orders). `app/services/paypal.py`, `web/components/PayPalButton.tsx`.
- **Shopping concierge**: an AI agent on every storefront page that searches the real catalogue, keeps to the buyer's spending limit and prepares a PayPal checkout card. The buyer ticks the terms and approves in PayPal; the agent cannot place or pay an order. `app/services/concierge.py`, `web/components/Concierge.tsx`.
- **PayPal desk** in `/admin`: an agent over the **PayPal Agent Toolkit** that compares the shop with PayPal and proposes refunds and tracking pushes the owner confirms. `app/services/desk.py`, `web/components/admin/PayPalDesk.tsx`.

How it works, the guard rails, how to run it with your own sandbox app, and what changed during the hackathon: **`docs/PAYPAL-AI.md`**. Hosted demo (sandbox, demonstration catalogue): https://uamarket-paypal.agintent.com

Before touching anything customer-facing, read **`docs/OWNER-ACTIONS.md`**: the decisions only the owner can make before opening, each with the setting it fills and what the shop does while it is empty, plus the defaults the software runs on. Deploying: **`docs/LAUNCH-RUNBOOK.md`** (one page). Locker decisions: `docs/locker-owner-actions.md`.

## Run everything

```bash
cp .env.example .env      # fill in what exists; an empty value switches a feature off honestly
docker compose up --build
```

- Storefront: http://localhost:3000
- Owner admin: http://localhost:3000/admin — orders, products, makers, photos, stock, import (see below)
- API reference: http://localhost:8000/docs
- Mailpit, every email the shop sends locally: http://localhost:8025
- The `scheduler` service sends due order email and releases expired stock holds every five minutes.
- Edge daemon with a simulated locker: `docker compose --profile edge up`
- Host ports are `APP_HOST_PORT`, `WEB_HOST_PORT` and `MAILPIT_UI_PORT` in `.env`.

Alembic runs before Uvicorn. Load the demo catalogue once: `curl -X POST -H "x-api-key: $ADMIN_API_KEY" http://localhost:8000/admin/seed-catalog`.

With `.env.example` as it is, no payment method is configured, so the checkout says the shop is not taking orders yet. For a local test purchase set `PAYMENT_PROVIDER=fake`: the card option opens a test payment page that marks the order paid through the same webhook code Stripe uses. The API refuses to start with it while `WEB_INDEXABLE=true` or `SHOP_CATALOGUE_STATUS=live`.

The whole purchase path, checked in a browser with a PASS/FAIL line per step (compose up, seed, receipts, EN and UK purchase with the test payment, reserve, scan, pack, weigh, ship with tracking, Mailpit, status page looked up by number and email, a second buyer for the last unit, idle request counter, the owner admin flow, and the wave 3 shopper checks):

```bash
scripts/e2e_local.sh          # own compose project and ports 13000/18000/18025; add --down to stop it after
```

The shopper checks on their own, against any running stack (search in both languages, phone layout metrics, the photo gallery, a Ukrainian purchase at 390 px, the order URL, seller block, icons, forged `X-Forwarded-For`; `--tax` with `SHOP_TAX_MODE=gst_hst_registered`, `--perf` for LCP and CLS with a 4x CPU throttle):

```bash
NODE_PATH=$(npm root -g) node web/tests/wave3-shopper.mjs http://localhost:3000 http://localhost:8000 "$ADMIN_API_KEY" ./e2e-artifacts [--tax] [--perf]
```

### Production

`docker-compose.prod.yml` goes on top of `docker-compose.yml`: Caddy with automatic TLS for `SHOP_DOMAIN` is the only published service and sends `/webhooks/stripe` to the API and everything else to the storefront; app, db and web have no host port; every service restarts; `POSTGRES_PASSWORD` and `INTERNAL_PROXY_SECRET` are required; a `backup` service dumps the database and the photo volume nightly and keeps 14 days (`scripts/backup/restore.sh` restores into a scratch database). The visitor's address reaches the API's rate limits as Caddy's `X-Real-IP`, passed on by the storefront with the internal secret; a forwarded header a visitor writes is ignored. Steps: `docs/LAUNCH-RUNBOOK.md`. A full rehearsal on a laptop, with Caddy's internal CA, forged and real client addresses, a browser purchase over https, backup and restore:

```bash
scripts/prod_local_check.sh --down
```

### The owner's admin (`/admin`)

```bash
python3 tools/admin_password_hash.py      # prints ADMIN_PASSWORD_HASH=… and ADMIN_SESSION_SECRET=… for .env
```

With those two and `ADMIN_API_KEY` set, `/admin` on the storefront asks for the password (5 wrong tries lock sign-in from that address for `ADMIN_LOGIN_LOCK_SECONDS`, default 15 min; wrong passwords from all addresses together only slow each check, up to 4 s, so nobody can lock the owner out). It works on a laptop and a phone, in English and Ukrainian:

- **Orders**: tabs for awaiting payment, to pack, ready to ship, shipped, problems, cancelled. The order page names the one next step and gives one button for it: mark e-Transfer received, reserve, scan items (a USB barcode scanner types into the focused field; without a scanner, type the barcode or SKU shown on each item, or confirm an item by hand, which the timeline records; a wrong code is refused and logged), pack with the weight, enter carrier and tracking (or buy an EasyPost label when `EASYPOST_API_KEY` and `SHIP_FROM_ADDRESS_JSON` are set), then shipped. Cancel needs a reason; a paid order opens a refund reminder. Email previews, notes and a timeline are on the same page.
- **Products and makers**: EN/UK copy, variants with UK labels (SKU and an in-store EAN-13 barcode fill themselves), retire and bring back, photos by drag and drop (JPEG, PNG or WebP up to `MEDIA_MAX_UPLOAD_MB`, EXIF removed, WebP copies at 480/960/1600 px served at `/media/…`), alt text in both languages, a size chart per product or a shop default. **Put on sale** refuses with a list of what is missing: price and weight always; once `SHOP_CATALOGUE_STATUS=live` also the Ukrainian copy, a photo with alt text, stock and a size chart for garments.
- **Stock**: receive and adjust with a reason; every change is a ledger entry, and the screen shows what the shopper sees beside the real counts.
- **Import**: a CSV sourcing sheet (template: `docs/catalogue-import-template.csv`, columns: `docs/catalogue-import.md`), checked first, applied whole or not at all, matched by product slug and SKU so a second import updates instead of duplicating.

The API key never reaches the browser: the screens call `/admin/api/…` on the Next.js server, which checks the session and the CSRF token and adds the key. The old header-key HTML dashboard at the API root is retired (the route now answers where to go); `GET /v1/dashboard` and `GET /v1/inventory` stay for scripts. The browser check for all of it:

```bash
ADMIN_PASSWORD=… ADMIN_API_KEY=… ADMIN_LOGIN_LOCK_SECONDS=20 NODE_PATH=$(npm root -g) \
  node web/tests/admin-flow.mjs http://localhost:3000 ./e2e-artifacts http://localhost:8025
```

Operator shipping without the locker: `POST /v1/orders/{id}/ship` with `{"carrier": "...", "tracking_code": "..."}` after pack and weight. Every order email can be previewed without sending: `GET /v1/orders/{id}/mail/{placed|paid|pickup_ready|handoff}/preview?format=html|text`.

### Without Docker

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.lock
export ALLOW_INSECURE_DEV=true TAX_RATES_JSON='{"ON":0.13}' PAYMENT_PROVIDER=fake WEB_BASE_URL=http://localhost:3010
.venv/bin/uvicorn app.main:app --port 8010
curl -X POST http://127.0.0.1:8010/admin/seed-catalog        # demo makers, products, variants, stock

cd web && npm install
API_URL=http://127.0.0.1:8010 WEB_BASE_URL=http://localhost:3010 npm run dev   # http://localhost:3010
```

Tests: `.venv/bin/python -m pytest -q` (under a minute; the PostgreSQL race gate runs only with `TEST_POSTGRES_URL` set). `python tools/check_env.py` fails when code reads a setting `.env.example` does not list. Storefront: `cd web && npm run typecheck && npm run build`; idle request counter: `NODE_PATH=$(npm root -g) node web/tests/smoke-requests.mjs http://localhost:3000`.

## The honesty rules this shop is built on

They are not style. They are why several features are switched off by default.

1. **A figure the owner has not confirmed is never stated as fact.** Delivery times, the return window, the carrier and the data-retention periods come from settings; where a setting is empty the page says the value is not published yet, a proposed number is marked "not confirmed yet", and the page carries one line: we'll confirm this before the shop opens.
2. **A feature the code cannot complete is not sold.** Pickup disappears from checkout until a locker address is configured. A payment method disappears until its recipient is configured, and with no method left the checkout says the shop is not taking orders yet. A non-routable address (`.local`, `.test`, `.invalid`, `example.*`) counts as unset everywhere.
3. **The catalogue admits what it is.** Until `SHOP_CATALOGUE_STATUS=live`, every page carries a demonstration strip at the top and the line above the footer, every machine surface says the assortment is demonstration data, and every order placed is marked as a demo that asks for no money. Going live takes two deliberate settings, so opening the shop to search engines can never silently remove that line.
4. **The shop publishes no rating, no review and no stock count.** Availability is coarse on purpose: in stock, last ones, sold out.

## Storefront

### Pages
Home · shop with filters, search and paging · product · makers and maker · bag · checkout · order lookup and status · how it works · questions and answers · shipping and pickup · care · privacy · terms of sale. Every one exists in both languages.

On a phone the shop's filters fold into a "Filter · Sort" drawer with the active filters as chips, and the header carries a search control. Search understands both languages and both alphabets (`вишиванка`, `vyshyvanka` and `blouse` reach the same shelf; `app/services/search.py`), matches category and collection names, and offers the closest category when nothing matches. The bag stores SKU, slug and quantity only and reads titles, variant labels and prices from the API in the page's language. While the API cannot be read, catalogue pages answer HTTP 503 "The shop is catching up" in both languages.

Filters are URL state, so a filtered view can be shared and indexed: collection, category, provenance, price band, maker, in stock, sort. Paging is server-side, twelve to a page, two complete chart bands.

### Catalogue
`makers` and `products` are the storefront's own tables; the sellable unit stays the existing `variants` row (a SKU), now linked to a product with an option label such as `Brick & black / M`. Availability shown to a shopper is computed from the ledger across sellable locations and never exposes a location, a quantity or a barcode.

`POST /admin/seed-catalog` loads a **placeholder assortment** (`app/services/catalog_seed.py`): seven invented workshops and twenty-one products with English and Ukrainian copy, there to design against and to exercise the order pipeline. Replace it with the real sourcing sheet before launch (`/admin` → Import). Categories and collections are rows in the `categories` and `collections` tables, seeded with the lists above. Money columns are `NUMERIC(10,2)`. The seed is insert-only: it never changes a row the owner edited or imported. It also attaches one generated demonstration picture per product and per maker from `app/assets/catalogue/` (`app/services/catalog_media.py`); these are generated images of the kind of piece described, and the placeholder line above the footer, `/llms.txt`, `/llms-full.txt` and `/api/catalog` all say so. A shop seeded before the pictures existed gets them with `python -m scripts.seed_media`. Photos uploaded in `/admin` take precedence and are never replaced; until any picture exists, a tile draws a cross-stitch chart generated from the product's own slug.

### Orders
`POST /v1/storefront/orders` creates a **WEB** order in state `AWAITING_PAYMENT`. Prices are re-read from the database, stock is checked line by line, totals come from configuration:

| setting | meaning |
|---|---|
| `SHIPPING_FLAT_CAD`, `SHIPPING_FREE_OVER_CAD` | flat Canada Post rate and the free-shipping threshold |
| `PICKUP_ADDRESS` | the gate on locker pickup: empty means checkout does not offer it |
| `SHOP_TAX_MODE` | `unregistered` (no tax line), `gst_hst_registered` (GST or HST by delivery province as named lines, plus `SHOP_PST_REGISTERED_PROVINCES`; rates in `app/services/tax.py`), or `custom` with `TAX_RATES_JSON`. `SHOP_GST_NUMBER` prints on the order page and in emails |
| `SHOP_SHIP_EXCLUDE_PROVINCES` | provinces the shop does not ship to; default `QC` while there is no French storefront, stated on the shipping page and refused at checkout |
| `ETRANSFER_EMAIL` | offers Interac e-Transfer with the order number as the message |
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_ENV`, `PAYPAL_WEBHOOK_ID` | offers PayPal (first in the list); `sandbox` moves test money only |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | offers card payment through Stripe Checkout |
| `SMTP_HOST`, `MAIL_FROM` | turns order email on; without them the shop stops promising email |

The buyer ticks the terms and privacy notice before Place order. The order page address carries the order number only: the key to it is an HttpOnly cookie set at checkout or at lookup (a POST of number and email), or `?key=` in the order email link. Placing an order holds its stock for `ORDER_HOLD_MINUTES`; the scheduler releases a hold that expires unpaid. An order becomes `PAID` through the Stripe webhook (amount and currency checked) or an operator's `POST /v1/orders/{id}/mark-paid`, which reserves the goods in the same step; a paid order whose stock is gone raises a `PAID_OUT_OF_STOCK` exception naming the refund. The pipeline takes it from there: pick, pack, then ship with tracking or put it in a locker bay. A customer can cancel while it is unpaid. The owner works unpaid and paid orders in `/admin`; `GET /v1/orders/awaiting-payment` stays for scripts.

### Locker pickup
A buyer who chooses pickup gets their own one-time bay code the moment the packer puts the parcel in a bay. It reaches them by email when SMTP is configured, and it is always on their order status page, which they open with the order number and the email they used. The code opens one bay, expires after `PICKUP_CODE_VALID_HOURS`, and is revoked when the parcel leaves. Customer and courier credentials are separate: neither opens the other's door. Both are stored as salted PBKDF2 and both are behind per-credential and per-address lockouts.

### Search, answer engines and social
`sitemap.xml`, `robots.txt`, canonical and hreflang (`en`, `uk`, `x-default`), Open Graph images drawn as the shop's own cross-stitch chart at `/og`, and JSON-LD for the store, the site search, products with honest availability, collections and breadcrumbs. `robots.txt` is deny-all until `WEB_INDEXABLE=true`.

For answer engines there are three generated surfaces, all built from one snapshot so they cannot disagree: `/llms.txt` (a short map of the shop), `/llms-full.txt` (every product and maker as a compact line), and `/api/catalog` (a JSON feed). Each opens by declaring what the catalogue is and lists what the shop deliberately does not publish. See `docs/GEO.md`.

## Fulfillment core

- deterministic locations and an append-only inventory ledger with a rebuildable projection;
- idempotent order ingestion (Shopify `orders/paid` with HMAC and webhook-id dedup, plus the WEB and demo channels) and all-or-nothing reservation: a stock-out rolls back to zero reservations, so a retry after restock can never pack short;
- barcode-verified pick missions, package weight, and label verification bound to the tracking code EasyPost actually purchased;
- EasyPost rating, label purchase and pickup adapters, crash-safe: a retry recovers an existing purchase instead of buying a second label;
- order email (placed, paid, pickup ready, handed over), disabled and logging when SMTP is unset;
- a transactional outbox and a persistent WebSocket cloud-to-edge command channel with an attempt cap;
- a durable SQLite edge journal: the command is persisted before actuation and the completion before the cloud ACK, and a completed physical action can never be demoted by a transport failure;
- fail-secure locker drivers (simulated and Modbus TCP) with an inner-gate interlock and a proven de-energize: a coil that cannot be shown to have released raises and reports a fault instead of a silent success;
- the cloud never invents physical state: `UNLOCK_REQUESTED` becomes `COURIER_OPEN` only after the edge reports `LOCKER_UNLOCKED`, handoff needs a sensor-confirmed closed and relocked bay, and the operator API cannot write a sensor-derived field;
- per-device edge credentials with rotation and revocation, re-checked on the live socket so a revoked device stops receiving commands;
- an exception list an operator can actually close, commissioning mode, a Modbus map preflight, and bench and 100-cycle acceptance runners.

The edge daemon turns at-least-once delivery into effectively-once physical execution: receive, journal `RECEIVED`, actuate, journal `COMPLETED`, ACK. Set its site with `EDGE_SITE`; the cloud addresses commands with `LOCKER_EDGE_SITE` (or `EDGE_SITE`), and the two must match or commands stay pending.

Operator and admin routes need `X-API-Key` (`OPERATOR_API_KEY` / `ADMIN_API_KEY`) and fail closed when unset. `ALLOW_INSECURE_DEV=true` is for local work only.

## Layout

```
app/            FastAPI: api/ (admin_catalog, admin_orders for /admin), services/, models, schemas
edge/           garage daemon and locker drivers (simulated, Modbus)
migrations/     Alembic, also applied by the app container before start
scripts/        e2e_local.sh, prod_local_check.sh, backup/, demo_flow, stress_flow, locker_bench, locker_acceptance
deploy/         Caddyfile for docker-compose.prod.yml
tests/          pytest, 22 files
docs/           OWNER-ACTIONS.md, LAUNCH-RUNBOOK.md, locker-owner-actions.md, GEO.md, catalogue import template, locker hardware sheets
web/            Next.js storefront and /admin — see web/DESIGN.md (Operator section for /admin)
tools/          check_env.py, admin_password_hash.py, brand_assets.py (favicon, apple-touch icon, 512 px logo)
```
