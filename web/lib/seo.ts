/**
 * The single place that knows the storefront's URLs and the shape of its metadata.
 *
 * URL law (mirrors web/proxy.ts): English is served without a language prefix
 * (`/shop`), Ukrainian lives under `/uk` (`/uk/shop`), and `/en/...` is a 308 to
 * the bare path. So the English URL is the x-default, and `href()` from
 * `lib/i18n.ts` is the one function that turns a locale-free path into a
 * language path — this module never re-implements it.
 *
 * Everything a crawler could read as a promise (return window, handling and
 * transit days, a pickup address) is configuration with an unset default, so an
 * unconfigured value is left out of the page instead of guessed. See
 * `shopPolicy()` and docs/OWNER-ACTIONS.md.
 */
import type { Metadata } from "next";
import { href, t } from "@/lib/i18n";
import type { Lang } from "@/lib/i18n";
import { clampText } from "@/lib/i18n.pages";
import { seoText } from "@/lib/i18n.seo";

/** Used when WEB_BASE_URL is unset, which is the local dev case. */
export const FALLBACK_BASE_URL = "http://localhost:3010";

/** The social card the /og route draws. */
export const OG_IMAGE_SIZE = { width: 1200, height: 630 } as const;

/** Search-result and filtered listing pages: crawlable, out of the index. */
export const NOINDEX_FOLLOW: Metadata["robots"] = { index: false, follow: true };

/** Absolute origin of the storefront, without a trailing slash. */
export function siteUrl(): string {
  const raw = (process.env.WEB_BASE_URL || FALLBACK_BASE_URL).trim();
  const withScheme = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
  return withScheme.replace(/\/+$/, "");
}

/** Hostname of the storefront, for display on the social card. */
export function siteHost(): string {
  try {
    return new URL(siteUrl()).host;
  } catch {
    return new URL(FALLBACK_BASE_URL).host;
  }
}

/**
 * WEB_INDEXABLE gates the whole site. It stays false until the owner says the
 * shop is live, which keeps a staging deployment out of search results.
 */
export function isIndexable(): boolean {
  return process.env.WEB_INDEXABLE === "true";
}

/** Leading slash, no trailing slash, query string preserved. */
function normalisePath(path: string): string {
  const raw = path && path.length ? path : "/";
  const withSlash = raw.startsWith("/") ? raw : `/${raw}`;
  const cut = withSlash.indexOf("?");
  const pathname = cut === -1 ? withSlash : withSlash.slice(0, cut);
  const query = cut === -1 ? "" : withSlash.slice(cut);
  const trimmed = pathname.length > 1 ? pathname.replace(/\/+$/, "") : "/";
  return `${trimmed}${query}`;
}

/** Absolute URL of one locale-free path in one language. */
export function urlFor(lang: Lang, path: string): string {
  return `${siteUrl()}${href(lang, normalisePath(path))}`;
}

/** The canonical URL of this page in this language. */
export function canonicalFor(lang: Lang, path: string): string {
  return urlFor(lang, path);
}

/**
 * hreflang set for one page: en, uk, and x-default pointing at the English
 * (unprefixed) URL.
 *
 * A page that asks not to be indexed gets the canonical alone. Google ignores
 * hreflang that points at a noindex URL and reports the pair as a conflicting
 * signal, and /bag, /checkout and /order are noindex, nofollow and Disallowed
 * in robots.txt on top of that.
 */
export function alternatesFor(lang: Lang, path: string, withLanguages = true): NonNullable<Metadata["alternates"]> {
  const canonical = canonicalFor(lang, path);
  // The three machine surfaces are otherwise discoverable only by convention:
  // nothing on the site links /llms.txt, and it is not in the sitemap. One
  // rel=alternate makes it reachable by following a link.
  const types = { "text/markdown": "/llms.txt" };
  if (!withLanguages) return { canonical, types };
  const en = urlFor("en", path);
  return {
    canonical,
    languages: {
      en,
      uk: urlFor("uk", path),
      "x-default": en,
    },
    types,
  };
}

/**
 * Last segment of a path, which for a product page is the slug the product
 * tile charts its motif from. So a card and its page show the same motif.
 */
export function seedFromPath(path: string): string {
  const clean = normalisePath(path).split("?")[0];
  const segments = clean.split("/").filter(Boolean);
  return segments[segments.length - 1] ?? "home";
}

export type OgImageInput = {
  /** Line drawn large on the card. */
  title: string;
  /** Product or page slug: picks which counted motif is charted. */
  seed?: string;
  /** Small line above the title; defaults to the localised kicker. */
  kicker?: string;
  lang?: Lang;
};

/** URL of the generated social card for a page. */
export function ogUrl(input: OgImageInput): string {
  const params = new URLSearchParams();
  params.set("title", input.title);
  if (input.seed) params.set("seed", input.seed);
  if (input.kicker) params.set("kicker", input.kicker);
  if (input.lang) params.set("lang", input.lang);
  return `${siteUrl()}/og?${params.toString()}`;
}

export type BuildMetadataInput = {
  lang: Lang;
  /** Locale-free path, e.g. "/product/kosiv-nyzynka-blouse" or "/shop?collection=heritage". */
  path: string;
  title: string;
  description: string;
  /** Absolute image URL. Defaults to the generated social card for this page. */
  image?: string;
  imageAlt?: string;
  /** Motif seed for the default social card. */
  ogSeed?: string;
  ogKicker?: string;
  /** Pass NOINDEX_FOLLOW for search and filtered listings. */
  robots?: Metadata["robots"];
  openGraphType?: "website" | "article";
};

/**
 * A complete Metadata object: canonical, hreflang alternates, Open Graph and a
 * large Twitter card. While WEB_INDEXABLE is off every page carries noindex,
 * matching the site-wide rule in app/[lang]/layout.tsx.
 */
export function buildMetadata(input: BuildMetadataInput): Metadata {
  // One place decides how long a description may be, so a fixed string cannot
  // slip past the limit the generated ones are cut to.
  const { lang, path, title } = input;
  const description = clampText(input.description);
  const url = canonicalFor(lang, path);
  const image =
    input.image ??
    ogUrl({ title, seed: input.ogSeed ?? seedFromPath(path), kicker: input.ogKicker, lang });
  const alt = input.imageAlt ?? seoText(lang).ogAlt(title);
  const brand = t(lang).brand;
  const robots = input.robots ?? (isIndexable() ? undefined : { index: false, follow: false });
  // A page the shop asks nobody to follow does not advertise its twin.
  const privatePage = typeof input.robots === "object" && input.robots !== null && "follow" in input.robots && input.robots.follow === false;

  return {
    title,
    description,
    metadataBase: new URL(siteUrl()),
    alternates: alternatesFor(lang, path, !privatePage),
    robots,
    openGraph: {
      type: input.openGraphType ?? "website",
      url,
      siteName: brand,
      title,
      description,
      locale: lang === "uk" ? "uk_UA" : "en_CA",
      alternateLocale: lang === "uk" ? ["en_CA"] : ["uk_UA"],
      images: [{ url: image, width: OG_IMAGE_SIZE.width, height: OG_IMAGE_SIZE.height, alt }],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [{ url: image, alt }],
    },
  };
}

/* ------------------------------------------------------------------ policy */

export type PostalAddressConfig = {
  streetAddress: string;
  addressLocality: string;
  addressRegion?: string;
  postalCode?: string;
  addressCountry?: string;
  telephone?: string;
  /** schema.org openingHours strings, e.g. ["Mo-Su 00:00-23:59"]. */
  openingHours?: string[];
};

export type ShopPolicy = {
  /** SHOP_RETURN_WINDOW_DAYS — days a buyer has to start a return. */
  returnWindowDays: number | null;
  /** SHOP_RETURN_METHOD — ReturnByMail or ReturnInStore. */
  returnMethod: "ReturnByMail" | "ReturnInStore" | null;
  /** SHOP_RETURN_FEES — FreeReturn or ReturnShippingFees. */
  returnFees: "FreeReturn" | "ReturnShippingFees" | null;
  /** SHOP_HANDLING_DAYS — business days before a parcel leaves, e.g. "1-3". */
  handlingDays: [number, number] | null;
  /** SHOP_TRANSIT_DAYS — business days in transit, e.g. "2-7". */
  transitDays: [number, number] | null;
  /** SHOP_PICKUP_ADDRESS_JSON — the Ottawa pickup point, as a PostalAddress. */
  pickupAddress: PostalAddressConfig | null;
};

function parseDayRange(value: string | undefined): [number, number] | null {
  if (!value) return null;
  const parts = value.split("-").map((p) => Number(p.trim()));
  const [min, max] = parts.length === 1 ? [parts[0], parts[0]] : parts;
  if (!Number.isFinite(min) || !Number.isFinite(max) || min < 0 || max < min) return null;
  return [min, max];
}

/**
 * The field names SHOP_PICKUP_ADDRESS_JSON may use, most specific first.
 *
 * The fulfillment core reads the same setting through `_address_from_json` in
 * app/services/locker.py and accepts `line1`/`city`/`province`/`postal_code`
 * beside the schema.org names — which is the shape docs and .env.example show.
 * Reading only the schema.org names here meant the documented example
 * configured the API and left the storefront's structured data empty.
 */
const ADDRESS_FIELDS = {
  streetAddress: ["streetAddress", "line1", "street1", "street"],
  addressLocality: ["addressLocality", "city"],
  addressRegion: ["addressRegion", "province", "region", "state"],
  postalCode: ["postalCode", "postal_code", "postcode"],
  addressCountry: ["addressCountry", "country"],
  telephone: ["telephone", "phone"],
} as const;

function parseAddress(value: string | undefined): PostalAddressConfig | null {
  if (!value || !value.trim()) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
  const source = parsed as Record<string, unknown>;
  const read = (names: readonly string[]): string | undefined => {
    for (const name of names) {
      const raw = source[name];
      if (typeof raw === "string" && raw.trim()) return raw.trim();
    }
    return undefined;
  };
  const streetAddress = read(ADDRESS_FIELDS.streetAddress);
  const addressLocality = read(ADDRESS_FIELDS.addressLocality);
  // A street with no city is not an address a person or a map can use, and
  // half an address in structured data is worse than none.
  if (!streetAddress || !addressLocality) return null;
  const openingHours = Array.isArray(source.openingHours)
    ? source.openingHours.filter((h): h is string => typeof h === "string" && h.trim() !== "")
    : [];
  return {
    streetAddress,
    addressLocality,
    addressRegion: read(ADDRESS_FIELDS.addressRegion),
    postalCode: read(ADDRESS_FIELDS.postalCode),
    addressCountry: read(ADDRESS_FIELDS.addressCountry),
    telephone: read(ADDRESS_FIELDS.telephone),
    openingHours: openingHours.length ? openingHours : undefined,
  };
}

/**
 * Shipping and return promises, read from configuration. Every field defaults
 * to null, and a null field is omitted from the page's structured data — a
 * shop that has not set a return window does not claim one.
 */
export function shopPolicy(): ShopPolicy {
  const window = Number(process.env.SHOP_RETURN_WINDOW_DAYS);
  const method = process.env.SHOP_RETURN_METHOD;
  const fees = process.env.SHOP_RETURN_FEES;
  return {
    returnWindowDays: Number.isFinite(window) && window > 0 ? window : null,
    returnMethod: method === "ReturnByMail" || method === "ReturnInStore" ? method : null,
    returnFees: fees === "FreeReturn" || fees === "ReturnShippingFees" ? fees : null,
    handlingDays: parseDayRange(process.env.SHOP_HANDLING_DAYS),
    transitDays: parseDayRange(process.env.SHOP_TRANSIT_DAYS),
    pickupAddress: parseAddress(process.env.SHOP_PICKUP_ADDRESS_JSON),
  };
}

/* ------------------------------------------------------------ pickup point */

/**
 * The pickup config as the API publishes it, narrowed to the three printable
 * values. lib/api.ts owns the full `PickupConfig`; this module takes the shape
 * it needs so a page may hand it either.
 */
export type PickupAddressSource = {
  address: string | null;
  hours: string | null;
  note: string | null;
};

/**
 * Where the locker is, resolved once for the whole storefront.
 *
 * Two settings hold one address. `PICKUP_ADDRESS` is the fulfillment core's,
 * and it is the line every page already prints, because the API sends it back
 * on /v1/storefront/config. `SHOP_PICKUP_ADDRESS_JSON` is the storefront's, and
 * it is the only one that carries the address field by field — street, city,
 * province, postal code — which is what structured data needs.
 *
 * The core already falls back from the first to the second, so an owner who
 * filled in only the JSON gets a working checkout. This is the other half of
 * that promise: an owner who filled in only `PICKUP_ADDRESS` gets pages and
 * structured data that carry the address too, instead of a shop whose checkout
 * offers a pickup its own pages call switched off.
 */
export type PickupPlace = {
  /** Field by field, from SHOP_PICKUP_ADDRESS_JSON. Null when the shop published only a line. */
  postal: PostalAddressConfig | null;
  /** The address as one printable line — what every page shows. */
  line: string;
};

/** One printable line out of a structured address, in the order it is read aloud. */
export function addressLine(address: PostalAddressConfig): string {
  return [address.streetAddress, address.addressLocality, address.addressRegion, address.postalCode]
    .map((part) => (part ?? "").trim())
    .filter(Boolean)
    .join(", ");
}

/**
 * The pickup point both halves of the shop agree on, or null while neither
 * setting names one.
 *
 * `line` prefers the API's own string, so /about, /shipping, the FAQ and the
 * order page cannot print two different streets; the JSON stays the richer
 * source for the structured data, which is the only place that needs the parts.
 * Whether pickup is offered at all is a separate question — `pickup.enabled` on
 * the storefront config answers it, and a caller that has not checked it must
 * not publish this.
 */
export function pickupPlace(source: PickupAddressSource | null | undefined): PickupPlace | null {
  const postal = parseAddress(process.env.SHOP_PICKUP_ADDRESS_JSON);
  const line = (source?.address ?? "").trim() || (postal ? addressLine(postal) : "");
  if (!line) return null;
  return { postal, line };
}
