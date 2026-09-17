/**
 * Answer-engine surfaces (GEO) — the one place that decides what UA Market
 * tells a machine about itself.
 *
 * Three routes describe the same shop: `/llms.txt` (a short map for an agent),
 * `/llms-full.txt` (the same map with every product and maker on one line each)
 * and `/api/catalog` (the same catalogue as JSON). A shop that says 21 products
 * on one surface and 19 on another is a shop an answer engine stops quoting, so
 * all three read one snapshot built here, from the catalogue API and the
 * storefront config, and never from a hand-written list.
 *
 * The honesty rules live in this file rather than in the routes, so a new
 * surface cannot forget them:
 *
 *  1. Availability is coarse — `InStock`, `LimitedAvailability`, `OutOfStock`.
 *     The inventory ledger's numbers stay inside the fulfillment core.
 *  2. A policy value that nobody configured is printed as "not published"
 *     instead of guessed; a value that is only a software default is printed
 *     with that fact attached (see `policyLines`).
 *  3. While the deployment carries the seeded assortment, every surface opens
 *     with a line naming it placeholder data. See `catalogueStatus()`.
 *  4. Ratings, reviews, stock counts, delivery dates and a phone number are
 *     absent from the shop, so each surface prints the list of things it does
 *     not claim — and on a deployment whose checkout refuses a pickup order,
 *     collection in person joins that list. See `notPublished()`.
 *
 * Everything a reader could take as a promise comes from configuration through
 * `shopPolicy()` in lib/content.ts, which is the same reader the FAQ, shipping,
 * privacy and terms pages use. One setting therefore drives the pages, the
 * structured data and these three machine surfaces at once.
 */
import { api, money } from "@/lib/api";
import type { Category, Collection, Maker, Product, ProductSummary, StorefrontConfig, Variant } from "@/lib/api";
import { PROVINCES, pick, plural } from "@/lib/i18n";
import type { Lang } from "@/lib/i18n";
import { demoNote, fromBase, pickupHours, say, shopPolicy } from "@/lib/content";
import type { Bilingual, ShopPolicy } from "@/lib/content";
import { mailNotice } from "@/lib/i18n.mail";
import { isIndexable, pickupPlace, siteUrl, urlFor } from "@/lib/seo";
import type { PickupPlace } from "@/lib/seo";

/* --------------------------------------------------------------- constants */

/** How long a CDN may serve one generated surface. Fifteen minutes: a price or
 *  a sold-out mark reaches an agent within a quarter of an hour, and a crawler
 *  hammering the file never reaches the catalogue API. */
export const GEO_MAX_AGE_SECONDS = 900;

export const GEO_CACHE_CONTROL = `public, max-age=0, s-maxage=${GEO_MAX_AGE_SECONDS}, stale-while-revalidate=${GEO_MAX_AGE_SECONDS * 4}`;

/** Above this many products the per-product detail fetch is skipped and the
 *  surface says so, rather than making one request per product forever. */
export const GEO_DETAIL_LIMIT = 500;

const PAGE_SIZE = 120; // the catalogue API's maximum page
const DETAIL_CONCURRENCY = 6;

export const LLMS_PATH = "/llms.txt";
export const LLMS_FULL_PATH = "/llms-full.txt";
export const CATALOG_FEED_PATH = "/api/catalog";

/** These three surfaces have one address each, in no language, so they are
 *  built from the origin instead of `urlFor`, which adds the /uk prefix. */
export function absolute(path: string): string {
  return `${siteUrl()}${path}`;
}

/* ------------------------------------------------------------ page chrome */

/**
 * Section headings and fixed lines, in both languages. Interpolated sentences
 * are written as inline `{ en, uk }` pairs at the point of use, so an English
 * line and its Ukrainian twin are always edited together.
 */
export const GEO_TEXT = {
  en: {
    assortment: "What the shop sells",
    provenance: "Provenance — the three levels",
    delivery: "Delivery and pickup",
    payment: "Payment and tax",
    pages: "Pages",
    feeds: "Machine-readable surfaces",
    notPublished: "What this shop does not publish",
    contact: "Contact",
    products: "Products",
    makers: "Makers",
    fieldOrder: "Fields, in order, separated by ` | ` (the field names are the same in both languages):",
    emptyField: "An empty field means the shop has not recorded that value.",
    unavailable: "The catalogue could not be read just now. Try this address again in a minute.",
  },
  uk: {
    assortment: "Що продає крамниця",
    provenance: "Походження — три рівні",
    delivery: "Доставка та самовивіз",
    payment: "Оплата та податок",
    pages: "Сторінки",
    feeds: "Машинні поверхні",
    notPublished: "Чого ця крамниця не публікує",
    contact: "Контакт",
    products: "Товари",
    makers: "Майстри",
    fieldOrder: "Поля, по порядку, розділені ` | ` (назви полів однакові обома мовами, тому лишаються англійськими):",
    emptyField: "Порожнє поле означає, що крамниця не записала це значення.",
    unavailable: "Каталог зараз не читається. Спробуйте цю адресу за хвилину.",
  },
} as const;

export function geoText(lang: Lang) {
  return GEO_TEXT[lang];
}

/* ------------------------------------------------------------ availability */

/** Coarse availability. The three values are schema.org's, so a consumer that
 *  already understands product markup understands these without a mapping. */
export type GeoAvailability = "InStock" | "LimitedAvailability" | "OutOfStock";

/**
 * `low` on a variant is the shop's own "last ones" flag; it carries no number
 * and none is derived here. A product whose in-stock variants are all flagged
 * low reads as LimitedAvailability, anything else in stock reads as InStock.
 */
export function availabilityOf(product: ProductSummary, variants?: Variant[]): GeoAvailability {
  if (!product.in_stock) return "OutOfStock";
  const live = (variants ?? []).filter((v) => v.availability.in_stock);
  if (live.length > 0 && live.every((v) => v.availability.low)) return "LimitedAvailability";
  return "InStock";
}

/* -------------------------------------------------------- catalogue status */

export type CatalogueStatus = "placeholder" | "live";

/**
 * Whether the catalogue on this deployment is the shop's real assortment.
 *
 * `SHOP_CATALOGUE_STATUS=live` is the only thing that says yes. Everything else
 * — unset, misspelt, `placeholder` — reads as placeholder.
 *
 * It used to fall back to `WEB_INDEXABLE`, which made one switch do two jobs:
 * the day the owner turned the shop on for search engines, every surface
 * silently stopped admitting that the twenty-one seeded products are
 * demonstration data, with no second look at the catalogue itself. Going live
 * is now two deliberate switches, which is what docs/OWNER-ACTIONS.md already
 * asks the owner to decide separately. A real catalogue described as
 * placeholder costs the shop nothing; a placeholder catalogue described as
 * real is a lie an assistant repeats.
 */
export function catalogueStatus(): CatalogueStatus {
  return (process.env.SHOP_CATALOGUE_STATUS ?? "").trim().toLowerCase() === "live" ? "live" : "placeholder";
}

/* ------------------------------------------------------------------ snapshot */

export type GeoSnapshot = {
  /** ISO 8601, UTC. Printed on every surface. */
  generatedAt: string;
  /** False when the catalogue API did not answer; the routes return 503. */
  ok: boolean;
  status: CatalogueStatus;
  indexable: boolean;
  /** `full` carries technique, material and variants for every product. */
  detail: "full" | "summary";
  detailNote: Bilingual | null;
  config: StorefrontConfig | null;
  policy: ShopPolicy;
  /**
   * The locker, and null whenever this deployment's checkout will not take a
   * pickup order — which is what `pickup.enabled` on the storefront config says,
   * and what a POST of a PICKUP order is answered with. Every pickup sentence on
   * every surface hangs off this field, so a surface cannot offer a method the
   * shop refuses.
   */
  pickup: PickupPlace | null;
  /** Whether the shop can send email at all. Decides how a code is said to reach a buyer. */
  mail: boolean;
  collections: Collection[];
  categories: Category[];
  makers: Maker[];
  products: ProductSummary[];
  /** slug → full product; empty when `detail` is `summary`. */
  details: Record<string, Product>;
};

async function allProducts(): Promise<ProductSummary[]> {
  const out: ProductSummary[] = [];
  let offset = 0;
  for (;;) {
    const page = await api.products({ limit: PAGE_SIZE, offset, sort: "position" });
    out.push(...page.items);
    offset += page.items.length;
    if (page.items.length < PAGE_SIZE || offset >= page.total) break;
  }
  return out;
}

async function loadDetails(products: ProductSummary[]): Promise<Record<string, Product>> {
  const out: Record<string, Product> = {};
  for (let i = 0; i < products.length; i += DETAIL_CONCURRENCY) {
    const chunk = products.slice(i, i + DETAIL_CONCURRENCY);
    const loaded = await Promise.all(chunk.map((p) => api.product(p.slug).catch(() => null)));
    for (const product of loaded) if (product) out[product.slug] = product;
  }
  return out;
}

/**
 * Read the whole catalogue once. A failing sub-call leaves its part empty and
 * the surfaces print what they do have; a failing product list sets `ok` false
 * and the routes answer 503 instead of publishing an empty shop.
 */
export async function loadSnapshot(options: { detail?: boolean } = {}): Promise<GeoSnapshot> {
  const [config, collections, categories, makers, products] = await Promise.all([
    api.config().catch(() => null),
    api.collections().then((r) => r.items).catch(() => [] as Collection[]),
    api.categories().then((r) => r.items).catch(() => [] as Category[]),
    api.makers().then((r) => r.items).catch(() => [] as Maker[]),
    allProducts().catch(() => null),
  ]);

  const wantDetail = options.detail === true;
  const list = products ?? [];
  const tooMany = wantDetail && list.length > GEO_DETAIL_LIMIT;
  const detail: "full" | "summary" = wantDetail && !tooMany ? "full" : "summary";

  return {
    generatedAt: new Date().toISOString(),
    ok: products !== null,
    status: catalogueStatus(),
    indexable: isIndexable(),
    detail,
    detailNote: tooMany
      ? {
          en: `Per-product detail is left out above ${GEO_DETAIL_LIMIT} products. This catalogue holds ${list.length}.`,
          uk: `Деталі кожного товару пропущено, бо каталог більший за ${GEO_DETAIL_LIMIT} позицій. Тут ${list.length}.`,
        }
      : null,
    config,
    policy: shopPolicy(),
    // Offered, and only then resolved: the address the pages print comes from the
    // API, the structured parts from SHOP_PICKUP_ADDRESS_JSON, and either setting
    // alone is enough. See pickupPlace() in lib/seo.ts.
    pickup: config?.pickup.enabled ? pickupPlace(config.pickup) : null,
    mail: mailNotice(config).email,
    collections,
    categories,
    makers,
    products: list,
    details: detail === "full" ? await loadDetails(list) : {},
  };
}

/* ------------------------------------------------------------- derivations */

export const PROVENANCE_CODES = ["HANDMADE_UA", "MADE_UA", "DESIGNED_UA"] as const;
export type ProvenanceCode = (typeof PROVENANCE_CODES)[number];

/**
 * The three origin levels, with the wording the product pages use. The label
 * comes from the catalogue API per product; the meaning comes from the site's
 * own legend, so an agent reading this file and a person reading the footer are
 * told the same thing.
 */
export const PROVENANCE: { code: ProvenanceCode; label: Bilingual; means: Bilingual }[] = [
  {
    code: "HANDMADE_UA",
    label: { en: "Hand-made in Ukraine", uk: "Зроблено руками в Україні" },
    means: {
      en: "red cross-stitch: embroidered or made by hand in a named Ukrainian workshop",
      uk: "червоний хрестик: вишито чи зроблено руками в конкретній українській майстерні",
    },
  },
  {
    code: "MADE_UA",
    label: { en: "Made in Ukraine", uk: "Зроблено в Україні" },
    means: {
      en: "running stitch: sewn or produced in Ukraine, machine embroidery",
      uk: "стібок уперед голку: пошито або виготовлено в Україні, машинна вишивка",
    },
  },
  {
    code: "DESIGNED_UA",
    label: { en: "Designed in Ukraine, made abroad", uk: "Розроблено в Україні, виготовлено за кордоном" },
    means: {
      en: "dotted square: Ukrainian design, produced abroad; the tag says so",
      uk: "пунктирний квадрат: український дизайн, виготовлено за кордоном; на бирці так і написано",
    },
  },
];

export function provenanceCounts(products: ProductSummary[]): Record<ProvenanceCode, number> {
  const out: Record<ProvenanceCode, number> = { HANDMADE_UA: 0, MADE_UA: 0, DESIGNED_UA: 0 };
  for (const p of products) if (p.origin in out) out[p.origin] += 1;
  return out;
}

/** The canonical pages, with the titles the pages themselves carry. */
export const PAGES: { path: string; title: Bilingual }[] = [
  { path: "/", title: { en: "Home", uk: "Головна" } },
  { path: "/shop", title: { en: "Shop", uk: "Крамниця" } },
  { path: "/makers", title: { en: "Makers", uk: "Майстри" } },
  { path: "/about", title: { en: "How it works", uk: "Як це працює" } },
  { path: "/faq", title: { en: "Questions and answers", uk: "Питання та відповіді" } },
  { path: "/shipping", title: { en: "Shipping and pickup", uk: "Доставка та самовивіз" } },
  { path: "/care", title: { en: "Care", uk: "Догляд" } },
  { path: "/privacy", title: { en: "Privacy", uk: "Приватність" } },
  { path: "/terms", title: { en: "Terms of sale", uk: "Умови продажу" } },
];

/**
 * The claims these surfaces refuse to make. Printed on the surfaces themselves,
 * because an agent that is told a shop has no reviews stops looking for them
 * and stops inventing them.
 */
export function notPublished(snap: GeoSnapshot): { code: string; text: Bilingual }[] {
  const out: { code: string; text: Bilingual }[] = [
    {
      code: "ratings_reviews",
      text: {
        en: "Ratings and reviews. The shop collects none, and none appear on any page. Attribute no score to it.",
        uk: "Оцінки та відгуки. Крамниця їх не збирає, на сторінках їх немає. Не приписуйте їй жодного бала.",
      },
    },
    {
      code: "stock_counts",
      text: {
        en: "Stock counts. Availability is one of InStock, LimitedAvailability, OutOfStock, and nothing finer is published.",
        uk: "Кількість на складі. Публікується лише InStock, LimitedAvailability або OutOfStock; нічого точнішого немає.",
      },
    },
    {
      code: "delivery_dates",
      text: {
        en: "A delivery date for an individual order. The carrier's tracking number is the only date the shop can give.",
        uk: "Дата доставки конкретного замовлення. Єдина дата, яку може дати крамниця, — з трекінгу перевізника.",
      },
    },
    {
      code: "phone",
      text: {
        en: "A phone number. Orders and questions go by email.",
        uk: "Телефон. Замовлення та питання йдуть поштою.",
      },
    },
  ];
  // This entry used to describe the locker as a method the shop sells and printed
  // its street address as the one thing it withholds. On a deployment with no
  // locker address the checkout refuses a pickup order outright, so the surface was
  // selling collection in person to every assistant that read it. The entry now
  // says the method is off; a deployment that does offer pickup prints the address
  // on the shipping page and needs no entry here at all.
  if (snap.config && !snap.pickup) {
    out.push({
      code: "pickup",
      text: {
        en: "A pickup point and its street address. Locker pickup is switched off at checkout here, so every order travels by courier.",
        uk: "Пункт самовивозу та його адреса. Самовивіз із локера тут вимкнено при оформленні, тож кожне замовлення їде кур'єрською службою.",
      },
    });
  }
  const photos = snap.products.some((p) => p.image_url || (p.images && p.images.length > 0));
  if (!photos && snap.products.length > 0) {
    out.push({
      code: "product_photos",
      text: {
        en: "Product photographs. Each product page draws a counted chart generated from the product's name in place of a photo.",
        uk: "Фотографії товарів. Замість фото сторінка товару малює лічильну схему, згенеровану з назви товару.",
      },
    });
  } else if (photos && snap.status === "placeholder" && snap.products.length > 0) {
    // The demonstration catalogue ships with generated pictures, so the entry above
    // stopped firing the day they arrived. A picture that looks like a photograph and
    // is not one is exactly the kind of thing this list exists to declare.
    out.push({
      code: "product_photos",
      text: {
        en: "Photographs of goods in stock. The pictures here are generated demonstration images of the kind of piece each entry describes.",
        uk: "Фотографії наявних товарів. Зображення тут — згенеровані демонстраційні картинки того типу речі, який описує кожен запис.",
      },
    });
  }
  return out;
}

/* ------------------------------------------------------------- formatting */

/** A price as a bare number, or a range when variants differ. Currency is
 *  stated once per surface, so it is left off the figure. */
export function priceField(p: ProductSummary): string {
  const from = p.price_from_cad.toFixed(2);
  if (p.price_to_cad > p.price_from_cad) return `${from}–${p.price_to_cad.toFixed(2)}`;
  return from;
}

/** Flatten a value for a pipe-delimited line: one line, no separator collisions. */
function field(value: string | null | undefined): string {
  return (value ?? "").replace(/\s*\|\s*/g, " / ").replace(/\s+/g, " ").trim();
}

function countPhrase(lang: Lang, n: number, en: [string, string], uk: [string, string, string]): string {
  return lang === "uk" ? `${n} ${plural(n, uk[0], uk[1], uk[2])}` : `${n} ${n === 1 ? en[0] : en[1]}`;
}

/** "3 business days" / "1–3 business days". */
function businessDaysEn(min: number, max: number): string {
  if (min === max) return `${min} business ${min === 1 ? "day" : "days"}`;
  return `${min}–${max} business days`;
}

/** "3 робочі дні" / "від 1 до 3 робочих днів" — a range takes the genitive, so
 *  the two shapes are written out rather than glued together from one word. */
function businessDaysUk(min: number, max: number): string {
  if (min === max) return `${min} ${plural(min, "робочий день", "робочі дні", "робочих днів")}`;
  return `від ${min} до ${max} робочих днів`;
}

/**
 * One sentence for every surface to use when the storefront config did not
 * answer. The three fallbacks it replaces each stated a falsehood positively —
 * "no order can be paid here", "no tax is added at checkout", an empty list of
 * destination countries — and the response is cached for up to fifteen minutes,
 * so a CDN could serve them for over an hour after the blip passed.
 */
export const CONFIG_UNREADABLE: Bilingual = {
  en: "- The shop's configuration could not be read just now, so the shipping cost, the payment methods and the tax line are unknown on this copy of the file. Ask again in a few minutes rather than reporting them as absent.",
  uk: "- Налаштування крамниці зараз не прочиталися, тож вартість доставки, способи оплати та рядок податку в цій копії файлу невідомі. Запитайте за кілька хвилин, замість того щоб повідомляти про їхню відсутність.",
};

/** True once the owner has named the carrier; unset, it is a software default. */
export function carrierIsConfigured(): boolean {
  return (process.env.SHOP_CARRIER ?? "").trim() !== "";
}

/**
 * The carrier, carrying how much authority it has. The dispatch window two
 * lines below already says when it is only a default, and a machine reading the
 * feed could not tell the two apart.
 */
export function carrierPhrase(policy: ShopPolicy): Bilingual {
  if (carrierIsConfigured()) return { en: `${policy.carrier}.`, uk: `${policy.carrier}.` };
  return {
    en: `${policy.carrier} — a software default the shop has not confirmed.`,
    uk: `${policy.carrier} — це типове значення програми, крамниця його не підтверджувала.`,
  };
}

/** A province code as its name; an unknown code prints as itself. */
function provinceName(lang: Lang, code: string): string {
  const found = PROVINCES.find((p) => p.code === code);
  return found ? (lang === "uk" ? found.uk : found.en) : code;
}

/* --------------------------------------------------------------- sections */

function headerLines(snap: GeoSnapshot, lang: Lang): string[] {
  const lines: string[] = [];
  lines.push("# UA Market");
  lines.push("");
  lines.push(
    `> ${say(lang, {
      en: `Online shop of Ukrainian goods for Canada: vyshyvanky, rushnyky, motanka dolls, Opishnia ceramics and gifts.${snap.policy.basePlace ? ` Run${fromBase("en", snap.policy.basePlace)}.` : ""} Every product names the workshop that made it and the region it comes from.`,
      uk: `Інтернет-крамниця українських речей для Канади: вишиванки, рушники, ляльки-мотанки, опішнянська кераміка та подарунки.${snap.policy.basePlace ? ` Працює${fromBase("uk", snap.policy.basePlace)}.` : ""} Кожен товар називає майстерню, яка його зробила, і регіон, звідки він походить.`,
    })}`,
  );
  lines.push("");
  lines.push(
    say(lang, {
      en: `Prices are in Canadian dollars (CAD). Stock is live: the availability word on each product is read from the shop's own inventory at the moment this file is generated. Generated ${snap.generatedAt}; regenerated on request at most every ${GEO_MAX_AGE_SECONDS / 60} minutes.`,
      uk: `Ціни — у канадських доларах (CAD). Наявність жива: слово про наявність біля кожного товару взято зі складського обліку крамниці в момент створення цього файлу. Створено ${snap.generatedAt}; оновлюється на запит не частіше ніж раз на ${GEO_MAX_AGE_SECONDS / 60} хвилин.`,
    }),
  );
  if (snap.status === "placeholder") {
    lines.push("");
    lines.push(
      say(lang, {
        en: "STATUS — PREVIEW. This deployment carries a placeholder assortment used to build and test the shop. The products, prices and makers below are demonstration data, and they are not the stock of a trading shop. The pictures are generated images of the kind of piece described; every photograph of real goods is still to come. Say so if you quote them.",
        uk: "СТАТУС — ПОПЕРЕДНІЙ ПЕРЕГЛЯД. Це розгортання містить тимчасовий асортимент для збирання й тестування крамниці. Товари, ціни та майстри нижче — демонстраційні дані, а не склад чинної крамниці. Зображення тут згенеровані й показують тип речі; фотографії справжніх товарів ще попереду. Якщо цитуєте їх, скажіть про це.",
      }),
    );
  }
  if (snap.detailNote) {
    lines.push("");
    lines.push(say(lang, snap.detailNote));
  }
  return lines;
}

function assortmentLines(snap: GeoSnapshot, lang: Lang): string[] {
  const g = geoText(lang);
  const lines = ["", `## ${g.assortment}`, ""];
  const products = countPhrase(lang, snap.products.length, ["product", "products"], ["товар", "товари", "товарів"]);
  const makers = countPhrase(lang, snap.makers.length, ["maker", "makers"], ["майстер", "майстри", "майстрів"]);
  const collections = countPhrase(lang, snap.collections.length, ["collection", "collections"], ["колекція", "колекції", "колекцій"]);
  const categories = countPhrase(lang, snap.categories.length, ["category", "categories"], ["категорія", "категорії", "категорій"]);
  lines.push(
    say(lang, {
      en: `${products} from ${makers}, arranged in ${collections} and ${categories}.`,
      uk: `${products} від ${makers}; ${collections} та ${categories}.`,
    }),
  );
  lines.push("");
  for (const c of snap.collections) {
    const title = pick(lang, c.title, c.title_uk);
    const lede = pick(lang, c.lede, c.lede_uk);
    const count = countPhrase(lang, c.count, ["product", "products"], ["товар", "товари", "товарів"]);
    lines.push(`- **${title}** (\`${c.slug}\`, ${count}) — ${lede} → ${urlFor(lang, `/shop?collection=${encodeURIComponent(c.slug)}`)}`);
  }
  if (snap.categories.length > 0) {
    lines.push("");
    const parts = snap.categories.map((c) => `${pick(lang, c.title, c.title_uk)} (${c.count}, \`${c.slug}\`)`);
    lines.push(
      say(lang, {
        en: `Categories: ${parts.join(", ")}.`,
        uk: `Категорії: ${parts.join(", ")}.`,
      }),
    );
  }
  return lines;
}

function provenanceLines(snap: GeoSnapshot, lang: Lang): string[] {
  const g = geoText(lang);
  const counts = provenanceCounts(snap.products);
  const lines = ["", `## ${g.provenance}`, ""];
  lines.push(
    say(lang, {
      en: "Every product carries exactly one of these three marks, shown on its tile, beside its title and in the bag. The mark describes how the thing was made.",
      uk: "Кожен товар несе рівно один із цих трьох знаків — на плитці, біля назви та в кошику. Знак описує, як річ зроблено.",
    }),
  );
  lines.push("");
  for (const level of PROVENANCE) {
    lines.push(`- \`${level.code}\` — ${say(lang, level.label)}; ${say(lang, level.means)}. ${counts[level.code]}/${snap.products.length}`);
  }
  return lines;
}

function deliveryLines(snap: GeoSnapshot, lang: Lang): string[] {
  const g = geoText(lang);
  const cfg = snap.config;
  const policy = snap.policy;
  const lines = ["", `## ${g.delivery}`, ""];

  const fromEn = fromBase("en", policy.basePlace);
  const fromUk = fromBase("uk", policy.basePlace);
  if (!cfg) {
    lines.push(say(lang, CONFIG_UNREADABLE));
    lines.push(
      `- ${say(lang, {
        en: `Shipping and pickup in full: ${urlFor(lang, "/shipping")}`,
        uk: `Доставка та самовивіз повністю: ${urlFor(lang, "/shipping")}`,
      })}`,
    );
    return lines;
  }
  const countries = cfg.shipping.countries ?? [];
  const where =
    countries.length === 0
      ? null
      : countries.includes("CA") && countries.length === 1
        ? say(lang, { en: "Canada", uk: "Канади" })
        : countries.join(", ");
  lines.push(
    where
      ? say(lang, {
          en: `- Ships${fromEn} to ${where}. Carrier: ${carrierPhrase(policy).en}`,
          uk: `- Відправлення${fromUk} у межах ${where}. Перевізник: ${carrierPhrase(policy).uk}`,
        })
      : say(lang, {
          en: `- Ships${fromEn}. The shop publishes no list of destination countries. Carrier: ${carrierPhrase(policy).en}`,
          uk: `- Відправлення${fromUk}. Крамниця не публікує переліку країн доставки. Перевізник: ${carrierPhrase(policy).uk}`,
        }),
  );
  lines.push(
    say(lang, {
      en: `- Shipping: flat ${money(cfg.shipping.flat_cad, "en")} per order, free over ${money(cfg.shipping.free_over_cad, "en")}.`,
      uk: `- Доставка: фіксовано ${money(cfg.shipping.flat_cad, "uk")} за замовлення, безкоштовно від ${money(cfg.shipping.free_over_cad, "uk")}.`,
    }),
  );
  if (snap.pickup) {
    const label = pick(lang, cfg.pickup.label, cfg.pickup.label_uk);
    // The hours clause was hard-coded as "day or night". Nothing in the config
    // or the environment records when the bay is reachable, and the pickup
    // point is a residential garage, so an assistant was telling buyers they
    // could collect at three in the morning. PICKUP_HOURS (or SHOP_PICKUP_HOURS,
    // with SHOP_PICKUP_HOURS_UK as its Ukrainian rendering) is the setting.
    const open = pickupHours(cfg);
    const hours = open ? say(lang, open) : "";
    // How the code reaches the buyer is a fact about SMTP, not a promise the
    // copy may make on its own: with the mailer off, nothing is sent to anybody
    // and the order page is the only place the digits appear.
    const reaches: Bilingual = snap.mail
      ? {
          en: "The code is emailed to the buyer, and their order page carries it too.",
          uk: "Код надходить покупцеві поштою, і той самий код показує сторінка його замовлення.",
        }
      : {
          en: "The code appears on the buyer's own order page; the shop sends no email yet.",
          uk: "Код з'являється на сторінці замовлення покупця; крамниця поки не надсилає листів.",
        };
    lines.push(
      say(lang, {
        en: `- ${label}: free. The locker is at ${snap.pickup.line}${hours ? `, and it can be reached ${hours}` : ""}. A one-time code opens the bay. ${reaches.en}`,
        uk: `- ${label}: безкоштовно. Локер стоїть за адресою ${snap.pickup.line}${hours ? `, дістатися до нього можна ${hours}` : ""}. Одноразовий код відкриває комірку. ${reaches.uk}`,
      }),
    );
  } else {
    // The silence used to be total: a surface that said nothing about pickup left an
    // assistant free to assume the shop has a counter. It answers the question
    // instead, the way the shipping page and the FAQ answer it.
    lines.push(
      say(lang, {
        en: "- Pickup: not offered at the moment. Every order travels by courier, and an order that asks for pickup is refused at checkout.",
        uk: "- Самовивіз: наразі не пропонується. Кожне замовлення їде кур'єрською службою, а замовлення із самовивозом при оформленні відхиляється.",
      }),
    );
  }
  lines.push(...policyLines(snap, lang));
  lines.push(
    `- ${say(lang, {
      en: `Shipping and pickup in full: ${urlFor(lang, "/shipping")}`,
      uk: `Доставка та самовивіз повністю: ${urlFor(lang, "/shipping")}`,
    })}`,
  );
  return lines;
}

/**
 * The two time promises, each printed with how much authority it carries.
 * `SHOP_HANDLING_DAYS` and `SHOP_TRANSIT_DAYS` are the settings; unset, the
 * dispatch window falls back to a software default and says so, and the transit
 * line states plainly that the shop publishes no estimate.
 */
export function policyLines(snap: GeoSnapshot, lang: Lang): string[] {
  const policy = snap.policy;
  const lines: string[] = [];
  const handlingSet =
    (process.env.SHOP_HANDLING_DAYS ?? "").trim() !== "" ||
    (process.env.SHOP_PROCESSING_DAYS_MIN ?? "").trim() !== "" ||
    (process.env.SHOP_PROCESSING_DAYS_MAX ?? "").trim() !== "";
  const { min, max } = policy.processingDays;
  lines.push(
    say(lang, {
      en: `- Dispatch window: ${businessDaysEn(min, max)} between payment and handover to ${policy.carrier}${handlingSet ? "." : " — a software default the shop has not confirmed."}`,
      uk: `- Пакування: ${businessDaysUk(min, max)} між оплатою та передачею до ${policy.carrier}${handlingSet ? "." : " — це типове значення програми, крамниця його не підтверджувала."}`,
    }),
  );
  if (policy.deliveryEstimate) {
    lines.push(`- ${say(lang, policy.deliveryEstimate)}`);
  } else if (policy.transitDays) {
    const [tmin, tmax] = policy.transitDays;
    lines.push(
      say(lang, {
        en: `- Time in transit: the shop's estimate is ${businessDaysEn(tmin, tmax)} with ${policy.carrier}.`,
        uk: `- Час у дорозі: крамниця оцінює його в ${businessDaysUk(tmin, tmax)} через ${policy.carrier}.`,
      }),
    );
  } else {
    lines.push(
      say(lang, {
        en: "- Time in transit: the shop publishes no estimate. The tracking number is the answer.",
        uk: "- Час у дорозі: крамниця не публікує оцінки. Відповідь дає номер відстеження.",
      }),
    );
  }
  if (policy.returnWindowDays) {
    lines.push(
      say(lang, {
        en: `- Returns: ${policy.returnWindowDays} days after delivery to start one${demoNote("en")}. Terms: ${urlFor(lang, "/terms")}`,
        uk: `- Повернення: ${policy.returnWindowDays} днів після доставки, щоб його розпочати${demoNote("uk")}. Умови: ${urlFor(lang, "/terms")}`,
      }),
    );
  } else {
    lines.push(
      say(lang, {
        en: `- Returns: the shop publishes no return window. A buyer writes and the case is settled by email. Terms: ${urlFor(lang, "/terms")}`,
        uk: `- Повернення: крамниця не публікує строку повернення. Покупець пише, і справу залагоджують поштою. Умови: ${urlFor(lang, "/terms")}`,
      }),
    );
  }
  return lines;
}

function paymentLines(snap: GeoSnapshot, lang: Lang): string[] {
  const g = geoText(lang);
  const cfg = snap.config;
  const lines = ["", `## ${g.payment}`, ""];
  if (!cfg) {
    lines.push(say(lang, CONFIG_UNREADABLE));
    return lines;
  }
  const methods = cfg.payment_methods ?? [];
  if (methods.includes("ETRANSFER")) {
    const to = cfg.etransfer_email;
    lines.push(
      say(lang, {
        en: `- Interac e-Transfer${to ? ` to ${to}` : ""}. An order waits as unpaid until the transfer arrives, then we pack it.`,
        uk: `- Interac e-Transfer${to ? ` на ${to}` : ""}. Замовлення лишається неоплаченим, доки надійде переказ, а тоді йде в роботу.`,
      }),
    );
  }
  if (methods.includes("STRIPE")) {
    lines.push(
      say(
        lang,
        cfg.payment_test_mode
          ? { en: "- Card (test payment, no money moves).", uk: "- Картка (тестова оплата, гроші не рухаються)." }
          : { en: "- Card payment through Stripe Checkout.", uk: "- Оплата карткою через Stripe Checkout." },
      ),
    );
  }
  if (methods.includes("INVOICE")) {
    lines.push(
      say(lang, {
        en: "- Payment details sent to the buyer by arrangement.",
        uk: "- Реквізити надсилають покупцеві за домовленістю.",
      }),
    );
  }
  if (methods.length === 0) {
    lines.push(
      say(lang, {
        en: "- No payment method is configured on this deployment, so no order can be paid here.",
        uk: "- На цьому розгортанні не налаштовано жодного способу оплати, тож оплатити замовлення тут не можна.",
      }),
    );
  }
  const provinces = cfg.tax.configured_provinces ?? [];
  const named = (l: Lang) => provinces.map((code) => `${provinceName(l, code)} (${code})`).join(", ");
  lines.push(
    provinces.length > 0
      ? say(lang, {
          en: `- Sales tax is added for delivery to: ${named("en")}. No tax line is configured for any other province.`,
          uk: `- Податок з продажу додається для доставки в: ${named("uk")}. Для інших провінцій рядок податку не налаштовано.`,
        })
      : say(lang, {
          en: "- No sales tax line is configured, so no tax is added at checkout.",
          uk: "- Рядок податку з продажу не налаштовано, тож на оплаті податок не додається.",
        }),
  );
  return lines;
}

function pageLines(snap: GeoSnapshot, lang: Lang): string[] {
  const g = geoText(lang);
  const lines = ["", `## ${g.pages}`, ""];
  for (const page of PAGES) lines.push(`- [${say(lang, page.title)}](${urlFor(lang, page.path)})`);
  lines.push("");
  lines.push(
    say(lang, {
      en: `Each product lives at /product/<slug> and each maker at /makers/<slug>; ${LLMS_FULL_PATH} lists every one of them. English is served without a language prefix and Ukrainian under /uk, so ${urlFor("en", "/shop")} and ${urlFor("uk", "/shop")} are the same page in two languages.`,
      uk: `Кожен товар живе за /product/<slug>, кожен майстер — за /makers/<slug>; ${LLMS_FULL_PATH} перелічує їх усі. Англійська віддається без мовного префікса, українська — під /uk, тож ${urlFor("en", "/shop")} і ${urlFor("uk", "/shop")} — та сама сторінка двома мовами.`,
    }),
  );
  lines.push("");
  lines.push(
    say(lang, {
      en: "The bag, the checkout and a customer's own order page hold one shopper's state and are closed to crawlers in robots.txt.",
      uk: "Кошик, оформлення та сторінка власного замовлення тримають стан одного покупця й закриті для сканерів у robots.txt.",
    }),
  );
  return lines;
}

function feedLines(snap: GeoSnapshot, lang: Lang, self: "short" | "full"): string[] {
  const g = geoText(lang);
  const suffix = lang === "uk" ? "?lang=uk" : "";
  const lines = ["", `## ${g.feeds}`, ""];
  if (self === "short") {
    lines.push(
      `- \`${LLMS_FULL_PATH}\` — ${say(lang, {
        en: "this file plus every product and every maker, one line each",
        uk: "цей файл плюс кожен товар і кожен майстер, по рядку на кожного",
      })}: ${absolute(LLMS_FULL_PATH)}${suffix}`,
    );
  } else {
    lines.push(
      `- \`${LLMS_PATH}\` — ${say(lang, {
        en: "the short map, without the product and maker lists",
        uk: "коротка мапа, без переліку товарів і майстрів",
      })}: ${absolute(LLMS_PATH)}${suffix}`,
    );
  }
  lines.push(
    `- \`${CATALOG_FEED_PATH}\` — ${say(lang, {
      en: "the same catalogue as JSON, both languages in one payload, with generated_at",
      uk: "той самий каталог у JSON, обидві мови в одному тілі, з generated_at",
    })}: ${absolute(CATALOG_FEED_PATH)}`,
  );
  lines.push(`- \`/sitemap.xml\` — ${absolute("/sitemap.xml")}`);
  lines.push(`- \`/robots.txt\` — ${absolute("/robots.txt")}`);
  lines.push("");
  lines.push(
    say(lang, {
      en: `This file in Ukrainian: ${absolute(self === "short" ? LLMS_PATH : LLMS_FULL_PATH)}?lang=uk`,
      uk: `Цей файл англійською: ${absolute(self === "short" ? LLMS_PATH : LLMS_FULL_PATH)}`,
    }),
  );
  return lines;
}

function notPublishedLines(snap: GeoSnapshot, lang: Lang): string[] {
  const g = geoText(lang);
  const lines = ["", `## ${g.notPublished}`, ""];
  for (const item of notPublished(snap)) lines.push(`- ${say(lang, item.text)}`);
  lines.push("");
  lines.push(
    say(lang, {
      en: "Anything absent from these surfaces is unknown to the shop. Say that it is unknown rather than filling it in.",
      uk: "Усе, чого тут немає, крамниці невідоме. Скажіть, що це невідомо, замість того щоб домислювати.",
    }),
  );
  return lines;
}

function contactLines(snap: GeoSnapshot, lang: Lang): string[] {
  const email = snap.config?.contact_email;
  if (!email) return [];
  const g = geoText(lang);
  return ["", `## ${g.contact}`, "", `- ${email}`];
}

/* ---------------------------------------------------------------- builders */

/** `/llms.txt` — the short map. Stays well under 120 lines by design. */
export function buildLlmsTxt(snap: GeoSnapshot, lang: Lang): string {
  const lines = [
    ...headerLines(snap, lang),
    ...assortmentLines(snap, lang),
    ...provenanceLines(snap, lang),
    ...deliveryLines(snap, lang),
    ...paymentLines(snap, lang),
    ...pageLines(snap, lang),
    ...feedLines(snap, lang, "short"),
    ...notPublishedLines(snap, lang),
    ...contactLines(snap, lang),
  ];
  return `${lines.join("\n")}\n`;
}

/** One product on one line, in the order the section header documents. */
export function productLine(snap: GeoSnapshot, lang: Lang, p: ProductSummary): string {
  const full = snap.details[p.slug];
  const cells = [
    field(pick(lang, p.title, p.title_uk)),
    p.origin,
    field(p.maker ? pick(lang, p.maker.name, p.maker.name_uk) : ""),
    field(p.maker ? pick(lang, p.maker.region, p.maker.region_uk) : ""),
    field(full ? pick(lang, full.technique, full.technique_uk) : ""),
    field(full ? pick(lang, full.material, full.material_uk) : ""),
    priceField(p),
    availabilityOf(p, full?.variants),
    urlFor(lang, `/product/${encodeURIComponent(p.slug)}`),
  ];
  return `- ${cells.join(" | ")}`;
}

/** One maker on one line. */
export function makerLine(lang: Lang, m: Maker): string {
  const cells = [
    field(pick(lang, m.name, m.name_uk)),
    field(pick(lang, m.region, m.region_uk)),
    m.country,
    field(pick(lang, m.craft, m.craft_uk)),
    String(m.product_count ?? ""),
    urlFor(lang, `/makers/${encodeURIComponent(m.slug)}`),
  ];
  return `- ${cells.join(" | ")}`;
}

/** `/llms-full.txt` — the short map plus every product and every maker. */
export function buildLlmsFullTxt(snap: GeoSnapshot, lang: Lang): string {
  const g = geoText(lang);
  const lines = [
    ...headerLines(snap, lang),
    ...assortmentLines(snap, lang),
    ...provenanceLines(snap, lang),
    ...deliveryLines(snap, lang),
    ...paymentLines(snap, lang),
    ...pageLines(snap, lang),
  ];

  lines.push("", `## ${g.products} (${snap.products.length})`, "");
  lines.push(g.fieldOrder);
  lines.push("`title | origin | maker | region | technique | material | price CAD | availability | url`");
  lines.push(g.emptyField);
  lines.push("");
  for (const p of snap.products) lines.push(productLine(snap, lang, p));

  lines.push("", `## ${g.makers} (${snap.makers.length})`, "");
  lines.push(g.fieldOrder);
  lines.push("`name | region | country | craft | products | url`");
  lines.push("");
  for (const m of snap.makers) lines.push(makerLine(lang, m));

  lines.push(...feedLines(snap, lang, "full"));
  lines.push(...notPublishedLines(snap, lang));
  lines.push(...contactLines(snap, lang));
  return `${lines.join("\n")}\n`;
}

/* ------------------------------------------------------------- JSON feed */

export type FeedText = { en: string; uk: string | null };

export type FeedProduct = {
  slug: string;
  url: { en: string; uk: string };
  title: FeedText;
  subtitle: FeedText;
  category: string;
  collection: string;
  origin: ProvenanceCode | string;
  origin_label: FeedText;
  origin_note: FeedText;
  maker: { slug: string; name: FeedText; region: FeedText } | null;
  price_cad: { from: number; to: number };
  availability: GeoAvailability;
  variant_count: number;
  technique?: FeedText;
  material?: FeedText;
  care?: FeedText;
  description?: FeedText;
  variants?: { sku: string; label: string; options: Record<string, string>; price_cad: number; weight_g: number | null; availability: GeoAvailability }[];
};

export type CatalogFeed = Record<string, unknown>;

function text(en: string | null | undefined, uk: string | null | undefined): FeedText {
  return { en: en ?? "", uk: uk ?? null };
}

/**
 * `/api/catalog` — the machine feed.
 *
 * Both languages travel in one payload rather than one document per language,
 * so a consumer cannot pick up an English price and a Ukrainian availability
 * from two different reads. A Google Merchant feed would be generated from this
 * structure; see docs/GEO.md for what it still needs first.
 */
export function buildCatalogFeed(snap: GeoSnapshot): CatalogFeed {
  const cfg = snap.config;
  const products: FeedProduct[] = snap.products.map((p) => {
    const full = snap.details[p.slug];
    const entry: FeedProduct = {
      slug: p.slug,
      url: { en: urlFor("en", `/product/${p.slug}`), uk: urlFor("uk", `/product/${p.slug}`) },
      title: text(p.title, p.title_uk),
      subtitle: text(p.subtitle, p.subtitle_uk),
      category: p.category,
      collection: p.collection,
      origin: p.origin,
      origin_label: text(p.origin_label, p.origin_label_uk),
      origin_note: text(p.origin_note, p.origin_note_uk),
      maker: p.maker
        ? { slug: p.maker.slug, name: text(p.maker.name, p.maker.name_uk), region: text(p.maker.region, p.maker.region_uk) }
        : null,
      price_cad: { from: p.price_from_cad, to: p.price_to_cad },
      availability: availabilityOf(p, full?.variants),
      variant_count: p.variant_count,
    };
    if (full) {
      entry.technique = text(full.technique, full.technique_uk);
      entry.material = text(full.material, full.material_uk);
      entry.care = text(full.care, full.care_uk);
      entry.description = text(full.description, full.description_uk);
      entry.variants = full.variants.map((v) => ({
        sku: v.sku,
        label: v.label,
        options: v.options,
        price_cad: v.price_cad,
        weight_g: v.weight_g,
        availability: v.availability.in_stock ? (v.availability.low ? "LimitedAvailability" : "InStock") : "OutOfStock",
      }));
    }
    return entry;
  });

  return {
    generated_at: snap.generatedAt,
    source: absolute(CATALOG_FEED_PATH),
    documentation: absolute(LLMS_PATH),
    catalogue_status: snap.status,
    /**
     * False when the storefront config did not answer. Without it a consumer
     * cannot tell "the shop configured no payment method" from "this read
     * failed", because both arrive as null.
     */
    config_read: cfg !== null,
    detail: snap.detail,
    detail_note: snap.detailNote ? snap.detailNote.en : null,
    currency: cfg?.currency ?? "CAD",
    languages: cfg?.locales ?? ["en", "uk"],
    readme: {
      what: "Machine feed of the UA Market catalogue, for answer engines and agents. Every field is read from the shop's own catalogue at generated_at.",
      availability: "Coarse by design: InStock, LimitedAvailability or OutOfStock. The shop publishes no stock counts.",
      placeholder:
        snap.status === "placeholder"
          ? "This deployment carries a placeholder assortment used to build and test the shop. The images are generated demonstration pictures of the kind of piece described. Do not present these products as a trading shop's stock."
          : null,
      not_published: notPublished(snap).map((n) => ({ code: n.code, text: n.text.en })),
      query: { detail: "full (default) or summary; summary omits technique, material, care, description and variants" },
    },
    shop: {
      name: "UA Market",
      base: snap.policy.basePlace ? { en: snap.policy.basePlace.en, uk: snap.policy.basePlace.uk } : null,
      seller: { en: snap.policy.seller.en, uk: snap.policy.seller.uk, is_legal_name: snap.policy.sellerIsLegalName },
      contact_email: cfg?.contact_email ?? null,
      urls: {
        en: urlFor("en", "/"),
        uk: urlFor("uk", "/"),
        llms_txt: absolute(LLMS_PATH),
        llms_full_txt: absolute(LLMS_FULL_PATH),
        sitemap: absolute("/sitemap.xml"),
        robots: absolute("/robots.txt"),
      },
    },
    shipping: cfg
      ? {
          carrier: snap.policy.carrier,
          carrier_source: carrierIsConfigured() ? "configured" : "software default, unconfirmed",
          flat_cad: cfg.shipping.flat_cad,
          free_over_cad: cfg.shipping.free_over_cad,
          countries: cfg.shipping.countries,
          handling_days: snap.policy.processingDays,
          handling_days_source: (process.env.SHOP_HANDLING_DAYS ?? "").trim() !== "" ? "configured" : "software default, unconfirmed",
          transit_days: snap.policy.transitDays,
          /**
           * Null means the checkout refuses a pickup order, which is the whole of
           * what a consumer needs to know: no label, no address, no code. The
           * `code_reaches` value is a fact about this deployment's mailer, so a
           * consumer never tells a buyer to wait for a message nobody will send.
           */
          pickup: snap.pickup
            ? {
                label: text(cfg.pickup.label, cfg.pickup.label_uk),
                province: cfg.pickup.province,
                address: snap.pickup.line,
                hours: pickupHours(cfg)?.en ?? null,
                code_reaches: snap.mail ? "email and the buyer's order page" : "the buyer's order page only",
              }
            : null,
        }
      : null,
    payment: cfg ? { methods: cfg.payment_methods, etransfer_email: cfg.etransfer_email } : null,
    tax: cfg ? { configured_provinces: cfg.tax.configured_provinces } : null,
    returns: { window_days: snap.policy.returnWindowDays, refund_business_days: snap.policy.refundBusinessDays },
    provenance: PROVENANCE.map((level) => ({ code: level.code, label: level.label, means: level.means, count: provenanceCounts(snap.products)[level.code] })),
    collections: snap.collections.map((c) => ({
      slug: c.slug,
      title: text(c.title, c.title_uk),
      lede: text(c.lede, c.lede_uk),
      product_count: c.count,
      url: { en: urlFor("en", `/shop?collection=${c.slug}`), uk: urlFor("uk", `/shop?collection=${c.slug}`) },
    })),
    categories: snap.categories.map((c) => ({
      slug: c.slug,
      title: text(c.title, c.title_uk),
      product_count: c.count,
      url: { en: urlFor("en", `/shop?category=${c.slug}`), uk: urlFor("uk", `/shop?category=${c.slug}`) },
    })),
    makers: snap.makers.map((m) => ({
      slug: m.slug,
      name: text(m.name, m.name_uk),
      region: text(m.region, m.region_uk),
      country: m.country,
      craft: text(m.craft, m.craft_uk),
      founded_year: m.founded_year,
      product_count: m.product_count ?? null,
      url: { en: urlFor("en", `/makers/${m.slug}`), uk: urlFor("uk", `/makers/${m.slug}`) },
    })),
    products,
  };
}
