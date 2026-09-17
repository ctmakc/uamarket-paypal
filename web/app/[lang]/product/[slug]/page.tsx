import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import JsonLd, { breadcrumbList, product as productNode } from "@/components/JsonLd";
import Gallery from "@/components/Gallery";
import type { GalleryPhoto } from "@/components/Gallery";
import Motif from "@/components/Motif";
import SelectedSku from "@/components/SelectedSku";
import ProductTile from "@/components/ProductTile";
import ProvenanceNote from "@/components/ProvenanceNote";
import PurchasePanel from "@/components/PurchasePanel";
import SizeGuide, { sizeGuideKeys, sizesOffered } from "@/components/SizeGuide";
import StitchMark from "@/components/StitchMark";
import { api, ApiDown, ApiError, isApiDown } from "@/lib/api";
import type { Maker, Product, ProductSummary } from "@/lib/api";
import Crumbs, { crumbNodes, trail } from "@/lib/crumbs";
import { catalogueStatus } from "@/lib/geo";
import type { Lang } from "@/lib/i18n";
import { href, pick, t } from "@/lib/i18n";
import { tb } from "@/lib/i18n.buy";
import { productDescription } from "@/lib/i18n.pages";
import { DIMENSION_KEYS, attributeLabel, dimensionUnit, tpd } from "@/lib/i18n.product";
import { buildMetadata, canonicalFor, siteUrl } from "@/lib/seo";

const SIZE_GUIDE_ID = "size-guide";
const PROVENANCE_ID = "provenance";

/* The buy column follows the page down beside a tall gallery. It is switched on
   only where it has both a neighbour to travel beside (two columns, from
   1024px) and a screen deep enough to hold it whole (820px); anywhere else it
   is an ordinary block and so can cover nothing. The max-height is the backstop
   for a piece with more options than these: rather than hide its own add-to-bag
   button below the fold, the panel caps at the viewport and scrolls inside
   itself. The 4px of padding, undone by the same margin, keeps the focus ring
   clear of that scroll edge. */
const CSS = `
.pd-buy { align-self: start; }
@media (min-width: 1024px) and (min-height: 820px) {
  .pd-buy {
    position: sticky;
    top: calc(var(--st) * 7);
    max-height: calc(100dvh - var(--st) * 8);
    overflow-y: auto;
    overscroll-behavior: contain;
    padding: 4px;
    margin: -4px;
  }
}
`;

/** The collection's own name, or its slug while the catalogue call is down. */
async function collectionName(lang: Lang, slug: string): Promise<string> {
  const collections = await api.collections().catch(() => ({ items: [] }));
  const found = collections.items.find((c) => c.slug === slug);
  return found ? pick(lang, found.title, found.title_uk) : slug;
}

function crumbsFor(lang: Lang, p: Product, collection: string) {
  return trail(
    lang,
    { name: t(lang).shop.title, path: "/shop" },
    { name: collection, path: `/shop?collection=${p.collection}` },
    { name: pick(lang, p.title, p.title_uk), path: `/product/${p.slug}` },
  );
}

/** Catalogue images can be relative; structured data needs absolute URLs. */
function absolute(url: string): string {
  return /^https?:\/\//i.test(url) ? url : `${siteUrl()}${url.startsWith("/") ? "" : "/"}${url}`;
}

type Band = { key: string; heading: string; link: { path: string; label: string } | null; items: ProductSummary[] };

/**
 * Tile widths for a band: the 4/3/5 chart rhythm when the band is full, a
 * halved row for two pieces, and half a row for one. ProductTile's span prop
 * stops at six blocks, so a lone piece takes half the band rather than all of
 * it; the band's header row carries the workshop link, so the row still reads
 * as finished.
 */
function bandSpans(n: number): (3 | 4 | 5 | 6)[] {
  if (n >= 3) return [4, 3, 5];
  if (n === 2) return [6, 6];
  return [6];
}

/**
 * What to show after the piece.
 *
 * The catalogue's own `related` is the maker's other work, which is the right
 * first answer and an empty one for a workshop that has sent us a single piece.
 * So the row is topped up from the collection this piece sits in, under its own
 * heading — a heading that says where the pieces came from, rather than one row
 * quietly mixing a workshop's work with strangers'. Three tiles fill one chart
 * band exactly (4/3/5 blocks), so each band is capped at three.
 */
async function bands(lang: Lang, p: Product, collection: string): Promise<Band[]> {
  const d = t(lang);
  const out: Band[] = [];
  const seen = new Set<string>([p.slug]);
  const first = p.related.filter((r) => !seen.has(r.slug)).slice(0, 3);
  first.forEach((r) => seen.add(r.slug));
  if (first.length) {
    out.push({
      key: "related",
      heading: p.maker ? d.product.related : d.product.relatedCategory,
      link: p.maker
        // The link is a maker's name too, so it carries the same short word a tile does.
        ? { path: `/makers/${p.maker.slug}`, label: `${pick(lang, p.maker.name, p.maker.name_uk)}${catalogueStatus() === "placeholder" ? ` (${d.makers.exampleShort})` : ""}` }
        : { path: `/shop?category=${p.category}`, label: d.home.seeAll },
      items: first,
    });
  }
  if (first.length >= 3) return out;
  const more = await api.products({ collection: p.collection, limit: 12 }).catch(() => ({ items: [] as ProductSummary[] }));
  const fill = more.items.filter((r) => !seen.has(r.slug)).slice(0, 3);
  if (fill.length) {
    out.push({
      key: "collection",
      heading: tpd(lang).related.inCollection(collection),
      link: { path: `/shop?collection=${p.collection}`, label: d.home.seeAll },
      items: fill,
    });
  }
  return out;
}

/**
 * The specification list: what the catalogue holds about the object itself,
 * after the provenance block has taken the origin lines and the size guide has
 * taken the cut and the size chart. An attribute we have no label for is still
 * printed, with its key humanised, so nothing a workshop sends disappears.
 */
function specRows(lang: Lang, p: Product): [string, string][] {
  const d = t(lang);
  const rows: [string, string][] = [];
  if (p.material) rows.push([d.product.material, pick(lang, p.material, p.material_uk)]);
  if (p.care) rows.push([d.product.care, pick(lang, p.care, p.care_uk)]);
  const used = sizeGuideKeys(p);
  for (const key of DIMENSION_KEYS) {
    const v = p.attributes[key];
    if (v === undefined) continue;
    used.add(key);
    rows.push([attributeLabel(lang, key), `${v} ${dimensionUnit(key, lang)}`.trim()]);
  }
  for (const [key, value] of Object.entries(p.attributes)) {
    if (used.has(key) || key.endsWith("_uk")) continue;
    const twin = p.attributes[`${key}_uk`];
    rows.push([attributeLabel(lang, key), pick(lang, String(value), twin === undefined ? null : String(twin))]);
  }
  return rows;
}

export async function generateMetadata({ params }: { params: Promise<{ lang: string; slug: string }> }): Promise<Metadata> {
  const { lang: raw, slug } = await params;
  const lang = raw as Lang;
  let p: Product;
  try {
    p = await api.product(slug);
  } catch {
    // A slug that is not in the catalogue renders the 404 page; give it the
    // brand and nothing that claims a product exists here.
    return { title: t(lang).brand };
  }
  const images = (p.image_url ? [p.image_url, ...p.images.filter((i) => i !== p.image_url)] : p.images).map(absolute);
  return buildMetadata({
    lang,
    path: `/product/${p.slug}`,
    title: pick(lang, p.title, p.title_uk),
    description: productDescription(lang, p),
    // The photo when there is one; otherwise the card charts the same motif the
    // product tile draws from this slug.
    image: images[0],
    ogSeed: p.slug,
  });
}

export default async function ProductPage({ params }: { params: Promise<{ lang: string; slug: string }> }) {
  const { lang: raw, slug } = await params;
  const lang = raw as Lang;
  const d = t(lang);
  const td = tpd(lang);
  let p;
  try {
    p = await api.product(slug);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    // Anything else means the catalogue could not be read, which is not "no such piece".
    throw isApiDown(e) ? new ApiDown() : e;
  }
  const [collection, config, maker] = await Promise.all([
    collectionName(lang, p.collection),
    api.config().catch(() => null),
    // The workshop's craft and founding year live on the maker record, and the
    // provenance block states them; a failed call simply drops those two lines.
    p.maker ? api.maker(p.maker.slug).catch(() => null) : Promise.resolve<Maker | null>(null),
  ]);
  const title = pick(lang, p.title, p.title_uk);
  const subtitle = pick(lang, p.subtitle, p.subtitle_uk);
  const images = p.image_url ? [p.image_url, ...p.images.filter((i) => i !== p.image_url)] : p.images;
  // Uploaded photos carry their size, their resized copies and alt text in both languages;
  // a legacy image URL carries only itself.
  const photos: GalleryPhoto[] = p.photos && p.photos.length
    ? p.photos.map((ph) => ({ src: ph.src, srcset: ph.srcset, width: ph.width, height: ph.height, alt: pick(lang, ph.alt, ph.alt_uk) }))
    : images.map((src) => ({ src, alt: "" }));
  const crumbs = crumbsFor(lang, p, collection);
  const url = canonicalFor(lang, `/product/${p.slug}`);
  const keyLine = [pick(lang, p.technique, p.technique_uk), pick(lang, p.material, p.material_uk), p.maker ? pick(lang, p.maker.region, p.maker.region_uk) : null].filter(Boolean);
  const hasSizes = sizesOffered(p).length > 0;
  const spec = specRows(lang, p);
  const rows = await bands(lang, p, collection);

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      {/* The offer, the workshop as the brand, and availability straight from
          the catalogue. Shipping comes from the storefront config, so a rate
          the shop has not set is left out rather than guessed. */}
      <JsonLd
        id="ld-product"
        data={[
          productNode({
            lang,
            product: p,
            url,
            images: images.map(absolute),
            description: pick(lang, p.description, p.description_uk),
            shipping: config?.shipping ?? null,
          }),
          breadcrumbList(crumbNodes(lang, crumbs)),
        ]}
      />
      <section className="canvas band">
        <Crumbs lang={lang} items={crumbs} style={{ marginBottom: "calc(var(--st) * 2)" }} />
        <div className="split">
          <div className="split__a">
            {photos.length ? (
              <Gallery lang={lang} photos={photos} title={title} />
            ) : (
              <div className="gallery">
                <div className="gallery__main chart" style={{ padding: "var(--st)", aspectRatio: "1 / 1" }}>
                  <Motif seed={p.slug} mode="complete" size={24} title={d.product.photoPending} />
                </div>
                <p className="mono mono--sm muted">{d.product.photoPending}</p>
              </div>
            )}
          </div>
          <div className="split__b">
            <div className="pd-buy stack">
              <div className="stack--tight">
                <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "var(--st) calc(var(--st) * 2)" }}>
                  <span className="status" style={{ color: "var(--ink)" }}>
                    <StitchMark origin={p.origin} lang={lang} />
                    <span className="mono mono--sm">{pick(lang, p.origin_label, p.origin_label_uk)}</span>
                  </span>
                  {/* A native anchor: <Link href="#…"> is a no-op on the current URL. */}
                  <a href={`#${PROVENANCE_ID}`} className="thread-link mono mono--sm">{td.provenance.link} ↓</a>
                </div>
                <h1 className="h1 h1--lead">{title}</h1>
                {subtitle ? <p className="muted">{subtitle}</p> : null}
                {keyLine.length ? (
                  <p className="key">
                    {keyLine.map((k, i) => <span key={i}>{k}</span>)}
                  </p>
                ) : null}
              </div>
              {/* The workshop is not repeated here: the provenance block below
                  carries its name, its craft and the link, and the key line
                  above already names the region. */}
              <PurchasePanel product={p} lang={lang} sizeGuideId={hasSizes ? SIZE_GUIDE_ID : undefined} />
            </div>
          </div>
        </div>
      </section>

      <section className="canvas band" id="details">
        <div className="split">
          <div className="split__a stack--loose">
            <div className="stack">
              <h2 className="h3">{td.description}</h2>
              <div className="prose measure">
                {pick(lang, p.description, p.description_uk).split(/\n\n+/).map((para, i) => <p key={i}>{para}</p>)}
              </div>
            </div>
            {hasSizes ? <SizeGuide lang={lang} product={p} contactEmail={config?.contact_email ?? null} id={SIZE_GUIDE_ID} /> : null}
          </div>
          <div className="split__b stack--loose">
            <ProvenanceNote lang={lang} product={p} maker={maker} id={PROVENANCE_ID} />
            <section className="stack" aria-labelledby="spec-h">
              <h2 className="h3" id="spec-h">{td.spec}</h2>
              <dl>
                {spec.map(([k, v]) => (
                  <div key={k} className="row-line" style={{ gridTemplateColumns: "minmax(110px, 1fr) 2fr" }}>
                    <dt className="mono mono--sm muted">{k}</dt>
                    <dd style={{ margin: 0, fontSize: "var(--fs-ui)", lineHeight: "24px" }}>{v}</dd>
                  </div>
                ))}
                {/* The SKU of the choice in the buy panel: a code for a question by email,
                    kept down here beside the other facts rather than next to the price. */}
                <div className="row-line" style={{ gridTemplateColumns: "minmax(110px, 1fr) 2fr" }}>
                  <dt className="mono mono--sm muted">{tb(lang).sku}</dt>
                  <dd style={{ margin: 0, fontSize: "var(--fs-ui)", lineHeight: "24px" }}>
                    <SelectedSku initial={(p.variants.find((v) => v.availability.in_stock) || p.variants[0])?.sku ?? null} />
                  </dd>
                </div>
              </dl>
            </section>
          </div>
        </div>
      </section>

      {rows.map((band) => (
        <section className="canvas band" key={band.key}>
          <div className="row-line" style={{ marginBottom: "calc(var(--st) * 3)" }}>
            <h2 className="h2">{band.heading}</h2>
            {band.link ? (
              <Link href={href(lang, band.link.path)} className="thread-link ui">{band.link.label} →</Link>
            ) : null}
          </div>
          <div className="blocks blocks--pairs">
            {band.items.map((r, i) => (
              <ProductTile key={r.slug} p={r} lang={lang} span={bandSpans(band.items.length)[i]} short />
            ))}
          </div>
        </section>
      ))}
    </>
  );
}
