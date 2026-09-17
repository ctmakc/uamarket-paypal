/**
 * The shop's query model: what a shop URL is allowed to say, how it is read,
 * how it is written back, and how one page of results is fetched.
 *
 * URL state is the whole state. Every filter and the page number live in the
 * query string, so a filtered view can be shared, bookmarked, crawled and
 * rendered on the server with no JavaScript in the browser.
 *
 * Parameter names already in use elsewhere keep their spelling exactly:
 * `collection`, `category`, `maker`, `q`, `in_stock=1`, `sort`. The links in
 * app/sitemap.ts, components/SiteFooter.tsx, app/[lang]/page.tsx and
 * lib/geo.ts all point at those and keep working. Two names are new — `origin`
 * and `price` — plus `page`.
 *
 * The catalogue API (GET /v1/catalog/products) filters by category,
 * collection, maker, free text and stock, and pages with limit/offset. It has
 * no origin filter and no price filter, so those two are applied here, over
 * the API's own result set. See MAX_SCAN below and the note in
 * docs/OWNER-ACTIONS.md.
 */
import { api } from "@/lib/api";
import type { ProductSummary } from "@/lib/api";

/* ------------------------------------------------------------------ shape */

/** Every parameter this page understands, as it appears in the URL. */
export type ShopQuery = {
  collection?: string;
  category?: string;
  maker?: string;
  /** One of ORIGIN_IDS. */
  origin?: string;
  /** A band written "min-max"; either side may be empty ("-50", "250-"). */
  price?: string;
  q?: string;
  /** "1" or absent. */
  in_stock?: string;
  sort?: string;
  /** "2" and up. Page one is written as no parameter at all. */
  page?: string;
};

export type OriginValue = "HANDMADE_UA" | "MADE_UA" | "DESIGNED_UA";

/**
 * Provenance is the shop's own differentiator, so it is a first-class filter
 * with a readable URL word for each of the three levels the catalogue records.
 */
export const ORIGINS: { id: string; value: OriginValue }[] = [
  { id: "handmade", value: "HANDMADE_UA" },
  { id: "made", value: "MADE_UA" },
  { id: "designed", value: "DESIGNED_UA" },
];

const ORIGIN_BY_ID = new Map(ORIGINS.map((o) => [o.id, o.value]));

export function originValue(id: string | undefined): OriginValue | null {
  return (id && ORIGIN_BY_ID.get(id)) || null;
}

const SORTS = ["price_asc", "price_desc", "newest"];

/**
 * Twelve tiles: the tile rhythm is 4/3/5 then 5/4/3 (see spanFor in
 * components/ProductTile.tsx), so a page holds two complete chart bands on
 * desktop and six rows of two on a phone. Every page ends on a finished band.
 */
export const PAGE_SIZE = 12;

/** The catalogue API's own maximum for one request. */
const API_MAX = 120;

/**
 * How deep the origin and price filters read when the API cannot apply them.
 * Ten requests of 120. A catalogue larger than this needs those two filters in
 * the API itself; until then the page says out loud that it read the first
 * MAX_SCAN products of the view rather than quietly reporting a wrong count.
 */
export const MAX_SCAN = 1200;

/* ------------------------------------------------------------------ price */

export type PriceBand = {
  /** URL value, e.g. "-50", "50-120", "250-". */
  id: string;
  /** Inclusive lower bound in CAD, null for "no lower bound". */
  min: number | null;
  /** Exclusive upper bound in CAD, null for "no upper bound". */
  max: number | null;
};

/** The default break points, used when SHOP_PRICE_BANDS_CAD is unset. */
export const PRICE_BAND_DEFAULT = "50,120,250";

function bandId(min: number | null, max: number | null): string {
  return `${min ?? ""}-${max ?? ""}`;
}

/**
 * Price bands are a merchandising decision, so they are configuration with a
 * documented default: SHOP_PRICE_BANDS_CAD is an ascending, comma-separated
 * list of break points in CAD. "50,120,250" makes four bands — under 50,
 * 50 to 120, 120 to 250, 250 and up.
 */
export function priceBands(): PriceBand[] {
  const raw = (process.env.SHOP_PRICE_BANDS_CAD || PRICE_BAND_DEFAULT).trim();
  const points = raw
    .split(",")
    .map((p) => Number(p.trim()))
    .filter((n) => Number.isFinite(n) && n > 0);
  const sorted = [...new Set(points)].sort((a, b) => a - b);
  if (sorted.length === 0) return [];
  const bands: PriceBand[] = [{ id: bandId(null, sorted[0]), min: null, max: sorted[0] }];
  for (let i = 0; i < sorted.length - 1; i += 1) {
    bands.push({ id: bandId(sorted[i], sorted[i + 1]), min: sorted[i], max: sorted[i + 1] });
  }
  const last = sorted[sorted.length - 1];
  bands.push({ id: bandId(last, null), min: last, max: null });
  return bands;
}

/**
 * Read a price band out of the URL. Any "min-max" pair is accepted, not only
 * the configured ones, so an old shared link keeps working after the bands are
 * re-cut.
 */
export function parsePrice(raw: string | undefined): PriceBand | null {
  if (!raw) return null;
  const m = /^(\d{0,7})-(\d{0,7})$/.exec(raw.trim());
  if (!m) return null;
  const min = m[1] === "" ? null : Number(m[1]);
  const max = m[2] === "" ? null : Number(m[2]);
  if (min === null && max === null) return null;
  if (min !== null && max !== null && max <= min) return null;
  return { id: bandId(min, max), min, max };
}

/**
 * A product's price band is decided by the number the tile prints — the
 * lowest price of its variants. The filter matches what the shopper sees.
 */
function inBand(p: ProductSummary, band: PriceBand): boolean {
  const price = p.price_from_cad;
  if (band.min !== null && price < band.min) return false;
  if (band.max !== null && price >= band.max) return false;
  return true;
}

/* ------------------------------------------------------------------ read */

/** The filters this page understands, read once from the query string. */
export function readQuery(sp: ShopQuery): ShopQuery {
  const price = parsePrice(sp.price);
  const page = Number(sp.page);
  return {
    collection: sp.collection || undefined,
    category: sp.category || undefined,
    maker: sp.maker || undefined,
    origin: originValue(sp.origin) ? sp.origin : undefined,
    price: price ? price.id : undefined,
    q: (sp.q || "").trim().slice(0, 80) || undefined,
    in_stock: sp.in_stock === "1" ? "1" : undefined,
    sort: SORTS.includes(sp.sort || "") ? sp.sort : undefined,
    page: Number.isInteger(page) && page > 1 ? String(page) : undefined,
  };
}

/** The page number this URL asks for, one-based. */
export function pageOf(current: ShopQuery): number {
  const n = Number(current.page);
  return Number.isInteger(n) && n > 1 ? n : 1;
}

/**
 * The filters, narrowest first. A view that matches nothing is widened by
 * dropping them in this order: a price band cuts hardest, a collection least,
 * so the first one dropped is the one most likely to be the reason nothing
 * matched. The empty state walks this list.
 */
export const DROP_ORDER = ["price", "origin", "in_stock", "q", "maker", "category", "collection"] as const;

/* ------------------------------------------------------------------ write */

/** Parameter order in every URL this page writes, so one view has one address. */
const ORDER = ["collection", "category", "maker", "origin", "price", "q", "in_stock", "sort", "page"] as const;

function serialise(current: ShopQuery): string {
  const p = new URLSearchParams();
  for (const key of ORDER) {
    const value = current[key];
    if (value) p.set(key, value);
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

/**
 * The locale-free address of this view. Fixed parameter order, so the same set
 * of filters has the same canonical URL whatever order they were clicked in.
 */
export function viewPath(current: ShopQuery): string {
  return `/shop${serialise(current)}`;
}

/**
 * The query string for this view with one change applied. Changing a filter
 * returns to page one, because page four of the old view says nothing about
 * the new one; pass `page` in the patch to move within a view.
 */
export function qs(base: ShopQuery, patch: Partial<ShopQuery>): string {
  const merged: ShopQuery = { ...base, ...patch };
  if (!("page" in patch)) merged.page = undefined;
  if (merged.page === "1") merged.page = undefined;
  return serialise(merged);
}

/** Locale-free paths of the pages either side of this one, for rel=prev/next. */
export function paginationPaths(
  current: ShopQuery,
  page: number,
  pageCount: number,
): { prev: string | null; next: string | null } {
  const at = (n: number) => `/shop${qs(current, { page: n > 1 ? String(n) : undefined })}`;
  return {
    prev: page > 1 ? at(page - 1) : null,
    next: page < pageCount ? at(page + 1) : null,
  };
}

/* ------------------------------------------------------------------ robots */

/**
 * What may enter the index.
 *
 * One collection, one category or one origin level is a listing a person could
 * reasonably search for, and each is a stable page of the shop. Everything else
 * stays crawlable and out of the index: a free-text search, a stock toggle, a
 * sort order, a maker (whose own page at /makers/<slug> carries the same
 * pieces), a price band (an arbitrary slice of the same goods) and any two
 * facets at once — those multiply into pages that say the same thing.
 *
 * A view with nothing in it is never indexable, whatever its filters, and that
 * includes a collection or category that has gone empty.
 */
export function indexable(current: ShopQuery, hasResults: boolean): boolean {
  if (!hasResults) return false;
  if (current.q || current.in_stock || current.sort || current.maker || current.price) return false;
  const facets = [current.collection, current.category, current.origin].filter(Boolean).length;
  return facets <= 1;
}

/* ------------------------------------------------------------------ fetch */

export type Resolved = {
  items: ProductSummary[];
  /** Products matching this view, across all its pages. */
  total: number;
  page: number;
  pageCount: number;
  /** One-based position of the first and last tile on this page. */
  from: number;
  to: number;
  /** True when origin/price were applied to the first MAX_SCAN products only. */
  truncated: boolean;
  /** True when the catalogue API could not be read. */
  failed: boolean;
  /** For a search that found nothing: the category whose name is closest to the words. */
  suggestion?: { category: string; title: string; title_uk: string } | null;
};

function apiQuery(current: ShopQuery) {
  return {
    category: current.category,
    collection: current.collection,
    maker: current.maker,
    q: current.q,
    in_stock: current.in_stock ? true : undefined,
    sort: current.sort || "position",
  };
}

const EMPTY: Resolved = { items: [], total: 0, page: 1, pageCount: 0, from: 0, to: 0, truncated: false, failed: true };

/**
 * One page of the shop.
 *
 * When every active filter is one the API understands, the API pages the
 * result and this makes a single request whatever the catalogue's size. When
 * origin or price is active, the view is read in chunks of API_MAX up to
 * MAX_SCAN and filtered here.
 */
export async function runQuery(current: ShopQuery, page: number = pageOf(current)): Promise<Resolved> {
  const origin = originValue(current.origin);
  const band = parsePrice(current.price);
  const query = apiQuery(current);

  try {
    if (!origin && !band) {
      const res = await api.products({ ...query, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE });
      return { ...frame(res.items, res.total, page, false), suggestion: res.suggestion ?? null };
    }

    const scanned: ProductSummary[] = [];
    let total = 0;
    for (;;) {
      const res = await api.products({ ...query, limit: API_MAX, offset: scanned.length });
      total = res.total;
      scanned.push(...res.items);
      if (res.items.length < API_MAX || scanned.length >= Math.min(total, MAX_SCAN)) break;
    }
    const matched = scanned.filter(
      (p) => (!origin || p.origin === origin) && (!band || inBand(p, band)),
    );
    const start = (page - 1) * PAGE_SIZE;
    return frame(matched.slice(start, start + PAGE_SIZE), matched.length, page, total > scanned.length);
  } catch {
    return { ...EMPTY, page };
  }
}

function frame(items: ProductSummary[], total: number, page: number, truncated: boolean): Resolved {
  const pageCount = Math.ceil(total / PAGE_SIZE);
  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  return { items, total, page, pageCount, from, to: from === 0 ? 0 : from + items.length - 1, truncated, failed: false };
}

/** How many products a candidate view would show. Used by the empty state. */
export async function countFor(current: ShopQuery): Promise<number> {
  const resolved = await runQuery(current, 1);
  return resolved.failed ? 0 : resolved.total;
}
