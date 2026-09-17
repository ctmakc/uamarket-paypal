# GEO — the answer-engine surfaces

An engineering note for the owner and for the next agent to touch `web/`.

People now find a shop by asking an assistant. "Where can I buy a vyshyvanka in
Canada" is answered from pages and files an assistant was allowed to read, and a
shop that publishes nothing machine-readable is a shop that is never named. This
directory of work is that publication: three files that describe UA Market to a
machine, generated from the live catalogue, carrying no claim the shop cannot
back.

Everything below is generated. Nothing here is hand-maintained content, so a new
product, a new maker or a sold-out variant reaches all three surfaces within one
cache window without anyone editing a file.

## The three surfaces

| URL | Type | What it is for |
|---|---|---|
| `/llms.txt` | `text/plain` (markdown) | The short map. What the shop is, where it ships from and to, the three provenance levels, the collections with their real counts, payment and delivery as configured, links to the canonical pages. 82 lines against the seeded catalogue; the shape holds it under 120. |
| `/llms-full.txt` | `text/plain` (markdown) | The same map plus every product on one line and every maker on one line. An agent that fetches this one file can answer "who made it, what is it made of, what does it cost, is it in stock" without walking the site. |
| `/api/catalog` | `application/json` | The same catalogue as data. Both languages in one payload, `generated_at` in the body, coarse availability, a `readme` block that states the rules. A Google Merchant feed would be generated from this. |

All three are built by `web/lib/geo.ts` from one `loadSnapshot()` read, which is
the point: three surfaces that quote different numbers are worse than two
surfaces and a gap.

`?lang=uk` returns the Ukrainian document from either text surface, and each
file links to its twin. The JSON feed carries both languages in every field
(`{ "en": …, "uk": … }`), so no consumer can pair an English title with a
Ukrainian price.

`/api/catalog` takes `?detail=summary` to skip technique, material, care,
description and variants. The default, `full`, costs one request per product to
the catalogue API and is worth it at this catalogue size; above
`GEO_DETAIL_LIMIT` (500 products) the detail pass is skipped automatically and
the surface says so in its own header.

## Which crawlers may read this, and why

`web/app/robots.ts` names four answer engines — `GPTBot`, `ClaudeBot`,
`PerplexityBot`, `Google-Extended` — and gives them the same access as a search
crawler: the catalogue, the maker pages and the content pages, with the bag,
the checkout, a customer's own order page and the fulfillment API closed.

The reasoning, which the owner has already been asked to confirm in
`OWNER-ACTIONS.md`: product copy, prices and maker stories are public sales
material, so an assistant paraphrasing them costs the shop little, and being
absent from the answer costs it a customer. Reversing the decision means moving
a bot's name out of `ANSWER_ENGINES` in `robots.ts` into a rule with
`disallow: "/"`. None of this is a security control — a crawler that ignores
`robots.txt` reads everything a browser reads.

While `WEB_INDEXABLE` is unset, `robots.txt` closes the whole site to everyone,
including these four. That is the correct state for a preview.

### The feed is open to the crawlers it exists for

`web/app/robots.ts` disallows `/api/` for every user agent, which would close
`/api/catalog` to the very crawlers it was built for. Both rule groups therefore
carry `Allow: /api/catalog` beside that `Disallow`: a more specific `Allow` beats
a broader `Disallow` for Google, Bing and the four answer engines. Verified on a
running instance with `WEB_INDEXABLE=true`; the same file also closes the
crawl traps (`?sort=`, `?price=`, `?in_stock=`, `?q=`).

## How to regenerate

There is nothing to regenerate by hand. Each request rebuilds the surface from
the catalogue API; `Cache-Control: s-maxage=900` lets a CDN hold the answer for
fifteen minutes, and `lib/api`'s own revalidate windows (30–60s) keep the
underlying calls cheap. `GEO_MAX_AGE_SECONDS` in `web/lib/geo.ts` is the one
number that changes that window, and it is printed inside the files themselves
so a reader knows how fresh the copy is.

To see them:

```
curl -s http://localhost:3010/llms.txt
curl -s "http://localhost:3010/llms.txt?lang=uk"
curl -s http://localhost:3010/llms-full.txt
curl -s http://localhost:3010/api/catalog | python3 -m json.tool | head -40
curl -s "http://localhost:3010/api/catalog?detail=summary" | python3 -m json.tool | head -40
```

To check that the surfaces still agree with the shop, compare the collection
counts printed in `/llms.txt` against the API they came from:

```
curl -s http://127.0.0.1:8010/v1/catalog/collections | python3 -m json.tool
```

The product total, the maker total, the per-collection counts, the per-category
counts and the provenance split all come from the same read, so one mismatch
means the catalogue changed between two requests and nothing worse.

## What these surfaces deliberately do not claim

This is the list, and it is printed on the surfaces themselves so an agent that
reads one is told what to stop looking for.

- **No ratings and no reviews.** The shop collects none. Nothing on any page,
  in any feed or in any structured data carries a score, a star or a review
  count. An answer that gives UA Market a rating invented it.
- **No stock counts.** Availability is one of `InStock`, `LimitedAvailability`,
  `OutOfStock`. `LimitedAvailability` comes from the shop's own "last ones"
  flag, which carries no number. The inventory ledger's figures stay inside the
  fulfillment core.
- **No delivery date for an individual order.** The carrier's tracking number
  is the only date the shop can give. A transit estimate appears only when
  `SHOP_TRANSIT_DAYS` or `SHOP_DELIVERY_ESTIMATE` is set; unset, the surfaces
  say plainly that the shop publishes no estimate.
- **No unconfirmed policy stated as policy.** The dispatch window is printed
  with the words "a software default the shop has not confirmed" until
  `SHOP_HANDLING_DAYS` is set. The return window is absent until
  `SHOP_RETURN_WINDOW_DAYS` is set, and the surfaces say the shop publishes
  none.
- **No phone number.** None exists in configuration, and every surface says the
  shop takes orders and questions by email.
- **No pickup a buyer cannot actually choose.** The pickup sentences follow
  `pickup.enabled` on the storefront config, which is true only when the switch
  is on and an address is set — the same key the checkout branches on, and a
  `PICKUP` order sent while it is false is answered `400 Pickup is not
  available`. With it false the delivery section says pickup is not offered and
  the "does not publish" list carries a pickup point and its street address; with
  it true the surfaces print the address (`PICKUP_ADDRESS`, or the line composed
  from `SHOP_PICKUP_ADDRESS_JSON`), the hours if any are set, and how the
  one-time code reaches the buyer — email plus the order page while SMTP is
  configured, the order page alone while it is not.
- **No product photographs claimed.** The seeded catalogue carries generated
  demonstration pictures, and while the catalogue status is `placeholder` the
  surfaces declare exactly that: the images show the kind of piece described and
  no photograph here shows goods in stock. A catalogue with no image at all falls
  back to the older line about the generated chart, and a `live` catalogue with
  uploaded photos declares neither, so the entry disappears by itself once real
  photographs arrive.
- **No maker, region, technique or material that the catalogue did not
  record.** A missing value leaves an empty field, and the file's own header
  says an empty field means the shop has not recorded that value.

## Placeholder or live

`catalogueStatus()` in `web/lib/geo.ts` decides whether the assortment is the shop's
real stock. It returns `live` only when `SHOP_CATALOGUE_STATUS` is exactly `live`
(case and surrounding spaces ignored); any other value, and no value at all, is
`placeholder`. It does not look at `WEB_INDEXABLE`: opening the site to search
engines and declaring the catalogue real are two separate settings, so one can
never switch the other on. The API reads the same setting (`catalogue_live()` in
`app/services/storefront.py`) to mark orders as demo orders. While the status is
`placeholder`, every surface opens with a paragraph naming it as such and asking
a quoting agent to say so, and every page carries the demonstration strip.

The default is `placeholder` on purpose. A real catalogue described as a
placeholder costs the shop a sentence; a placeholder catalogue described as real
stock is a falsehood an assistant repeats to a customer.

## The Google Merchant feed, and why it is not here yet

`/api/catalog` is the structure a Merchant Center feed would be generated from:
it already carries the identifiers (`slug`, per-variant `sku`), the prices in
CAD, the coarse availability, the canonical URLs per language, the maker as a
brand candidate and the shipping configuration. Building the XML now would
produce a feed Merchant Center rejects, because two required things are missing:

1. **An image per product.** `image_link` is required, and the demonstration
   pictures do not qualify: Merchant Center wants the image of the goods being
   sold, and submitting a generated picture of "the kind of piece described"
   would misrepresent them exactly as the counted chart would. This waits for the
   owner's photographs, taken of the real stock.
2. **A product identifier policy.** Merchant Center wants GTIN or MPN, or an
   explicit `identifier_exists: false` per product. Hand-made pieces genuinely
   have neither, and that declaration belongs to the owner.

Both are in `OWNER-ACTIONS.md`. Once photographs exist, the feed is a small
route that reads the same `buildCatalogFeed()` snapshot and writes XML.

## Files

- `web/lib/geo.ts` — the snapshot loader and all three builders. Every honesty
  rule above is enforced here rather than in a route, so a fourth surface
  inherits them.
- `web/app/llms.txt/route.ts`, `web/app/llms-full.txt/route.ts`,
  `web/app/api/catalog/route.ts` — thin handlers: read the query, load the
  snapshot, set the content type and the cache header, answer 503 with
  `Retry-After` when the catalogue cannot be read.
- `web/app/robots.ts` and `web/app/sitemap.ts` — the traditional half of the
  same job, owned by the SEO work.

`web/proxy.ts` passes any path ending in a file extension and any path under
`/api`, so all three URLs reach their routes without a locale rewrite. There is
no `/uk/llms.txt`; the Ukrainian document is `?lang=uk` on the one canonical
address.
