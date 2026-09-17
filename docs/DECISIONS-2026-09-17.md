# Decisions taken on the owner's behalf, 17.09.2026

The owner wrote on 17.09: "decide everything yourself, go faster". Each line below is a decision
made under that instruction, with the reason in one line. Items marked **default for demo, to
confirm before real launch** are proposals the public demo runs on; the pages keep saying
"not confirmed yet" where they print them. The decisions that remain the owner's own before a
real (money-taking) launch are still listed in `docs/OWNER-ACTIONS.md`.

## 1. A public demo, not a live shop

| Setting | Value | Reason |
|---|---|---|
| `SHOP_CATALOGUE_STATUS` | `placeholder` | Keeps the demo strip on every page and marks every order as a test that asks for no money. |
| `PAYMENT_PROVIDER` | `fake` (Stripe test keys only if they exist; never live keys) | A visitor can walk the whole purchase without any money moving. |
| `WEB_INDEXABLE` | `false` | Search engines must not list a demonstration as a shop; pages carry noindex and robots.txt disallows all. |
| `STRIPE_SECRET_KEY` live / `ETRANSFER_EMAIL` | empty | No real payment route may exist in a demo. |

## 2. Address and hosting

- **Address**: `https://market.agintent.com`. agintent.com is the owner's own Cloudflare zone, so no domain is bought.
- **Hosting**: the docker compose stack (`docker-compose.yml` + `docker-compose.prod.yml`) on VPS docker-2
  (freelance-docker); fallback, if that server lacks room or access: the workstation behind a named
  Cloudflare Tunnel, as the other agintent.com apps run. Reason: the prod compose is already rehearsed
  (`scripts/prod_local_check.sh`), and both targets cost nothing extra.
- **Taken on 17.09.2026: the workstation fallback.** docker-2 had 48 MB of free memory with swap full and
  1.9 GB of free disk, too little to build and run the stack. The demo runs on the workstation behind the
  named tunnel `uamarket-demo`; details and commands in `docs/DEMO-DEPLOY.md`.
- **Database**: PostgreSQL from the compose file, nightly backups by the `backup` service (14 days). Reason: the runbook's tested path.
- **Mail**: Mailpit stays internal, no SMTP provider. When Mailpit is the mail server and `WEB_BASE_URL` is a
  public address, the storefront says the shop sends no email (`notifications_config`). Reason: a demo must
  not write to real inboxes, and a buyer on the public site would never see a Mailpit message.
- **Sign-in address behind a tunnel**: `ADMIN_CLIENT_IP_HEADER=cf-connecting-ip` when Cloudflare sits in
  front; empty behind Caddy alone. Reason: otherwise every visitor shares one address and the per-address
  sign-in lock would hit the owner too.

## 3. Seller model

- **Commission marketplace**: makers keep ownership of their pieces, the shop takes a commission on each sale.
  Reason: no stock purchase or consignment paperwork is needed before makers join.
- Operator data model note: `Maker` stays the owner of the piece; a future `commission_rate` per maker
  (or per product) and a payout ledger are the additions this model needs. Nothing is built for it yet.
- Public pages keep the neutral "shop" wording while the demo runs. Reason: terms naming a commission
  model need the lawyer's review first.

## 4. Policy figures (default for demo, to confirm before real launch)

| Setting | Demo value | How the pages show it |
|---|---|---|
| `SHOP_RETURN_WINDOW_DAYS` | `30` | Printed with "not confirmed yet" while `SHOP_CATALOGUE_STATUS` is not `live`; left out of search data (new `demoNote` in `web/lib/content.ts`). |
| `SHIPPING_FLAT_CAD` / `SHIPPING_FREE_OVER_CAD` | 12.00 / 150.00 (software default) | Checkout and shipping page; demo orders ask for no money. |
| `SHOP_CARRIER` | empty (proposal: Canada Post) | Pages describe "the carrier the label is bought from"; setting it would drop the unconfirmed marker, so it stays empty in the demo. |
| `SHOP_BASE_PLACE` | empty (proposal: Ottawa, Ontario) | No city named; same reason. |
| `SHOP_HANDLING_DAYS` | empty → 1–3 days | Marked "not confirmed yet". |
| `SHOP_SHIP_EXCLUDE_PROVINCES` | `QC` (software default) | Quebec refused at checkout with the reason (French storefront not built). |
| Retention (`SHOP_ORDER_RECORD_YEARS`, `SHOP_MESSAGE_RETENTION_MONTHS`, `SHOP_CANCELLED_RETENTION_MONTHS`) | empty → 7 years / 24 / 24 months | Marked "not confirmed yet". |
| `SHOP_GOVERNING_PLACE` | empty → Ontario, Canada | Marked "not confirmed yet". |

Reason for the whole table: sensible Canadian small-shop figures let the demo read like a shop, and the
honesty rules keep every one of them labelled as a proposal.

## 5. Tax rates, verified against official pages (17.09.2026)

Every rate in `app/services/tax.py` was compared with the official page on 17.09.2026. All matched, no change needed.

| Rate | Value in code | Official source and wording |
|---|---|---|
| GST | 5% | CRA GST/HST rate table: AB, BC, MB, NT, NU, QC, SK, YT 5% — https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/charge-collect-which-rate/calculator.html |
| HST ON | 13% | same CRA table |
| HST NS | 14% | same CRA table: "As of April 1, 2025, the HST rate has decreased to 14% in Nova Scotia." |
| HST NB, NL, PE | 15% | same CRA table |
| QST | 9.975% | Revenu Québec, Calculating the Taxes: QST at 9.975% on the price excluding GST — https://www.revenuquebec.ca/en/businesses/consumption-taxes/gsthst-and-qst/collecting-gst-and-qst/calculating-the-taxes/ |
| BC PST | 7% | "Generally, the rate of PST is 7% on the purchase or lease price of goods and services, with some exceptions." — https://www2.gov.bc.ca/gov/content/taxes/sales-taxes/pst |
| MB RST | 7% | "The general sales tax rate is 7%." — https://www.gov.mb.ca/finance/taxation/taxes/retail.html |
| SK PST | 6% | "Provincial Sales Tax (PST) is a six per cent sales tax that applies to taxable goods and services consumed or used in Saskatchewan." — https://www.saskatchewan.ca/business/taxes-licensing-and-reporting/provincial-taxes-policies-and-bulletins/provincial-sales-tax |

The demo runs `SHOP_TAX_MODE=unregistered` (no tax line): there is no GST/HST registration, and none is invented.
Registration, provincial registrations and whether shipping is taxed stay with the accountant.

## 6. Fixed before the public demo

| Fix | Where | Reason |
|---|---|---|
| Uploaded photos keep their order (positions 0, 1, 2…) | `app/services/catalog_admin.py` `next_image_position` | `max(position) or -1` turned position 0 into -1, so every photo after the first got 0. |
| `/admin/api` refuses `.`/`..` segments in any encoding, slashes/backslashes/`%` inside a segment, and any path the URL parser would rewrite | `web/lib/admin/api.ts` `safeJoin` | A double-encoded `..` reached API routes outside the allowlist with the admin key attached. |
| Sign-in: per-address lock after 5 wrong passwords; per-account slow-down (0.5 s doubling to 4 s after 10 failures from all addresses); no global lock | `web/lib/admin/session.ts`, `web/app/admin/api/login/route.ts` | The old shared lock let anyone lock the owner out with 25 wrong passwords. |
| Admin saves refresh the storefront at once | `web/lib/api.ts` (tag `catalog`), `web/app/admin/api/[...path]/route.ts` (`revalidateTag`) | Edits showed up to 30–60 s late. |
| Cancellation email to the buyer (EN/UK; refund sentence when paid, "do not send money" when unpaid; the internal reason is not quoted) | `app/services/mailer.py`, `app/api/admin_orders.py`, `app/api/storefront.py` | A cancelled buyer heard nothing. |
| Order history in the admin's language | `timeline` events carry `code` + `params`; `timelineText` in `web/lib/admin/i18n.ts` | The UK admin page showed English history lines. |
| Basic locker screen at `/admin/locker` (read-only: bay sensors, parcels with order links, whether a buyer code is live, courier windows, devices) | `GET /v1/admin/lockers`, `web/app/admin/(desk)/locker/page.tsx` | Locker pickup had no admin screen. Codes are never listed. |

## 7. Catalogue

- Stays demonstration data. No real maker's name, photo or story is published without that maker's consent.

## 8. Search and brand

- noindex and robots disallow for the whole demo (`WEB_INDEXABLE=false`).
- Title, icon and logo stay as designed (cross-stitched "UA"). No social accounts are created, no phone is published.

## Still off limits

No money spent (no domain, no paid service), no live payment keys, no invented legal entity, tax number,
reviews or partners, no messages or posts to people, no secrets in code, commits or reports.
