/**
 * Structured data for the storefront.
 *
 * <JsonLd data={...} /> is a server component that prints one
 * application/ld+json script. The builders below produce the nodes; none of
 * them carries "@context", the component adds it once, so several nodes can be
 * handed over as an array and land in a single "@graph".
 *
 * What this file will not emit: aggregateRating, review, a delivery time, a
 * return window or a street address that nobody has configured. A claim a
 * crawler can quote back at the shop has to come from real data, so every such
 * field is read from `shopPolicy()` and left out when it is unset.
 */
import { demoNote } from "@/lib/content";
import { href, pick, t } from "@/lib/i18n";
import type { Lang } from "@/lib/i18n";
import type { Product, ProductSummary, StorefrontConfig } from "@/lib/api";
import { pickupPlace, shopPolicy, siteUrl } from "@/lib/seo";
import type { PickupPlace } from "@/lib/seo";

export type JsonLdValue = string | number | boolean | null | JsonLdObject | JsonLdValue[];
export type JsonLdObject = { [key: string]: JsonLdValue | undefined };

const SCHEMA = "https://schema.org";
const CURRENCY = "CAD";
/** The shop ships inside Canada only (storefront config: shipping.countries). */
const COUNTRY = "CA";

/** Stable node ids so several scripts on one page describe the same things. */
export function storeId(): string {
  return `${siteUrl()}/#store`;
}
export function websiteId(): string {
  return `${siteUrl()}/#website`;
}

/** JSON that is safe between <script> tags. */
function serialise(node: JsonLdObject): string {
  return JSON.stringify(node)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/&/g, "\\u0026")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}

export default function JsonLd({ data, id }: { data: JsonLdObject | (JsonLdObject | null)[] | null; id?: string }) {
  const nodes = (Array.isArray(data) ? data : [data]).filter((n): n is JsonLdObject => Boolean(n));
  if (nodes.length === 0) return null;
  const payload: JsonLdObject =
    nodes.length === 1 ? { "@context": SCHEMA, ...nodes[0] } : { "@context": SCHEMA, "@graph": nodes };
  return <script id={id} type="application/ld+json" dangerouslySetInnerHTML={{ __html: serialise(payload) }} />;
}

/* ------------------------------------------------------------------ store */

export type OnlineStoreInput = {
  lang: Lang;
  /** Defaults to the brand name. */
  name?: string;
  description?: string;
  /** Absolute URL of a logo file. Left out while no logo exists. */
  logoUrl?: string | null;
  /** contact_email from the storefront config; left out when null. */
  email?: string | null;
};

/**
 * The shop itself. `sameAs` stays out until real profile links exist, and the
 * logo stays out until a logo file exists.
 */
export function onlineStore(input: OnlineStoreInput): JsonLdObject {
  const node: JsonLdObject = {
    "@type": "OnlineStore",
    "@id": storeId(),
    name: input.name ?? t(input.lang).brand,
    url: `${siteUrl()}/`,
    areaServed: { "@type": "Country", name: COUNTRY },
    currenciesAccepted: CURRENCY,
    knowsLanguage: ["en-CA", "uk-UA"],
  };
  if (input.description) node.description = input.description;
  if (input.logoUrl) node.logo = input.logoUrl;
  if (input.email) {
    node.email = input.email;
    node.contactPoint = {
      "@type": "ContactPoint",
      contactType: "customer support",
      email: input.email,
      areaServed: COUNTRY,
      availableLanguage: ["en", "uk"],
    };
  }
  return node;
}

/** Alias for callers that want the plain Organization name. */
export const organization = onlineStore;

/* ---------------------------------------------------------------- website */

export type WebsiteInput = {
  lang: Lang;
  name?: string;
  description?: string;
};

/** The site, with the search box that points at /shop?q=. */
export function website(input: WebsiteInput): JsonLdObject {
  const search = `${siteUrl()}${href(input.lang, "/shop")}?q={search_term_string}`;
  const node: JsonLdObject = {
    "@type": "WebSite",
    "@id": websiteId(),
    name: input.name ?? t(input.lang).brand,
    url: `${siteUrl()}${href(input.lang, "/")}`,
    inLanguage: input.lang === "uk" ? "uk-UA" : "en-CA",
    publisher: { "@id": storeId() },
    potentialAction: {
      "@type": "SearchAction",
      target: { "@type": "EntryPoint", urlTemplate: search },
      "query-input": "required name=search_term_string",
    },
  };
  if (input.description) node.description = input.description;
  return node;
}

/* ------------------------------------------------------------- breadcrumbs */

export type Crumb = { name: string; url: string };

export function breadcrumbList(items: Crumb[]): JsonLdObject | null {
  if (!items.length) return null;
  return {
    "@type": "BreadcrumbList",
    itemListElement: items.map((c, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: c.name,
      item: c.url,
    })),
  };
}

/* ---------------------------------------------------------------- product */

/**
 * The three availability words the shop publishes, and the only three.
 *
 * /llms.txt tells a reader "Availability is one of InStock,
 * LimitedAvailability, OutOfStock", and /api/catalog uses all three; the page
 * markup used to know only two, so nine variants read LimitedAvailability in
 * the feed and InStock in the same product's structured data. `low` is the
 * shop's own "last ones" flag and carries no number.
 */
function availabilityUrl(inStock: boolean, low = false): string {
  if (!inStock) return `${SCHEMA}/OutOfStock`;
  return low ? `${SCHEMA}/LimitedAvailability` : `${SCHEMA}/InStock`;
}

function amount(value: number): string {
  return value.toFixed(2);
}

function days(range: [number, number]): JsonLdObject {
  return { "@type": "QuantitativeValue", minValue: range[0], maxValue: range[1], unitCode: "DAY" };
}

/**
 * Shipping as the shop has it configured. The rate describes a single-item
 * order, so a product priced at or above the free-shipping threshold carries a
 * zero rate. deliveryTime appears only once handling and transit days are set.
 */
export function shippingDetails(shipping: StorefrontConfig["shipping"] | null | undefined, basisPriceCad: number): JsonLdObject | null {
  if (!shipping || !shipping.countries?.length) return null;
  const free = shipping.free_over_cad > 0 && basisPriceCad >= shipping.free_over_cad;
  const policy = shopPolicy();
  const node: JsonLdObject = {
    "@type": "OfferShippingDetails",
    shippingRate: {
      "@type": "MonetaryAmount",
      value: amount(free ? 0 : shipping.flat_cad),
      currency: CURRENCY,
    },
    shippingDestination: shipping.countries.map((c) => ({ "@type": "DefinedRegion", addressCountry: c })),
  };
  if (policy.handlingDays && policy.transitDays) {
    node.deliveryTime = {
      "@type": "ShippingDeliveryTime",
      handlingTime: days(policy.handlingDays),
      transitTime: days(policy.transitDays),
    };
  }
  return node;
}

/** A return policy only exists once the owner has set the window. */
export function merchantReturnPolicy(): JsonLdObject | null {
  const policy = shopPolicy();
  // A demonstration shop's window is a proposal, so search data gets none.
  if (policy.returnWindowDays === null || demoNote("en") !== "") return null;
  const node: JsonLdObject = {
    "@type": "MerchantReturnPolicy",
    applicableCountry: COUNTRY,
    returnPolicyCategory: `${SCHEMA}/MerchantReturnFiniteReturnWindow`,
    merchantReturnDays: policy.returnWindowDays,
  };
  if (policy.returnMethod) node.returnMethod = `${SCHEMA}/${policy.returnMethod}`;
  if (policy.returnFees) node.returnFees = `${SCHEMA}/${policy.returnFees}`;
  return node;
}

export type ProductJsonLdInput = {
  lang: Lang;
  /** A full Product carries variants and becomes an AggregateOffer. */
  product: Product | ProductSummary;
  /** Absolute canonical URL of the product page in this language. */
  url: string;
  /** Absolute image URLs. The field is omitted while a product has no photo. */
  images?: string[];
  /** Overrides the description taken from the product record. */
  description?: string;
  /** shipping block from api.config(); omitted when not passed. */
  shipping?: StorefrontConfig["shipping"] | null;
  /** Seller name; defaults to the shop. */
  sellerName?: string;
};

function hasVariants(p: Product | ProductSummary): p is Product {
  return Array.isArray((p as Product).variants);
}

/**
 * A product. Availability follows the catalogue exactly: in stock maps to
 * InStock, sold out to OutOfStock. Ratings and reviews are never emitted.
 * priceValidUntil is left out because no price expiry is recorded anywhere.
 */
export function product(input: ProductJsonLdInput): JsonLdObject {
  const { lang, url } = input;
  const p = input.product;
  const seller = { "@id": storeId() };
  const returns = merchantReturnPolicy();
  const shipping = shippingDetails(input.shipping, p.price_from_cad);
  const condition = `${SCHEMA}/NewCondition`;

  const offerBase = (price: number, inStock: boolean, sku?: string, low = false): JsonLdObject => {
    const offer: JsonLdObject = {
      "@type": "Offer",
      url,
      priceCurrency: CURRENCY,
      price: amount(price),
      availability: availabilityUrl(inStock, low),
      itemCondition: condition,
      seller,
    };
    if (sku) offer.sku = sku;
    if (shipping) offer.shippingDetails = shipping;
    if (returns) offer.hasMerchantReturnPolicy = returns;
    return offer;
  };

  const allLive = hasVariants(p) ? p.variants.filter((v) => v.availability.in_stock) : [];
  let offers: JsonLdObject;
  if (hasVariants(p) && p.variants.length > 1) {
    offers = {
      "@type": "AggregateOffer",
      url,
      priceCurrency: CURRENCY,
      lowPrice: amount(p.price_from_cad),
      highPrice: amount(p.price_to_cad),
      offerCount: p.variants.length,
      // The product reads "limited" only when every variant still on the shelf
      // is flagged low, which is the rule lib/geo.ts availabilityOf() applies.
      availability: availabilityUrl(p.in_stock, allLive.length > 0 && allLive.every((v) => v.availability.low)),
      offers: p.variants.map((v) => offerBase(v.price_cad, v.availability.in_stock, v.sku, v.availability.low)),
    };
  } else {
    const only = hasVariants(p) ? p.variants[0] : undefined;
    offers = offerBase(only?.price_cad ?? p.price_from_cad, only?.availability.in_stock ?? p.in_stock, only?.sku, only?.availability.low ?? false);
  }

  const description =
    input.description ??
    (hasVariants(p) ? pick(lang, p.description, p.description_uk) : pick(lang, p.subtitle, p.subtitle_uk));

  const node: JsonLdObject = {
    "@type": "Product",
    "@id": `${url}#product`,
    name: pick(lang, p.title, p.title_uk),
    url,
    offers,
  };
  if (description) node.description = description;
  if (input.images?.length) node.image = input.images;
  // A product-level SKU exists only when the product is a single variant;
  // otherwise the SKU belongs to each variant offer above.
  if (hasVariants(p) && p.variants.length === 1) node.sku = p.variants[0].sku;
  if (p.maker) node.brand = { "@type": "Brand", name: pick(lang, p.maker.name, p.maker.name_uk) };
  if (input.sellerName) node.manufacturer = { "@type": "Organization", name: input.sellerName };
  if (hasVariants(p) && pick(lang, p.material, p.material_uk)) node.material = pick(lang, p.material, p.material_uk);
  // Country of origin is claimed only for the two origins that mean it.
  if (p.origin === "HANDMADE_UA" || p.origin === "MADE_UA") {
    node.countryOfOrigin = { "@type": "Country", name: "UA" };
  }
  return node;
}

/* --------------------------------------------------------------- item list */

export type ItemListInput = {
  /** Absolute URL of the listing page. */
  url: string;
  name: string;
  items: { url: string; name: string }[];
};

/** A collection, category or maker listing. */
export function itemList(input: ItemListInput): JsonLdObject | null {
  if (!input.items.length) return null;
  return {
    "@type": "ItemList",
    "@id": `${input.url}#list`,
    name: input.name,
    url: input.url,
    numberOfItems: input.items.length,
    itemListElement: input.items.map((item, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: item.name,
      url: item.url,
    })),
  };
}

/* ----------------------------------------------------------- local business */

export type LocalBusinessInput = {
  lang: Lang;
  name?: string;
  /** Absolute URL of the page describing pickup. */
  url?: string;
  /**
   * The pickup point as `pickupPlace()` in lib/seo.ts resolves it, and null on a
   * deployment whose checkout takes no pickup order. A caller passes what it read
   * from the live storefront config; omitting it reads SHOP_PICKUP_ADDRESS_JSON
   * alone, which claims a place without checking that the shop still offers it.
   */
  place?: PickupPlace | null;
};

/**
 * The Ottawa pickup point. Opt-in: it returns null until an address is
 * configured, because a wrong address on a map is worse than no address, and the
 * caller is expected to withhold the place while pickup is switched off. See
 * docs/OWNER-ACTIONS.md.
 *
 * The address is marked up field by field when SHOP_PICKUP_ADDRESS_JSON carries
 * the parts, and as the one line the shop publishes when PICKUP_ADDRESS is all
 * there is — schema.org takes either, and a line the owner typed is a fact,
 * where a street and a city guessed out of it by splitting on commas would not
 * be. `openingHours` needs the machine format ("Mo-Su 09:00-17:00"), so it comes
 * from the JSON alone; the free text in PICKUP_HOURS is printed on the pages
 * instead of being reshaped into a claim.
 */
export function localBusiness(input: LocalBusinessInput): JsonLdObject | null {
  const place = input.place === undefined ? pickupPlace(null) : input.place;
  if (!place) return null;
  const postal = place.postal;
  const node: JsonLdObject = {
    "@type": "Store",
    "@id": `${siteUrl()}/#pickup`,
    name: input.name ?? t(input.lang).brand,
    url: input.url ?? `${siteUrl()}${href(input.lang, "/")}`,
    parentOrganization: { "@id": storeId() },
    address: postal
      ? {
          "@type": "PostalAddress",
          streetAddress: postal.streetAddress,
          addressLocality: postal.addressLocality,
          addressRegion: postal.addressRegion,
          postalCode: postal.postalCode,
          addressCountry: postal.addressCountry ?? COUNTRY,
        }
      : place.line,
    areaServed: { "@type": "Country", name: COUNTRY },
  };
  if (postal?.telephone) node.telephone = postal.telephone;
  if (postal?.openingHours?.length) node.openingHours = postal.openingHours;
  return node;
}
