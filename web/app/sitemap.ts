import type { MetadataRoute } from "next";
import { ORIGINS } from "@/components/shop/query";
import { api } from "@/lib/api";
import type { Category, Collection, Maker, ProductSummary } from "@/lib/api";
import { isIndexable, urlFor } from "@/lib/seo";

// The catalogue is read per request, so a new product is in the sitemap as soon
// as it is in the shop.
export const dynamic = "force-dynamic";

/**
 * Every indexable route, in both languages, each entry carrying the full
 * hreflang set (en, uk, x-default → the English URL).
 *
 * /bag, /checkout and /order stay out: they hold one shopper's own state.
 * lastModified, changeFrequency and priority stay out as well — the catalogue
 * API records no update timestamps, and a made-up date is worse than a missing
 * one. Add lastModified here once the API exposes updated_at.
 */
const STATIC_PATHS = [
  "/",
  "/shop",
  "/makers",
  "/about",
  // Content pages that live alongside the catalogue.
  "/faq",
  "/shipping",
  "/care",
  "/privacy",
  "/terms",
];

const PAGE_SIZE = 120; // the catalogue API's maximum
const MAX_PRODUCTS = 5000; // guard against an unbounded catalogue

async function allProducts(): Promise<ProductSummary[]> {
  const out: ProductSummary[] = [];
  let offset = 0;
  for (;;) {
    const page = await api.products({ limit: PAGE_SIZE, offset, sort: "position" });
    out.push(...page.items);
    offset += page.items.length;
    if (page.items.length < PAGE_SIZE || offset >= Math.min(page.total, MAX_PRODUCTS)) break;
  }
  return out;
}

function entry(path: string): MetadataRoute.Sitemap[number][] {
  const en = urlFor("en", path);
  const uk = urlFor("uk", path);
  const languages = { en, uk, "x-default": en };
  return [
    { url: en, alternates: { languages } },
    { url: uk, alternates: { languages } },
  ];
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // A deployment whose robots.txt reads "Disallow: /" has nothing to declare.
  // The file used to list all 98 URLs on a preview that forbids all crawling.
  if (!isIndexable()) return [];

  const [collections, categories, makers, products] = await Promise.all([
    api.collections().catch(() => ({ items: [] as Collection[] })),
    api.categories().catch(() => ({ items: [] as Category[] })),
    api.makers().catch(() => ({ items: [] as Maker[] })),
    allProducts().catch(() => [] as ProductSummary[]),
  ]);

  const paths = [
    ...STATIC_PATHS,
    // Filtered listings worth indexing: one page per collection, one per
    // category and one per provenance level. Those are the three rails
    // components/shop/query.ts `indexable` lets into the index, and the
    // sitemap used to declare only two of them — so six crawlable, indexable
    // origin views existed that the shop never told anyone about.
    // Free-text search (/shop?q=), price bands, sort orders and the stock
    // toggle stay out; those pages are noindex, follow and robots.txt keeps a
    // crawler out of the combinations they multiply into.
    ...collections.items.map((c) => `/shop?collection=${encodeURIComponent(c.slug)}`),
    ...categories.items.map((c) => `/shop?category=${encodeURIComponent(c.slug)}`),
    ...ORIGINS.map((o) => `/shop?origin=${encodeURIComponent(o.id)}`),
    ...makers.items.map((m) => `/makers/${encodeURIComponent(m.slug)}`),
    ...products.map((p) => `/product/${encodeURIComponent(p.slug)}`),
  ];

  const seen = new Set<string>();
  const unique = paths.filter((p) => (seen.has(p) ? false : (seen.add(p), true)));
  return unique.flatMap(entry);
}
