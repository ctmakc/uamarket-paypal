# DESIGN — UA Market storefront («КАНВА» / Counted Thread)

Subject & audience: an online shop + small marketplace of Ukrainian goods (vyshyvanky, rushnyky, motanky, Opishnia ceramics, gifts) for the Ukrainian diaspora in Canada and Canadians buying authentic things; Ottawa base, Canada Post shipping, locker pickup.
Page job: make the shop feel real and specific in three seconds, then let a person find a size, see who made the thing and where, and pay without doubt.

Direction: **«КАНВА» — the counted-thread chart.** UA Market sells cloth made one counted square at a time, so the page is built the same way: undyed flax linen as the ground, the embroiderer's chart (a 12px stitch, a bold line every tenth) as the layout law, two threads (black and garnet red) carrying all colour, and everything that appears gets *stitched in* row by row instead of fading up. Chosen over «ЛАВКА / The Stall» (kraft table, hanging tags on strings, chalk boards, KyivType Titling): the stall's tilted hanging photos and chalk boards hurt product scannability and read as café decor; its thermal-receipt order page is grafted here.

Unexpected pairing / risk taken: Swiss-chart rigour (grotesk, mono legend, counted grid, zero radius) for a folk-craft shop. The risk is dullness on a grey-beige ground; the answer is the red thread used only where a stitch means something, and photos/motifs that bleed to the tile edge.

## Palette (warm; never pure #000/#fff)
| token | hex | role |
|---|---|---|
| `--linen` | `#D9D2C1` | page ground, undyed flax (ink on it 10.98:1) |
| `--linen-bleached` | `#E8E3D6` | tile, drawer, input and reading-sheet surface; separation by lightness, never border or shadow |
| `--linen-shade` | `#CBC3B0` | pressed / selected / current-row ground |
| `--ink` | `#221E1B` | text and display type |
| `--ink-plate` | `#1E1A17` | dark plate: footer, bag-drawer head, maker band without photo |
| `--thread-black` | `#2A2320` | stitched lines, X marks, backstitch outlines, running stitches |
| `--thread-red` | `#A11D2B` | the one accent: price, add-to-bag, hand-embroidered mark; ≤3 per viewport (5.11:1 on linen) |
| `--thread-red-lit` | `#E5525B` | red on `--ink-plate` only (4.68:1); never on linen |
| `--thread-white` | `#EFE9DC` | text and stitches on `--ink-plate` (14.3:1) |
| `--muted` | `#574F48` | maker line, captions, secondary text (5.33:1 on linen) |
| `--thread-green` | `#245A32` | semantic only: in stock, paid, delivered |
| `--thread-mustard` | `#715608` | semantic only: low stock, payment pending |
| `--count-minor` | `rgba(42,35,32,.06)` | 12px chart line inside chart regions |
| `--count-major` | `rgba(42,35,32,.14)` | every tenth line (120px), the chart's bold rule |

## Type
- **Fixel Display** (MacPaw, Kyiv; SIL OFL 1.1, files in `public/fonts/`, licence alongside) — 900 for the hero line and footer wordmark, 600 for H2/H3, 200 for the hero sub-line. Hero `clamp(2.75rem, 1.4rem + 6vw, 7rem)`, tracking −0.03em, line-height 0.94 snapped to the 12px stitch. H2 36/36, H3 24/24. Heavy on purpose: embroidered lettering is always heavy.
- **Fixel Text** — 400 at 17/24 for reading (measure ≤62ch), 500 at 14/24 for UI. Tracking 0. No uppercase eyebrows.
- **Fira Mono** (SIL OFL) — 12/24 and 14/24, `tabular-nums`, tracking 0.02em: prices (`CA$ 148.00`), the chart-key line, sizes, order numbers, the bag cut list; 40/48 for the product-page price.
- Why: cross-stitch is a monoline craft and Fixel is a monoline grotesque with first-class Ukrainian Cyrillic, so EN and UK pages are twins. The colophon carries the same origin label the products do: “Typeface: Fixel, Kyiv”.

## Layout primitive — THE COUNTED BLOCK
One stitch `--st: 12px`; one block `--blk: 120px` (ten stitches, bold line every tenth). Desktop canvas 1440 = 12 blocks; page margin one block on desktop, one stitch on mobile. Vertical rhythm in stitches: body 24, H2 36, H1 96, section gaps 96/144/192. Product rows are chart bands with tile widths 4/3/5 blocks, next row 5/4/3; the hand-embroidered piece takes the wide slot. Chart lines live only inside chart regions (tiles, hero motif, bag, order row-counter), never as page wallpaper. The price always lands in the last cell of a tile's bottom row.

## Motion personality — needle rhythm
Signature moments use `steps()`: stitch fills `steps(10, end)`, underlines `steps(8)`, the bag knot `steps(2)`. Functional UI keeps a 160ms ease-out (link colour, drawer). Hero moment 1.4s: the motif stitches itself in row by row, red pass first, then black. Reveals are mask-row fills, never opacity+translateY. Hover: text link = dashed thread underline grows left→right; chart tile = the planned faint X's fill to 100%; photo tile = the selvedge row stitches in and the price cell inverts to ink. `prefers-reduced-motion`: everything arrives finished.

## Signature elements
1. Counted-grid layout law with the bold-every-tenth chart rule; 4/3/5 tile rhythm.
2. Procedural motif tiles: a 24×24-stitch four-fold-symmetric motif generated from the product slug, 60% stitched, finished on hover — the tile before photos exist.
3. Origin stitch-marks as the provenance system: red X = hand-embroidered; black running stitch = made in Ukraine; dotted square = designed in Ukraine, made abroad. Top-left of every tile, beside the product H1, in the bag's symbol column, legended in the footer.
4. The chart-key line in Fira Mono under every product, built only from maker-supplied data (technique · material · region); the bag is a cut list; the order page is a receipt with a row counter.
5. Stitch-in motion: the hero motif embroiders itself, the collection runner is stitched by scrolling, the footer wordmark is charted in X's.

## Photography — the linen table

Every picture in the shop is taken on the same surface the design is built on: a piece of
undyed flax linen, lit by soft diffuse daylight from one side, with no hard shadow, no
gradient, no vignette and no prop that is not for sale. The object lies flat-on and fills
the square; a garment is laid out with its sleeves spread so the embroidery reads at tile
size, and a pot or a doll is shot straight on at eye height. Colour stays inside the
palette the page already uses — flax, ink, garnet — so a photo tile and a chart tile can
sit in the same row without one shouting. Maker pictures are the workshop instead of the
goods: hands at work, a loom, a wheel, a table of thread. No faces, because a face in a
96 px square is a portrait of a person nobody asked, and the makers here are invented.

The pictures shipped with the demonstration catalogue (`app/assets/catalogue/`) are
generated to this brief, and the shop says so in the line above the footer, in `/llms.txt`,
`/llms-full.txt` and `/api/catalog`. A workshop's own photograph replaces one the moment it
arrives, and it is shot to the same rules: the reason the ground is linen is that the goods
are cloth, and a white studio sweep makes home-woven linen look grey.

## Ledger check
Differs from every ledger row on ≥4 of 5 axes: flax linen ground (no row), Fixel + Fira Mono (no row), garnet thread accent (red family shared only with rows that differ on all other axes), counted-grid signature with procedural motifs (no row), steps() stitch-in motion (no row). marta-stepanenko zigzag divider and UAFest rushnyk stripes are not used.

## Forbidden here
Any border-radius (the only radius is 0) · any box-shadow or glow · any gradient · glassmorphism · flag blue+yellow, tryzub or flag glyphs as decoration · zigzag dividers and rushnyk stripes-behind-object · feTurbulence grain · opacity+translateY fade-ups, parallax zoom · spring/bounce easing · pill chips, rounded buttons, tinted icon squares · serif type anywhere · icon sets and emoji (only drawn stitch marks, → and inline SVG) · chart grid as full-page wallpaper · centered hero + 3 icon cards + stat row · uniform bordered card grid · hover translateY(−2px) · mono uppercase eyebrows as wallpaper · fabricated thread counts, DMC numbers or regions · pure #000/#FFF · a dark theme toggle.

## Copy
Buttons say what happens (“Add to bag”, “Place order”). Provenance is stated in words next to its mark. No “streamline/empower”, no manufactured contrasts.

---

## Operator — «ЗВОРОТ» (the back of the cloth)

The shop floor is the front of the embroidery; `/admin` is its reverse side, where the embroiderer counts. Same tokens, same faces, same zero radius, no new colour. What changes is density and posture: the storefront sells one thing at a time, the operator screens move many rows fast, on a laptop at a desk and on a phone at a packing bench with a USB scanner plugged in.

Direction check: this is an extension of «КАНВА», not a new direction, so no ledger row. Nothing from the storefront's forbidden list is allowed here either (no radius, shadow, gradient, pill chips, icon sets).

### Rules
- **Ground and surfaces.** Page on `--linen`; working surfaces (tables, forms, the next-action slab's body) on `--linen-bleached`; the row under the cursor or selected on `--linen-shade`. The next-action slab is `--ink-plate` with `--thread-white` text: the one dark thing on an operator page, so the eye finds it first.
- **Type.** Fixel Text 500 at 14/24 for everything operators read in rows; Fixel Display 600 for page titles (H1 at `--fs-h1`, never the hero size); Fira Mono for order numbers, SKUs, barcodes, money, weights, timestamps. Money always two decimals, right-aligned, tabular.
- **Tables are cut lists.** Rows 48px (4 stitches) on desktop with a dashed `--count-major` rule between them, no vertical rules, no zebra. Numeric columns right-aligned mono. On phones a table becomes a stack of rows: first line = the name, second line = mono facts.
- **Touch targets.** Every action ≥48px tall (the next-action button is 60px) and full-width on phones; the next-action slab sits directly under the order number, so the step to take is inside the first screen at 390px.
- **Status is words plus a thread colour**, never a coloured pill: `--thread-green` for paid / shipped / on sale, `--thread-mustard` for awaiting payment / not on sale, `--thread-red` only for a problem or a destructive confirm. A 2px left stitch (border-left) in that colour marks the row.
- **Scanner input.** A 60px mono input with the dashed underline doubled (3px), autofocused whenever the order's next step is "scan", keeps focus after each scan, submits on Enter (USB scanners type the code then Enter). Result line under it: green "✓ <SKU> scanned" or red "<code> is not in this order" with the red solid underline; the input is cleared and refocused either way.
- **Red budget.** One red element per screen: the primary button of a destructive step, or the error. The next-action button is `--thread-red` on the ink slab only when it moves money or stock (mark paid, cancel); otherwise it is linen-bleached on ink.
- **Motion.** Functional only: 160ms ease on hover/pressed, a `steps(8)` dashed underline on the current section in the top bar. No reveal animations: a timeline row that animated in with clip-path was caught half-drawn in the first screenshot round and removed. `prefers-reduced-motion` removes all of it.

### Frame
```
desktop ≥1024                                              phone <1024
┌──────────────────────────────────────────────────────┐   ┌──────────────────────────┐
│ ▣ UA Market · Admin   Orders Products Makers Stock   │   │ ▣ Admin        UK  ☰     │
│                       Import           UK · Sign out │   ├──────────────────────────┤
├──────────────────────────────────────────────────────┤   │ Orders Products Stock …→ │  (row scrolls)
│ content, max 1200, one-block gutter                  │   │ content, 2-stitch gutter  │
```

### Order queue
```
Orders                                   Paid today CA$ 0.00
[Awaiting payment 1] [To pack 2] [Ready to ship 0] [Shipped 5] [Problems 1]   ← tabs, dashed underline on current
search order number, name, email ______________________
───────────────────────────────────────────────────────────────────────────────
│ UA-260917-4KQ2   Olena Buyer · Kanata ON        2 items   CA$ 88.14   Scan →
│ mono             text                           mono      mono right  next step
```

### Order page (the workbench)
```
← Orders
UA-260917-4KQ2                              Paid, preparing   DEMO
Placed 2026-09-17 14:02 UTC · Card (test)

┌─ NEXT ────────────────────────────────────────────────────────┐  ink slab
│ Scan each item                                                 │
│ ┌────────────────────────────────────────────┐                 │
│ │ scan or type a barcode ▌                    │  [Check]        │  60px mono input
│ └────────────────────────────────────────────┘                 │
│ ✓ OPISHNIA-MUG-01 scanned   /   0000 is not in this order      │
└───────────────────────────────────────────────────────────────┘
Placed ✕ · Paid ✕ · Reserved ✕ · Scanned ○ · Packed ○ · Shipped ○    row counter

Items                                  │ Ship to            │
[photo] Opishnia mug                   │ Olena Buyer        │
        Green vine · 350 ml  ×2  ✓     │ 1 Main St          │
        OPISHNIA-MUG-01   CA$ 76.00    │ Kanata ON K2K 1X1  │
                                       │ Customer           │
Totals  subtotal / shipping / tax      │ email · phone      │
                                       │ Payment            │
Timeline (newest last, mono times)     │ Note from buyer    │
Emails: placed ✓ preview · paid ✓ preview · shipped —
Problems (open first) [Resolve with note]
Cancel order (note required) — quiet ghost button at the very end
```
Next-step variants in the slab: **Mark e-Transfer received** (reference field + red button) · **Waiting for card payment** (no button) · **Reserve stock** · **Scan** (above) · **Pack**: weight in grams input prefilled with the estimated item weight + "Packed" · **Ship**: carrier + tracking inputs + "Mark shipped", and "Get label rates" when EasyPost is set · **Done** (tracking shown). On phones the slab spans the full width under the header.

### Product editor
```
← Products
Linen towel                        Not on sale · [Put on sale]   Preview ↗
┌ problems before it can go on sale (mustard stitch) ─────────────┐
│ · Shipping weight for LINEN-TOWEL-01                              │
└──────────────────────────────────────────────────────────────────┘
Text          EN column            │ UK column              (stack on phone)
              Title                │ Назва
              Subtitle / Description / Technique / Material / Care
Facts         Category ▾  Collection ▾  How it was made ▾  Maker ▾  Featured □
[Save]

Variants (cut list)
SKU            Label EN   Label UK   Price   Weight g  Stock (avail/on hand)  ⋯
LINEN-TOWEL-01 40×140 cm  40×140 см  59.00   260       2 / 2                  Edit · Retire
+ Add variant  (inline row: label EN, label UK, price, weight; SKU and barcode fill themselves)
Edit opens the full row: barcode, cost, fibre content, country, HS code, L×W×H cm

Photos
┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
  Drop photos here, or choose files       dashed stitched box, 144px tall
  JPEG, PNG or WebP · up to 15 MB
└ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
[img] 1  alt EN ____  alt UK ____   ← → Delete      (first photo = the tile photo)

Size chart (garments): rows of size × measure cells, unit cm/in
```

---

## Buying on a phone (wave 3)

Same КАНВА tokens, no new direction. What changed and why:

- **Home at 390 px.** The hero motif becomes a border band one block tall across the top of the
  hero (the chart's middle rows, the way a rushnyk ends), the shop's pick comes before the
  collections, and collections turn into a two-column index of small counted tiles with no lede.
  The first product tile sits inside the first screen.
- **Shop at 390 px.** The six filter rails fold into one ink-plate button "Filter · Sort (n)" that
  opens a bottom sheet (linen ground, 2px thread-black top rule, red "Show N pieces"). Active
  filters stay on the page as inverted chips with the unpick mark. Desktop keeps the rails.
- **Header.** Below 1024 px a square search control (a dashed ring magnifier) opens a search row
  pinned under the header; at 400 px and below the menu button keeps its glyph and drops the word.
- **Add to bag.** A toast under the header: bleached plate, hairline border, green 3px rule, the
  piece and its variant in the page's language, "View bag" (ghost) and "Checkout" (red). It
  enters with a stepped clip (240 ms, steps(8)) and closes itself after six seconds unless hovered
  or focused.
- **Gallery.** Thumbnails are buttons with a 2px red frame when chosen; the main frame takes a
  horizontal swipe; a square "full screen" control opens a plate-dark dialog with a mono counter.
- **Bag.** "Your bag · 2 items" with the count in the ExtraLight display weight. On a phone the
  quantity and the price share the line under the name.
- **Checkout.** One message per field, cleared as soon as the field is edited; the terms and
  privacy tick sits between the demo line and Place order, which stays disabled until it is
  ticked. A province the shop does not ship to prints its reason in red under the address.
- **Order steps.** Placed · Paid · Packed · Shipped (five steps for locker pickup), numbered mono
  cells; below 420 px they stack into a list.
- **Seller block.** A bleached plate with a thread-black rule on terms, privacy and how-it-works;
  a value the owner has not given reads "not published yet" in mustard mono.
- **Order email.** Table layout, linen ground, bleached receipt with a red top rule, mono money,
  named tax lines, one red "Open your order" button, no images.
- **Icons.** The footer's cross-stitch alphabet, "UA" in thread-red-lit on the ink plate with the
  minor grid (`tools/brand_assets.py`).
