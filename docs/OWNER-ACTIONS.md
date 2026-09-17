# Before opening: the owner's decisions

Each line is a decision only you can make, the setting it fills in the server's env file, and
what the shop does while the setting is empty. Nothing here needs a programmer: send the
answer, it is typed into the env file once, and every page, email and feed changes together.
How to switch things on in order: `docs/LAUNCH-RUNBOOK.md`. Locker pickup, which can wait
until after opening: `docs/locker-owner-actions.md`.

## A. The shop cannot take a real order until these are answered

| # | Decision | Setting | While it is empty |
|---|---|---|---|
| 1 | The shop's domain (`uamarket.com` belongs to someone else) | `SHOP_DOMAIN`, `WEB_BASE_URL=https://<domain>` | Nothing can be deployed; email links point nowhere |
| 2 | A monitored contact mailbox, and who reads it | `SHOP_CONTACT_EMAIL` (optional `SHOP_PRIVACY_EMAIL`, `MAIL_REPLY_TO`) | Pages say the contact address is not published yet |
| 3 | The email provider and the sender address on the shop's domain | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`, `MAIL_PROVIDER_NAME` | No email is sent; checkout and the order page say so |
| 4 | How customers pay: a Stripe account, an e-Transfer mailbox, or both | `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET`, `ETRANSFER_EMAIL` | Checkout says the shop is not taking orders yet |
| 5 | The registered seller name and business address | `SHOP_LEGAL_NAME` (`_UK`), `SHOP_BUSINESS_ADDRESS` | Terms, privacy and how-it-works print "not published yet" |
| 6 | GST/HST registration, with the accountant: mode, number, any provincial registrations, whether shipping is taxed | `SHOP_TAX_MODE` (`unregistered` / `gst_hst_registered` / `custom`), `SHOP_GST_NUMBER`, `SHOP_PST_REGISTERED_PROVINCES` | No tax line is added (correct only for a small supplier that is not registered) |
| 7 | The real catalogue: makers, products, photos with alt text, prices, weights, stock, size measurements, care lines | entered in `/admin` or imported (`docs/catalogue-import.md`), then `SHOP_CATALOGUE_STATUS=live` | Every page carries the demonstration strip and every order is a test that asks for no money |
| 8 | The business model toward makers: buy and resell, consignment, or a commission marketplace | none yet; wording on the site stays "shop" | Terms describe the shop as the seller of every piece |

The accountant also confirms the rates written in `app/services/tax.py` (GST 5%; HST 13% ON,
14% NS, 15% NB/NL/PE; QST 9.975%; BC PST 7%; MB RST 7%; SK PST 6%, checked against the official CRA and provincial pages 17.09.2026, all matched; sources in `docs/DECISIONS-2026-09-17.md`).

## B. What the policy pages promise

| # | Decision | Setting | While it is empty |
|---|---|---|---|
| 9 | Returns: days after delivery, by mail or in person, who pays return postage, days to refund | `SHOP_RETURN_WINDOW_DAYS`, `SHOP_RETURN_METHOD`, `SHOP_RETURN_FEES`, `SHOP_REFUND_BUSINESS_DAYS` | Pages ask the customer to write; no return policy in search data |
| 10 | Postage: the flat rate and the free-shipping threshold | `SHIPPING_FLAT_CAD`, `SHIPPING_FREE_OVER_CAD` | CA$ 12.00 flat, free over CA$ 150.00 (see appendix) |
| 11 | The carrier named in public | `SHOP_CARRIER` | Pages say "the carrier the label is bought from" and name no company |
| 12 | Working days from payment to handover, and whether to publish a transit estimate | `SHOP_HANDLING_DAYS` (e.g. `1-3`), `SHOP_TRANSIT_DAYS`, `SHOP_DELIVERY_ESTIMATE` (`_UK`) | 1–3 days printed and marked "not confirmed yet"; no transit promise |
| 13 | Where parcels leave from | `SHOP_BASE_PLACE` (`_UK`) | No city is named anywhere |
| 14 | Quebec: ship there (and fund a French storefront) or not yet | `SHOP_SHIP_EXCLUDE_PROVINCES` (`QC` or `none`) | Quebec is refused at checkout with the reason stated |
| 15 | Record retention: paid orders, email threads, cancelled unpaid orders | `SHOP_ORDER_RECORD_YEARS`, `SHOP_MESSAGE_RETENTION_MONTHS`, `SHOP_CANCELLED_RETENTION_MONTHS` | 7 years, 24 and 24 months printed, each marked "not confirmed yet" |
| 16 | A lawyer's review of the terms and the privacy notice, the governing law, and the version date | `SHOP_GOVERNING_PLACE` (`_UK`), `SHOP_TERMS_VERSION`, `POLICY_WRITTEN_ISO` in `web/lib/content.ts` | The pages stand as drafted; Ontario is named and marked "not confirmed yet" |
| 17 | The hosting provider named on the privacy page | `SHOP_HOSTING_PROVIDER` | Privacy page lists hosting as "not published yet" |
| 18 | Which extra emails customers get (cancellation, stock-out delay, refund) and who writes the ones that stay manual | none yet | Three emails go out: received, paid, shipped. A delay or a refund is written by a person |

## C. Being found

| # | Decision | Setting | While it is empty |
|---|---|---|---|
| 19 | Open the shop to search engines, only after 1–7 are done | `WEB_INDEXABLE=true` | `robots.txt` closes the site and pages carry noindex |
| 20 | Approve the proposed search title and description ("Ukrainian vyshyvanky, rushnyky and gifts, shipped in Canada") or send your own | `SEO_USE_PROPOSED_TITLES=true` (text in `web/lib/i18n.seo.ts`) | Google shows the hero line "Ukrainian things, counted stitch by stitch" |
| 21 | Approve the icon and logo (the cross-stitched "UA", `web/public/logo-512.png`) or send a replacement | re-run `tools/brand_assets.py` with a new mark | The cross-stitched "UA" is used |
| 22 | Social accounts to link, and whether a phone number is published | none yet | No profile links, no phone in structured data |
| 23 | Whether AI assistants may read the catalogue (allowed today for product, maker and content pages) | `web/app/robots.ts` | Allowed |

## D. Can wait until after opening

- The garage locker: every locker and courier decision is in `docs/locker-owner-actions.md`.
  Pickup stays off at checkout while `PICKUP_ADDRESS` is empty.
- A paid order with one line out of stock waits whole (no partial shipments). Say if partial
  fulfilment is wanted; it needs a second parcel and a rule for its postage.
- Who may close a problem on the order queue (today: anyone signed in to `/admin`).
- Price bands on the shop page (`SHOP_PRICE_BANDS_CAD`, today under 50 / 50–120 / 120–250 / 250+).
- A Google Merchant feed: needs photos for every product and your statement that hand-made
  pieces have no GTIN.

## Appendix: defaults the software runs on today

Confirmed by you or not, these are what the shop does now. Change any of them with the setting.

| Setting | Default | Where it shows |
|---|---|---|
| `SHIPPING_FLAT_CAD` / `SHIPPING_FREE_OVER_CAD` | 12.00 / 150.00 | checkout, shipping page, FAQ, emails |
| `SHOP_HANDLING_DAYS` | 1–3 working days, marked unconfirmed | shipping page, FAQ, search data. `SHOP_PROCESSING_DAYS_MIN/MAX` still work and are read only when it is empty |
| `SHOP_ORDER_RECORD_YEARS` | 7 | privacy page, marked unconfirmed |
| `SHOP_MESSAGE_RETENTION_MONTHS` | 24 | privacy page (email threads), marked unconfirmed |
| `SHOP_CANCELLED_RETENTION_MONTHS` | 24 | privacy page (cancelled unpaid orders), its own setting, marked unconfirmed |
| `SHOP_GOVERNING_PLACE` | Ontario, Canada | terms, marked unconfirmed |
| `SHOP_SHIP_EXCLUDE_PROVINCES` | QC | checkout refusal, shipping page, FAQ |
| `SHOP_TAX_MODE` | unregistered (custom while `TAX_RATES_JSON` is set) | checkout, order page, emails |
| `ORDER_HOLD_MINUTES` | 60 | FAQ, terms; stock is released by the scheduler |
| `ORDER_MAIL_MAX_AGE_DAYS` | 14 | the mail sweep never mails an order older than this |
| `SCHEDULER_INTERVAL_SECONDS` | 300 | the scheduler service: due email and expired stock holds |
| `ADMIN_LOGIN_LOCK_SECONDS` | 900 after 5 wrong passwords | `/admin` sign-in |
| `MEDIA_MAX_UPLOAD_MB` | 15 | `/admin` photo upload |
| `BACKUP_HOUR_UTC` / `BACKUP_KEEP_DAYS` | 07:00 UTC / 14 days | production backups |
| Sitemap | home, shop, one page per collection, category and provenance level (`?origin=`), products, makers, policy pages, in both languages | `/sitemap.xml` once `WEB_INDEXABLE=true` |
| Rate limits | 10 orders and 60 order lookups per visitor address per 10 minutes; 30 rejected form submissions | API |
