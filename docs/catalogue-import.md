# Catalogue import: columns

`/admin` → Import reads a CSV saved as UTF-8, one row per variant (a size, colour or option
that has its own SKU). Start from `docs/catalogue-import-template.csv` (also downloadable from
the import screen); its three rows are marked EXAMPLE and must be replaced.

**Check the sheet** validates every row and writes nothing. **Apply import** writes the whole
sheet in one transaction; a sheet with any row in error writes nothing.

Matching: `product_slug` finds a product, `sku` finds a variant, `maker_slug` finds a maker.
A row for something that exists updates it; an empty cell leaves the stored value alone.
Importing the same sheet twice creates nothing new.

| column | required | meaning |
|---|---|---|
| `product_slug` | yes | address name of the product page: a–z, 0–9, hyphens (`/product/<slug>`) |
| `sku` | yes | the variant's stock code: A–Z, 0–9, hyphens; unique in the shop |
| `on_sale` | no | `yes` asks to put the product on sale after import; it goes on sale only if the checks in `/admin` pass |
| `title_en`, `title_uk` | `title_en` on a product's first row | product title |
| `subtitle_en`, `subtitle_uk` | no | one line under the title |
| `description_en`, `description_uk` | no (both needed on a live catalogue) | product description |
| `category` | on a product's first row | one of the category slugs in `/admin` (women, men, kids, home, dolls, ceramics, gifts) |
| `collection` | on a product's first row | one of the collection slugs (heritage, everyday, home, kids, gifts) |
| `origin` | no | `HANDMADE_UA`, `MADE_UA` (default) or `DESIGNED_UA` |
| `maker_slug` | no | the maker; a new slug creates the maker and then needs `maker_name_en` |
| `maker_name_en`, `maker_name_uk`, `maker_region_en`, `maker_region_uk` | no | maker details |
| `technique_en/uk`, `material_en/uk`, `care_en/uk`, `origin_note_en/uk` | no | product facts shown on the page |
| `option_label_en`, `option_label_uk` | no | the variant's name on the page, e.g. `M` or `40 × 140 cm` |
| `price_cad` | yes | price in Canadian dollars, e.g. `120.00` |
| `cost_cad` | no | what the shop paid; never shown to shoppers |
| `weight_g` | needed to go on sale | packed weight of one unit in grams |
| `length_cm`, `width_cm`, `height_cm` | no | packed size of one unit, for label rates |
| `fibre_content` | no | the text on the care label |
| `country_of_origin` | no | two-letter code, e.g. `UA` |
| `hs_code` | no | customs tariff code, 6–10 digits; confirm with the carrier or a broker |
| `barcode` | no | the barcode printed on the item; empty makes an in-store EAN-13 starting with 2 |

Stock is not imported: receive it on the Stock screen, where each change is a ledger entry
with a reason.
