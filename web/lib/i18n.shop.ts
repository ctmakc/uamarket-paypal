/**
 * Strings for browsing the shop: the filter rails, the active-filter chips,
 * the result line, the pager and the empty state.
 *
 * `web/lib/i18n.ts` belongs to the orchestrator, so everything this pass needed
 * to say lives here. Every entry exists in English and in Ukrainian. Labels
 * that already exist in the shared dictionary — the three origin levels, the
 * sort names, "In stock only", "Clear" — are read from there and never
 * duplicated here.
 *
 * Nothing here states a fact about the shop: no delivery time, no policy, no
 * claim about the assortment. The only numbers are the ones counted from the
 * catalogue at request time.
 */
import type { Lang } from "@/lib/i18n";
import { plural } from "@/lib/i18n";

/** A band boundary as a bare number, grouped for the reader's locale. */
export function plainAmount(value: number, lang: Lang): string {
  return value.toLocaleString(lang === "uk" ? "uk-UA" : "en-CA", { maximumFractionDigits: 0 });
}

/**
 * A band boundary with the currency, spelled the way lib/api money() spells it.
 * Band edges are whole dollars, so they are printed without the cents a real
 * price carries.
 */
export function amount(value: number, lang: Lang): string {
  return `CA$ ${plainAmount(value, lang)}`;
}

const strings = {
  en: {
    /** aria-label of the whole filter block. */
    filterRegion: "Filter the shop",
    origin: "Origin",
    price: "Price",
    stock: "Stock",
    priceUnder: (max: string) => `Under ${max}`,
    priceFrom: (min: string) => `${min} and up`,
    priceBetween: (min: string, max: string) => `${min}–${max}`,
    /** Result line, beside the item count, when the view runs to several pages. */
    showing: (from: number, to: number) => `showing ${from}–${to}`,
    /** A category view's own head title: /shop?collection=kids and
     *  /shop?category=kids are two different pages and used to share one. */
    categoryTitle: (name: string) => `${name} · Shop`,
    activeFilters: "Filtering by",
    remove: (label: string) => `Remove filter: ${label}`,
    clearAll: "Clear all filters",
    searchTerm: (q: string) => `“${q}”`,
    search: "Search",
    /** The pager. */
    pages: "Pages",
    pageOf: (page: number, count: number) => `Page ${page} of ${count}`,
    goToPage: (page: number) => `Page ${page}`,
    prev: "Previous",
    next: "Next",
    prevLabel: "Previous page",
    nextLabel: "Next page",
    /** Page descriptions for views the shared dictionary has no words for. */
    originDescription: (label: string) => `Everything in the shop carrying the mark “${label}”.`,
    priceDescription: (band: string) => `Pieces in the shop priced ${band}.`,
    /** The empty state. */
    emptyWider: "Nearest views with something in them:",
    everything: "Everything in the shop",
    withCount: (n: number) => `${n} ${n === 1 ? "item" : "items"}`,
    /** Shown when the catalogue is larger than the origin/price filters can read. */
    scanNote: (n: number) =>
      `The origin and price filters read the first ${n} products of this view. Narrow it with a collection or a category to see the rest.`,
    /** Shown when the catalogue API cannot be reached. */
    apiDown: "The catalogue did not answer. Reload the page in a moment.",
  },
  uk: {
    filterRegion: "Фільтри крамниці",
    origin: "Походження",
    price: "Ціна",
    stock: "Наявність",
    priceUnder: (max: string) => `До ${max}`,
    priceFrom: (min: string) => `Від ${min}`,
    priceBetween: (min: string, max: string) => `${min}–${max}`,
    showing: (from: number, to: number) => `показано ${from}–${to}`,
    categoryTitle: (name: string) => `${name} · Крамниця`,
    activeFilters: "Фільтри",
    remove: (label: string) => `Прибрати фільтр: ${label}`,
    clearAll: "Скинути всі фільтри",
    searchTerm: (q: string) => `«${q}»`,
    search: "Пошук",
    pages: "Сторінки",
    pageOf: (page: number, count: number) => `Сторінка ${page} з ${count}`,
    goToPage: (page: number) => `Сторінка ${page}`,
    prev: "Попередня",
    next: "Наступна",
    prevLabel: "Попередня сторінка",
    nextLabel: "Наступна сторінка",
    originDescription: (label: string) => `Усе в крамниці зі знаком «${label}».`,
    priceDescription: (band: string) => `Речі в крамниці за ціною ${band}.`,
    emptyWider: "Найближчі переліки, де щось є:",
    everything: "Уся крамниця",
    withCount: (n: number) => `${n} ${plural(n, "товар", "товари", "товарів")}`,
    scanNote: (n: number) =>
      `Фільтри походження та ціни читають перші ${n} товарів цього переліку. Звузьте його колекцією чи категорією, щоб побачити решту.`,
    apiDown: "Каталог не відповів. Перезавантажте сторінку за хвилину.",
  },
};

export type ShopStrings = typeof strings.en;

export function ts(lang: Lang): ShopStrings {
  return lang === "uk" ? (strings.uk as unknown as ShopStrings) : strings.en;
}
