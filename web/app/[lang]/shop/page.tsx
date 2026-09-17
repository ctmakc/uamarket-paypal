import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import JsonLd, { breadcrumbList, itemList } from "@/components/JsonLd";
import ProductTile, { spansFor } from "@/components/ProductTile";
import ActiveFilters from "@/components/shop/ActiveFilters";
import type { ActiveChip } from "@/components/shop/ActiveFilters";
import EmptyResult from "@/components/shop/EmptyResult";
import type { Suggestion } from "@/components/shop/EmptyResult";
import FilterDrawer from "@/components/shop/FilterDrawer";
import FilterRails, { bandLabel } from "@/components/shop/FilterRails";
import FilterRow from "@/components/shop/FilterRow";
import Pager from "@/components/shop/Pager";
import type { ShopQuery } from "@/components/shop/query";
import {
  DROP_ORDER,
  MAX_SCAN,
  countFor,
  indexable,
  originValue,
  pageOf,
  parsePrice,
  qs,
  readQuery,
  runQuery,
  viewPath,
} from "@/components/shop/query";
import { api, ApiDown } from "@/lib/api";
import type { Category, Collection, Maker } from "@/lib/api";
import Crumbs, { crumbNodes, trail } from "@/lib/crumbs";
import type { Lang } from "@/lib/i18n";
import { CATEGORY_ORDER, href, pick, t } from "@/lib/i18n";
import { shipPhrase, tp } from "@/lib/i18n.pages";
import { ts } from "@/lib/i18n.shop";
import { PROPOSED_SEO, proposedSeoOn } from "@/lib/i18n.seo";
import { NOINDEX_FOLLOW, buildMetadata, canonicalFor, urlFor } from "@/lib/seo";

/**
 * The shop list.
 *
 * Every filter and the page number are URL state (see components/shop/query.ts
 * for the parameter names and the rules), everything that changes the view is
 * a link, and the page is rendered on the server. Nothing here needs
 * JavaScript in the browser to work.
 */

/* ------------------------------------------------------------- the view */

/**
 * Everything the metadata and the page both need to name this view. The
 * catalogue calls are the cached ones from lib/api, so asking twice per
 * request costs one round trip.
 */
async function view(lang: Lang, current: ShopQuery) {
  const d = t(lang);
  const p = tp(lang);
  const s = ts(lang);
  const [collections, categories, makers, config] = await Promise.all([
    api.collections().catch(() => ({ items: [] as Collection[] })),
    api.categories().catch(() => ({ items: [] as Category[] })),
    api.makers().catch(() => ({ items: [] as Maker[] })),
    // A category description offered pickup on every deployment, including one
    // where the checkout answers a PICKUP order with "Pickup is not available".
    // The config is the cached call the rest of the storefront already makes.
    api.config().catch(() => null),
  ]);
  const activeCollection = collections.items.find((c) => c.slug === current.collection);
  const activeCategory = categories.items.find((c) => c.slug === current.category);
  const activeMaker = makers.items.find((m) => m.slug === current.maker);
  const activeOrigin = originValue(current.origin);
  const activeBand = parsePrice(current.price);

  const originLabel = activeOrigin ? d.origin[activeOrigin] : null;
  const priceLabel = activeBand ? bandLabel(activeBand, lang) : null;

  const title = current.q
    ? d.shop.searchFor(current.q)
    : activeCollection
      ? pick(lang, activeCollection.title, activeCollection.title_uk)
      : activeCategory
        ? pick(lang, activeCategory.title, activeCategory.title_uk)
        : activeMaker
          ? pick(lang, activeMaker.name, activeMaker.name_uk)
          : originLabel
            ? originLabel
            : priceLabel
              ? priceLabel
              : d.shop.title;

  const lede = activeCollection
    ? pick(lang, activeCollection.lede, activeCollection.lede_uk)
    : activeMaker
      ? pick(lang, activeMaker.craft, activeMaker.craft_uk)
      : null;

  // Written from the shop's own words: a collection says its lede, a maker its
  // craft, a category the plain sentence that is true of every category, an
  // origin level the mark it filters by.
  const description = current.q
    ? p.searchDescription(current.q)
    : activeCollection
      ? pick(lang, activeCollection.lede, activeCollection.lede_uk) || p.shopDescription
      : activeCategory
        ? p.categoryDescription(pick(lang, activeCategory.title, activeCategory.title_uk), shipPhrase(lang), config?.pickup.enabled === true)
        : activeMaker
          ? p.makerFilterDescription(pick(lang, activeMaker.name, activeMaker.name_uk))
          : originLabel
            ? s.originDescription(originLabel)
            : priceLabel
              ? s.priceDescription(priceLabel)
              : p.shopDescription;

  // The card charts the motif the tile for this collection or maker already charts.
  const seed = activeCollection
    ? `collection-${activeCollection.slug}`
    : activeMaker
      ? `maker-${activeMaker.slug}`
      : activeCategory
        ? activeCategory.slug
        : current.origin
          ? `origin-${current.origin}`
          : activeBand
            ? `price-${activeBand.id}`
            : "shop";

  // A category and a collection can share a name — "Kids" is both — so the two
  // pages carried one head title between them. The heading stays the plain name.
  const metaTitle = activeCategory ? s.categoryTitle(title) : title;

  const named = Boolean(current.q || activeCollection || activeCategory || activeMaker || originLabel || priceLabel);
  const crumbs = trail(
    lang,
    { name: d.shop.title, path: "/shop" },
    ...(named ? [{ name: title, path: viewPath({ ...current, page: undefined }) }] : []),
  );

  return {
    collections,
    categories,
    makers,
    activeCollection,
    activeCategory,
    activeMaker,
    originLabel,
    priceLabel,
    title,
    metaTitle,
    lede,
    description,
    seed,
    crumbs,
  };
}

/* --------------------------------------------------------------- metadata */

export async function generateMetadata({
  params,
  searchParams,
}: {
  params: Promise<{ lang: string }>;
  searchParams: Promise<ShopQuery>;
}): Promise<Metadata> {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  const current = readQuery(await searchParams);
  const page = pageOf(current);
  const [{ metaTitle, description, seed }, resolved] = await Promise.all([view(lang, current), runQuery(current, page)]);
  const s = ts(lang);
  // Page two of a listing is its own page, so it carries its own canonical URL
  // and a title that says which page it is.
  // The plain first page of the shop may carry the proposed search title (lib/i18n.seo.ts).
  const plain = !current.q && !current.collection && !current.category && !current.maker && !current.origin && !current.price && !current.in_stock && !current.sort;
  const baseTitle = plain && proposedSeoOn() ? PROPOSED_SEO[lang].shopTitle : metaTitle;
  const pageTitle = page > 1 && resolved.pageCount > 1 ? `${baseTitle} — ${s.pageOf(page, resolved.pageCount)}` : baseTitle;
  return buildMetadata({
    lang,
    path: viewPath(current),
    title: pageTitle,
    description,
    ogSeed: seed,
    robots: indexable(current, resolved.total > 0) ? undefined : NOINDEX_FOLLOW,
  });
}

/* ------------------------------------------------------------- empty state */

/**
 * The nearest wider views: this view with one filter taken off, most specific
 * filter first. Only views that really hold something are offered, so each
 * suggestion is checked against the catalogue before it is printed.
 */
async function widerViews(
  lang: Lang,
  base: string,
  current: ShopQuery,
  names: Awaited<ReturnType<typeof view>>,
): Promise<Suggestion[]> {
  const d = t(lang);
  const s = ts(lang);

  /** What a candidate view is called: its remaining facets, or the whole shop. */
  const nameOf = (q: ShopQuery): string => {
    const parts = [
      q.collection ? pick(lang, names.activeCollection?.title, names.activeCollection?.title_uk) : null,
      q.category ? pick(lang, names.activeCategory?.title, names.activeCategory?.title_uk) : null,
      q.maker ? pick(lang, names.activeMaker?.name, names.activeMaker?.name_uk) : null,
      q.origin ? names.originLabel : null,
      q.price ? names.priceLabel : null,
      q.q ? d.shop.searchFor(q.q) : null,
      q.in_stock ? d.shop.inStock : null,
    ].filter(Boolean);
    return parts.length ? parts.join(" · ") : s.everything;
  };

  const candidates: ShopQuery[] = [];
  for (const key of DROP_ORDER) {
    if (current[key]) candidates.push({ ...current, [key]: undefined, page: undefined });
  }
  // The plain shop, always worth offering as the last step out.
  if (candidates.length > 1) candidates.push({});

  // Two candidates that filter the same way are one suggestion, whatever sort
  // order they carry: "everything, cheapest first" and "everything" would read
  // as two lines saying the same thing.
  const keyOf = (q: ShopQuery) => viewPath({ ...q, sort: undefined, page: undefined });

  const out: Suggestion[] = [];
  for (const candidate of candidates) {
    if (out.length >= 3) break;
    const key = keyOf(candidate);
    if (out.some((x) => x.key === key)) continue;
    const count = await countFor(candidate);
    if (count > 0) out.push({ key, label: nameOf(candidate), href: `${base}${qs(candidate, {})}`, count });
  }
  return out;
}

/* ------------------------------------------------------------------ page */

export default async function Shop({
  params,
  searchParams,
}: {
  params: Promise<{ lang: string }>;
  searchParams: Promise<ShopQuery>;
}) {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  const d = t(lang);
  const s = ts(lang);
  const current = readQuery(await searchParams);
  const page = pageOf(current);
  const [resolved, meta] = await Promise.all([runQuery(current, page), view(lang, current)]);
  // An unreadable catalogue is not an empty one: the page answers "catching up" (lib/down.ts).
  if (resolved.failed) throw new ApiDown();

  // A page number past the end of the run is not a page of this shop.
  if (page > 1 && page > resolved.pageCount) notFound();
  // Neither is a collection or a category the catalogue has never heard of.
  // /shop?category=bogus used to answer 200 with an empty grid and a canonical
  // pointing at itself, so every garbage value minted another soft 404.
  if (current.category && meta.categories.items.length > 0 && !meta.activeCategory) notFound();
  if (current.collection && meta.collections.items.length > 0 && !meta.activeCollection) notFound();

  const { collections, categories, title, lede, crumbs } = meta;
  const base = href(lang, "/shop");
  const orderedCategories = [...categories.items].sort(
    (a, b) => CATEGORY_ORDER.indexOf(a.slug) - CATEGORY_ORDER.indexOf(b.slug),
  );
  const listUrl = canonicalFor(lang, viewPath(current));

  // Filters that have no rail of their own. Collection, category, origin,
  // price, sort and stock each carry their state on their own chip, and
  // clicking an active chip takes the filter off — printing those a second
  // time under "Filtering by" showed one filter twice in two visual
  // languages. A maker and a search term arrive from elsewhere, so they get
  // the only chip that can unpick them.
  const drop = (patch: Partial<ShopQuery>) => `${base}${qs(current, patch)}`;
  const chips: ActiveChip[] = [
    meta.activeMaker
      ? {
          key: "maker",
          label: `${d.shop.maker}: ${pick(lang, meta.activeMaker.name, meta.activeMaker.name_uk)}`,
          href: drop({ maker: undefined }),
        }
      : null,
    current.q ? { key: "q", label: d.shop.searchFor(current.q), href: drop({ q: undefined }) } : null,
  ].filter((c): c is ActiveChip => c !== null);
  // On a phone the rails are folded into the drawer, so every active filter needs its own
  // chip under the "Filter · Sort" button, sort included.
  const sortLabels: Record<string, string> = { price_asc: d.shop.sortPriceAsc, price_desc: d.shop.sortPriceDesc, newest: d.shop.sortNewest };
  const phoneChips: ActiveChip[] = [
    meta.activeCollection ? { key: "collection", label: pick(lang, meta.activeCollection.title, meta.activeCollection.title_uk), href: drop({ collection: undefined }) } : null,
    meta.activeCategory ? { key: "category", label: pick(lang, meta.activeCategory.title, meta.activeCategory.title_uk), href: drop({ category: undefined }) } : null,
    meta.originLabel ? { key: "origin", label: meta.originLabel, href: drop({ origin: undefined }) } : null,
    meta.priceLabel ? { key: "price", label: meta.priceLabel, href: drop({ price: undefined }) } : null,
    current.in_stock ? { key: "in_stock", label: d.shop.inStock, href: drop({ in_stock: undefined }) } : null,
    current.sort && sortLabels[current.sort] ? { key: "sort", label: sortLabels[current.sort], href: drop({ sort: undefined }) } : null,
    ...chips,
  ].filter((c): c is ActiveChip => c !== null);
  const anyFilter = Boolean(
    current.collection || current.category || current.maker || current.origin || current.price || current.q || current.in_stock,
  );
  // A collection holds the same number of pieces whatever else is filtered, so
  // its chip count and the header's own count of this view disagree the moment
  // a second filter is on. The count is printed only where it is the whole
  // truth about the view it opens.
  const showCounts = !current.category && !current.origin && !current.price && !current.q && !current.in_stock;

  const suggestions = resolved.total === 0 && !resolved.failed ? await widerViews(lang, base, current, meta) : [];
  const tileSpans = spansFor(resolved.items.length);

  return (
    <>
      <JsonLd
        id="ld-shop"
        data={[
          breadcrumbList(crumbNodes(lang, crumbs)),
          itemList({
            url: listUrl,
            name: title,
            items: resolved.items.map((p) => ({
              url: urlFor(lang, `/product/${p.slug}`),
              name: pick(lang, p.title, p.title_uk),
            })),
          }),
        ]}
      />
      <section className="canvas band">
        <Crumbs lang={lang} items={crumbs} style={{ marginBottom: "calc(var(--st) * 2)" }} />
        <div className="row-line" style={{ marginBottom: "calc(var(--st) * 2)", borderTop: "1px dashed var(--count-major)" }}>
          <div>
            <h1 className="h1">{title}</h1>
            {lede ? <p className="muted measure">{lede}</p> : null}
          </div>
          <span className="mono mono--sm muted">
            {d.shop.results(resolved.total)}
            {resolved.pageCount > 1 ? ` · ${s.showing(resolved.from, resolved.to)}` : ""}
          </span>
        </div>

        {/* ------------------------------------------------------------------
            The filter stack: five rails, one chip, one label column, one left
            edge. Collection and category used to be a scrolling pill rail and
            a row of underlined links while origin, price and sort each had a
            third treatment; a shopper read four control systems on one page. */}
        <Suspense fallback={null}>
        <FilterDrawer lang={lang} chips={phoneChips} clearHref={base} total={resolved.total}>
        <div aria-label={s.filterRegion} role="group">
          <FilterRow id="filter-collection" label={d.shop.collection}>
            <Link
              href={`${base}${qs(current, { collection: undefined, category: undefined, q: undefined })}`}
              className="chip"
              aria-current={!current.collection && !current.category && !current.q ? "true" : undefined}
            >
              {d.shop.all}
            </Link>
            {collections.items.map((c) => (
              <Link
                key={c.slug}
                href={`${base}${qs(current, { collection: current.collection === c.slug ? undefined : c.slug, category: undefined, q: undefined })}`}
                className="chip"
                aria-current={current.collection === c.slug ? "true" : undefined}
              >
                {pick(lang, c.title, c.title_uk)}
                {showCounts ? (
                  <span className="mono mono--sm" style={{ opacity: 0.7 }}>
                    {c.count}
                  </span>
                ) : null}
              </Link>
            ))}
          </FilterRow>

          <FilterRow id="filter-category" label={d.shop.category}>
            {orderedCategories.map((c) => (
              <Link
                key={c.slug}
                href={`${base}${qs(current, { category: current.category === c.slug ? undefined : c.slug, q: undefined })}`}
                className="chip"
                aria-current={current.category === c.slug ? "true" : undefined}
              >
                {pick(lang, c.title, c.title_uk)}
              </Link>
            ))}
          </FilterRow>

          {/* provenance and price: the two rails the catalogue API cannot filter by */}
          <FilterRails lang={lang} base={base} current={current} />

          <FilterRow id="filter-sort" label={d.shop.sort}>
            {([
              ["position", d.shop.sortPosition],
              ["price_asc", d.shop.sortPriceAsc],
              ["price_desc", d.shop.sortPriceDesc],
              ["newest", d.shop.sortNewest],
            ] as [string, string][]).map(([k, label]) => (
              <Link
                key={k}
                href={`${base}${qs(current, { sort: k === "position" ? undefined : k })}`}
                className="chip"
                aria-current={(current.sort || "position") === k ? "true" : undefined}
              >
                {label}
              </Link>
            ))}
          </FilterRow>

          <FilterRow id="filter-stock" label={s.stock}>
            <Link
              href={`${base}${qs(current, { in_stock: current.in_stock ? undefined : "1" })}`}
              className="chip"
              aria-current={current.in_stock ? "true" : undefined}
            >
              {d.shop.inStock}
            </Link>
          </FilterRow>
        </div>
        </FilterDrawer>
        </Suspense>

        <div className="fdesk">
          <ActiveFilters lang={lang} chips={chips} clearHref={base} anyFilter={anyFilter} />
        </div>

        {resolved.truncated ? (
          <p className="notice" style={{ marginTop: "calc(var(--st) * 2)" }}>
            {s.scanNote(MAX_SCAN)}
          </p>
        ) : null}

        <div style={{ marginTop: "calc(var(--st) * 3)" }}>
          {resolved.failed ? (
            <p className="notice">{s.apiDown}</p>
          ) : resolved.items.length === 0 ? (
            <EmptyResult
              lang={lang}
              suggestions={suggestions}
              shelf={current.q && resolved.suggestion ? {
                label: pick(lang, resolved.suggestion.title, resolved.suggestion.title_uk),
                href: `${base}?category=${encodeURIComponent(resolved.suggestion.category)}`,
              } : null}
            />
          ) : (
            <div className="blocks blocks--pairs">
              {resolved.items.map((p, i) => (
                <ProductTile key={p.slug} p={p} lang={lang} span={tileSpans[i]} eager={i < 2} />
              ))}
            </div>
          )}
        </div>

        <Pager
          lang={lang}
          page={page}
          pageCount={resolved.pageCount}
          hrefFor={(n) => `${base}${qs(current, { page: n > 1 ? String(n) : undefined })}`}
        />
      </section>
    </>
  );
}
