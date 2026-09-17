# Pictures for the demonstration catalogue

One WebP per seeded product (`products/<slug>.webp`) and per seeded maker
(`makers/<slug>.webp`), 1024 px square. `app/services/catalog_media.py` attaches them
when the catalogue is seeded, and `python -m scripts.seed_media` fills them in on a shop
seeded before they existed.

**These are generated images, not photographs of goods.** They show the kind of piece each
entry describes, to the brief in `web/DESIGN.md` ("Photography — the linen table"): the
object flat on undyed flax linen, soft diffuse daylight from one side, no hard shadow, no
gradient, no prop that is not for sale, nothing in frame but the piece. Maker pictures are
the workshop with no people in it — no face is invented for a maker who does not exist.

The shop says so wherever it describes itself: the line above the footer on every page, the
preview paragraph in `/llms.txt` and `/llms-full.txt`, the `placeholder` note and the
`product_photos` entry of the "does not publish" list in `/api/catalog`, and the FAQ entry
`chart-instead-of-photo`. Each database row keeps `seed-generated/<slug>.webp` as its
original file name, so the same thing is visible in `/admin`.

## Replacing one with a real photograph

Upload it in `/admin` → the product → Photos. An uploaded photo takes position 0 and the
generated one can be deleted there like any other. `scripts/seed_media.py` never touches a
product that carries a photo it did not write itself, so a re-seed cannot undo the swap.

Once every product carries a real photograph and `SHOP_CATALOGUE_STATUS=live`, the
declarations above disappear on their own (`web/lib/geo.ts`), and the Merchant feed
question in `docs/GEO.md` opens up.
