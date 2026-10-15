/**
 * The content model behind the pre-purchase pages: FAQ, shipping, care,
 * privacy and terms.
 *
 * Three rules hold this file together.
 *
 * 1. Content is data, not prose buried in JSX. Every entry carries both
 *    languages, so a page can never render half a translation, and the FAQ
 *    entries can be fed to a FAQPage JSON-LD builder later without rewriting.
 * 2. Every number or promise (shipping price, free threshold, tax provinces,
 *    payment methods, pickup) comes from /v1/storefront/config, which the API
 *    already serves. Nothing that varies is typed into a page.
 * 3. What the config does not carry lives in POLICY_DEFAULTS below, is
 *    overridable by an environment variable, and is listed in
 *    docs/OWNER-ACTIONS.md as a value the owner must confirm before launch.
 *    A policy the owner has never set (a return window, a refund clock, how
 *    long a locker bay holds an order) stays null and the page prints an
 *    honest "write to us" line in its place instead of a made-up rule.
 */
import type { StorefrontConfig, Product, ProductSummary } from "@/lib/api";
import { money } from "@/lib/api";
import type { Lang } from "@/lib/i18n";
import { PROVINCES, plural, t } from "@/lib/i18n";
import { mailNotice } from "@/lib/i18n.mail";
import type { PickupCopyInput, PickupPolicyCopy } from "@/lib/i18n.pickup";
import { PICKUP_UNKNOWN, pickupAnswer, pickupPolicy, pickupUnavailable } from "@/lib/i18n.pickup";

/* ------------------------------------------------------------------ types */

export type Bilingual = { en: string; uk: string };

export function say(lang: Lang, value: Bilingual): string {
  return lang === "uk" ? value.uk : value.en;
}

export type PolicyRow = {
  label: Bilingual;
  value: Bilingual;
  href?: string;
  /** Where a figure comes from, when it is a default rather than a setting. */
  note?: Bilingual;
};

export type PolicyBlock =
  | { kind: "text"; body: Bilingual }
  | { kind: "list"; items: Bilingual[] }
  | { kind: "rows"; layout: "figures" | "notes"; rows: PolicyRow[] }
  | { kind: "qa"; entries: FaqEntry[] };

export type PolicySection = { id: string; heading: Bilingual; blocks: PolicyBlock[] };

export type PolicyDoc = {
  id: "faq" | "shipping" | "care" | "privacy" | "terms";
  title: Bilingual;
  lede: Bilingual;
  description: Bilingual;
  sections: PolicySection[];
};

export type FaqEntry = {
  id: string;
  question: Bilingual;
  /** The first sentence answers the question on its own: these entries also feed answer engines. */
  answer: Bilingual;
  link?: { label: Bilingual; path: string };
};

/* --------------------------------------------------------------- defaults */

/**
 * Values the storefront config does not carry. Each one is a DEFAULT WE CHOSE,
 * not a fact the owner confirmed; each is listed in docs/OWNER-ACTIONS.md.
 * Override any of them with the environment variable named beside it.
 * `null` means "the owner has not set this", and the pages then print a
 * "write to us" line instead of inventing a rule.
 */
export const POLICY_DEFAULTS = {
  /**
   * Working days between payment and handover to the courier.
   * Read from SHOP_HANDLING_DAYS ("1-3", the same variable the structured data
   * uses) first, then SHOP_PROCESSING_DAYS_MIN / SHOP_PROCESSING_DAYS_MAX.
   */
  processingDaysMin: 1,
  processingDaysMax: 3,
  /**
   * Transit time after handover. SHOP_DELIVERY_ESTIMATE / SHOP_DELIVERY_ESTIMATE_UK
   * carry a sentence of your own; SHOP_TRANSIT_DAYS ("2-7", again shared with the
   * structured data) carries a range. Unset: the pages point at the carrier and the
   * tracking number and promise nothing.
   */
  deliveryEstimate: null as Bilingual | null,
  /** SHOP_RETURN_WINDOW_DAYS — days after delivery in which a return is accepted. Unset: the pages ask the customer to write. */
  returnWindowDays: null as number | null,
  /** SHOP_REFUND_BUSINESS_DAYS — working days between an accepted return and the refund. Unset: the pages ask the customer to write. */
  refundBusinessDays: null as number | null,
  /** SHOP_LOCKER_HOLD_DAYS — days a locker bay holds a packed order. Unset: the pages say the period is not published. */
  lockerHoldDays: null as number | null,
  /** SHOP_ORDER_RECORD_YEARS — how long paid-order records are kept for bookkeeping. */
  orderRecordYears: 7,
  /** SHOP_MESSAGE_RETENTION_MONTHS — how long customer email threads are kept. */
  messageRetentionMonths: 24,
  /**
   * SHOP_CANCELLED_RETENTION_MONTHS — how long a cancelled, unpaid order is
   * kept. It used to borrow the email-thread setting, so the privacy page
   * published a period no setting governed.
   */
  cancelledRetentionMonths: 24,
  /** SHOP_CARRIER — the carrier named on the shipping page. */
  carrier: "Canada Post",
  /** SHOP_BASE_PLACE / SHOP_BASE_PLACE_UK — where parcels leave from. Unset: no place is named anywhere. */
  basePlace: null as Bilingual | null,
  /** SHOP_GOVERNING_PLACE / SHOP_GOVERNING_PLACE_UK — the law the terms name. */
  governingPlace: { en: "Ontario, Canada", uk: "Онтаріо, Канада" } as Bilingual,
  /** SHOP_LEGAL_NAME / SHOP_LEGAL_NAME_UK — the registered seller. Unset: the pages print the trading name and say the legal name is not published. */
  legalName: null as Bilingual | null,
  tradingName: "UA Market",
} as const;

/** The day this copy was written. Shown on the policy pages so a reader knows how old the text is. */
export const POLICY_WRITTEN_ISO = "2026-09-02";

export function writtenDate(lang: Lang): string {
  return new Date(`${POLICY_WRITTEN_ISO}T12:00:00Z`).toLocaleDateString(lang === "uk" ? "uk-UA" : "en-CA", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

export type ShopPolicy = {
  processingDays: { min: number; max: number };
  deliveryEstimate: Bilingual | null;
  transitDays: [number, number] | null;
  returnWindowDays: number | null;
  refundBusinessDays: number | null;
  lockerHoldDays: number | null;
  orderRecordYears: number;
  messageRetentionMonths: number;
  cancelledRetentionMonths: number;
  carrier: string;
  basePlace: Bilingual | null;
  governingPlace: Bilingual;
  seller: Bilingual;
  sellerIsLegalName: boolean;
};

/** Ukrainian "from <place>" needs the genitive; the places the shop is likely to name are listed. */
const UK_FROM_PLACE: Record<string, string> = { "Оттава, Онтаріо": "Оттави (Онтаріо)", "Оттава": "Оттави" };

/**
 * " from Ottawa, Ontario" / " з Оттави (Онтаріо)", with its leading space, or "" while
 * SHOP_BASE_PLACE is unset. Every sentence that names where parcels leave from is built
 * with this, so an unset place removes the city from all of them at once.
 */
export function fromBase(lang: Lang, place: Bilingual | null = shopPolicy().basePlace): string {
  if (!place) return "";
  if (lang === "uk") {
    const genitive = UK_FROM_PLACE[place.uk];
    return genitive ? ` з ${genitive}` : ` (місце відправлення: ${place.uk})`;
  }
  return ` from ${place.en}`;
}

/** The site tagline, naming where parcels leave from only when SHOP_BASE_PLACE is set. */
export function taglineFor(lang: Lang): string {
  const from = fromBase(lang);
  const base = t(lang).tagline;
  return from ? base.replace(/\.$/, `${from}.`) : base;
}

/** The hero sub-line: "Shipped across Canada[ from X][, or picked up from our locker]." */
export function heroSubFor(lang: Lang, pickup: boolean): string {
  const d = t(lang).home;
  const from = fromBase(lang);
  if (!from) return pickup ? d.heroSubPickup : d.heroSub;
  return pickup
    ? d.heroSubPickup.replace(lang === "uk" ? "Доставка по Канаді" : "Shipped across Canada", (m) => `${m}${from}`)
    : d.heroSub.replace(/\.$/, `${from}.`);
}

/** The footer colophon, with the shop's place when one is configured. */
export function colophonFor(lang: Lang): string {
  const place = shopPolicy().basePlace;
  const base = t(lang).footer.colophon;
  if (!place) return base;
  return lang === "uk" ? `${base} · Зроблено: ${place.uk}` : `${base} · Made in ${place.en}`;
}

function envRaw(name: string): string {
  return (process.env[name] ?? "").trim();
}

function envNumber(name: string, fallback: number | null): number | null {
  const raw = envRaw(name);
  if (!raw) return fallback;
  if (/^(none|unset|off)$/i.test(raw)) return null;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? Math.round(n) : fallback;
}

/** "1-3" or "2", the shape web/lib/seo.ts already reads for the same values. */
function envDayRange(name: string): [number, number] | null {
  const raw = envRaw(name);
  if (!raw) return null;
  const parts = raw.split("-").map((part) => Number(part.trim()));
  const [min, max] = parts.length === 1 ? [parts[0], parts[0]] : parts;
  if (!Number.isFinite(min) || !Number.isFinite(max) || min < 0 || max < min) return null;
  return [Math.round(min), Math.round(max)];
}

function envText(name: string, fallback: string): string {
  return envRaw(name) || fallback;
}

function envBilingual(name: string, fallback: Bilingual | null): Bilingual | null {
  const en = envRaw(name);
  const uk = envRaw(`${name}_UK`);
  if (!en && !uk) return fallback;
  return { en: en || uk, uk: uk || en };
}

/** Read the policy values once per render. Server side only: these are plain server env vars. */
export function shopPolicy(): ShopPolicy {
  const legalName = envBilingual("SHOP_LEGAL_NAME", POLICY_DEFAULTS.legalName);
  const handling = envDayRange("SHOP_HANDLING_DAYS");
  return {
    processingDays: handling
      ? { min: handling[0], max: handling[1] }
      : {
          min: envNumber("SHOP_PROCESSING_DAYS_MIN", POLICY_DEFAULTS.processingDaysMin) ?? POLICY_DEFAULTS.processingDaysMin,
          max: envNumber("SHOP_PROCESSING_DAYS_MAX", POLICY_DEFAULTS.processingDaysMax) ?? POLICY_DEFAULTS.processingDaysMax,
        },
    deliveryEstimate: envBilingual("SHOP_DELIVERY_ESTIMATE", POLICY_DEFAULTS.deliveryEstimate),
    transitDays: envDayRange("SHOP_TRANSIT_DAYS"),
    returnWindowDays: envNumber("SHOP_RETURN_WINDOW_DAYS", POLICY_DEFAULTS.returnWindowDays),
    refundBusinessDays: envNumber("SHOP_REFUND_BUSINESS_DAYS", POLICY_DEFAULTS.refundBusinessDays),
    lockerHoldDays: envNumber("SHOP_LOCKER_HOLD_DAYS", POLICY_DEFAULTS.lockerHoldDays),
    orderRecordYears: envNumber("SHOP_ORDER_RECORD_YEARS", POLICY_DEFAULTS.orderRecordYears) ?? POLICY_DEFAULTS.orderRecordYears,
    messageRetentionMonths:
      envNumber("SHOP_MESSAGE_RETENTION_MONTHS", POLICY_DEFAULTS.messageRetentionMonths) ?? POLICY_DEFAULTS.messageRetentionMonths,
    cancelledRetentionMonths:
      envNumber("SHOP_CANCELLED_RETENTION_MONTHS", POLICY_DEFAULTS.cancelledRetentionMonths) ?? POLICY_DEFAULTS.cancelledRetentionMonths,
    carrier: envText("SHOP_CARRIER", POLICY_DEFAULTS.carrier),
    basePlace: envBilingual("SHOP_BASE_PLACE", POLICY_DEFAULTS.basePlace),
    governingPlace: envBilingual("SHOP_GOVERNING_PLACE", POLICY_DEFAULTS.governingPlace) as Bilingual,
    seller: legalName ?? { en: POLICY_DEFAULTS.tradingName, uk: POLICY_DEFAULTS.tradingName },
    sellerIsLegalName: legalName !== null,
  };
}

/* ------------------------------------------------------- what is confirmed */

/**
 * Which POLICY_DEFAULTS the owner has actually set.
 *
 * The pages say which figures are still unconfirmed.
 * Half of them come from the table above instead, so each of those says so
 * where it is printed rather than passing as a setting.
 */
export function carrierIsSet(): boolean {
  return envRaw("SHOP_CARRIER") !== "";
}

export function handlingIsSet(): boolean {
  return envRaw("SHOP_HANDLING_DAYS") !== "" || envRaw("SHOP_PROCESSING_DAYS_MIN") !== "" || envRaw("SHOP_PROCESSING_DAYS_MAX") !== "";
}

export function orderRecordYearsIsSet(): boolean {
  return envRaw("SHOP_ORDER_RECORD_YEARS") !== "";
}

export function messageRetentionIsSet(): boolean {
  return envRaw("SHOP_MESSAGE_RETENTION_MONTHS") !== "";
}

export function cancelledRetentionIsSet(): boolean {
  return envRaw("SHOP_CANCELLED_RETENTION_MONTHS") !== "";
}

/**
 * When the locker bay can be reached, in both languages. Unset everywhere: unpublished.
 *
 * The hours live in two settings, one on each side of the shop: the API reads
 * `PICKUP_HOURS` (falling back to `SHOP_PICKUP_HOURS`) and sends the result back on
 * /v1/storefront/config, and the storefront reads `SHOP_PICKUP_HOURS` itself. A page that
 * has the config passes it, so a deployment that set only the API's setting prints the
 * hours here too rather than saying they are not published while /shipping prints them.
 * `SHOP_PICKUP_HOURS_UK` only translates whichever string won.
 */
export function pickupHours(cfg?: StorefrontConfig | null): Bilingual | null {
  const en = (cfg?.pickup.hours ?? "").trim() || envRaw("SHOP_PICKUP_HOURS");
  const uk = envRaw("SHOP_PICKUP_HOURS_UK");
  if (!en && !uk) return null;
  return { en: en || uk, uk: uk || en };
}

/**
 * Everything the FAQ and the shipping page say about locker pickup comes through here,
 * so the two pages cannot describe the same locker differently.
 *
 * The hours are the one value with two homes: the API reads PICKUP_HOURS (falling back to
 * SHOP_PICKUP_HOURS, which these pages have always read), and the storefront additionally
 * holds a Ukrainian rendering the API cannot produce. The API's string is therefore the
 * single source of the hours themselves, and SHOP_PICKUP_HOURS_UK only translates it.
 */
function pickupInput(cfg: StorefrontConfig | null): PickupCopyInput | null {
  if (!cfg) return null;
  return {
    cfg: cfg.pickup,
    mail: mailNotice(cfg).email,
    contact: cfg.contact_email ?? null,
    shipping: { flat: biMoney(cfg.shipping.flat_cad), free: biMoney(cfg.shipping.free_over_cad) },
    hoursUk: envRaw("SHOP_PICKUP_HOURS_UK") || null,
  };
}

/**
 * The locker copy for a page that summarises pickup rather than documenting it — /about.
 *
 * Null means the page prints nothing about pickup: either the checkout will not take a
 * pickup order on this deployment, or the settings could not be read and nothing
 * about pickup is knowable. The sentences themselves are the shipping page's, so the two
 * pages cannot describe the same locker differently.
 */
export function pickupCopy(cfg: StorefrontConfig | null): PickupPolicyCopy | null {
  const input = pickupInput(cfg);
  if (!input || !input.cfg.enabled) return null;
  return pickupPolicy(input);
}

/**
 * A figure the owner has set is still a proposal while the shop runs as a demonstration
 * (SHOP_CATALOGUE_STATUS is not "live"): the return window then carries the same note.
 */
export function demoNote(lang: Lang): string {
  return (process.env.SHOP_CATALOGUE_STATUS ?? "").trim().toLowerCase() === "live" ? "" : ` (${UNCONFIRMED[lang]})`;
}

/** The note a defaulted figure carries, in the words lib/geo.ts already uses. */
export const UNCONFIRMED: Bilingual = {
  en: "not confirmed yet",
  uk: "ще не підтверджено",
};

/**
 * How a page may name the carrier.
 *
 * The software never chooses one: the fulfillment core reads the carrier back
 * off the postage rate it bought. While SHOP_CARRIER is unset the pages
 * therefore describe the carrier instead of naming a company — which matters
 * most in the privacy policy, where the sentence names a recipient of a
 * customer's name, address and phone.
 *
 * `nom` is the subject form, `obj` the form that follows a preposition, which
 * Ukrainian needs and English does not.
 */
export function carrier(policy: ShopPolicy): { nom: Bilingual; obj: Bilingual } {
  if (carrierIsSet()) {
    const both = { en: policy.carrier, uk: policy.carrier };
    return { nom: both, obj: both };
  }
  return {
    nom: { en: "the carrier the label is bought from", uk: "перевізник, у якого куплено етикетку" },
    obj: { en: "the carrier the label is bought from", uk: "перевізника, у якого куплено етикетку" },
  };
}

/* -------------------------------------------------------------- formatting */

function biMoney(value: number): Bilingual {
  return { en: money(value, "en"), uk: money(value, "uk") };
}

function joinBilingual(parts: Bilingual[]): Bilingual {
  if (parts.length === 0) return { en: "", uk: "" };
  if (parts.length === 1) return parts[0];
  const en = `${parts.slice(0, -1).map((p) => p.en).join(", ")} and ${parts[parts.length - 1].en}`;
  const uk = `${parts.slice(0, -1).map((p) => p.uk).join(", ")} та ${parts[parts.length - 1].uk}`;
  return { en, uk };
}

/** Country codes the shipping config can carry. Anything unknown prints as its code. */
const COUNTRY_NAMES: Record<string, Bilingual> = {
  CA: { en: "Canada", uk: "Канада" },
  US: { en: "the United States", uk: "США" },
};

function countryNames(codes: string[]): Bilingual {
  return joinBilingual(codes.map((code) => COUNTRY_NAMES[code] ?? { en: code, uk: code }));
}

function provinceNames(codes: string[]): Bilingual {
  const parts = codes.map((code) => {
    const found = PROVINCES.find((p) => p.code === code);
    return found ? { en: found.en, uk: found.uk } : { en: code, uk: code };
  });
  return joinBilingual(parts);
}

/**
 * The payment methods the shop has switched on, as one phrase. Exported so the
 * home page and /about read the same list the FAQ, the terms and checkout do,
 * instead of a fixed sentence that can drift away from the settings.
 */
export function paymentList(cfg: StorefrontConfig | null, withAddress = false): Bilingual | null {
  const parts = paymentParts(cfg, withAddress);
  return parts.length ? joinBilingual(parts) : null;
}

function paymentParts(cfg: StorefrontConfig | null, withAddress = true): Bilingual[] {
  const methods = cfg?.payment_methods ?? [];
  const parts: Bilingual[] = [];
  if (methods.includes("ETRANSFER")) {
    const to = withAddress ? cfg?.etransfer_email : null;
    parts.push({
      en: to ? `Interac e-Transfer to ${to}` : "Interac e-Transfer",
      uk: to ? `Interac e-Transfer на ${to}` : "Interac e-Transfer",
    });
  }
  if (methods.includes("PAYPAL"))
    parts.push(
      cfg?.paypal?.env === "sandbox"
        ? { en: "PayPal (sandbox: test money, nothing real moves)", uk: "PayPal (пісочниця: тестові гроші, нічого справжнього не рухається)" }
        : { en: "PayPal", uk: "PayPal" },
    );
  if (methods.includes("STRIPE"))
    parts.push(
      cfg?.payment_test_mode
        ? { en: "card (test payment, no money moves)", uk: "картка (тестова оплата, гроші не рухаються)" }
        : { en: "card payment through Stripe", uk: "оплата карткою через Stripe" },
    );
  if (methods.includes("INVOICE")) parts.push({ en: "payment details sent to you by arrangement", uk: "реквізити, надіслані вам за домовленістю" });
  return parts;
}

function daysWord(n: number): Bilingual {
  const mod10 = n % 10;
  const mod100 = n % 100;
  const uk = mod10 === 1 && mod100 !== 11 ? "день" : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? "дні" : "днів";
  return { en: n === 1 ? "day" : "days", uk };
}

function businessDays(n: number): Bilingual {
  return { en: `${n} business ${n === 1 ? "day" : "days"}`, uk: `${n} ${plural(n, "робочий день", "робочі дні", "робочих днів")}` };
}

function years(n: number): Bilingual {
  return { en: `${n} ${n === 1 ? "year" : "years"}`, uk: `${n} ${plural(n, "рік", "роки", "років")}` };
}

function months(n: number): Bilingual {
  return { en: `${n} ${n === 1 ? "month" : "months"}`, uk: `${n} ${plural(n, "місяць", "місяці", "місяців")}` };
}

/**
 * What the pages say about time in transit: the owner's own sentence if there is
 * one, then a configured range, and otherwise no promise at all.
 */
function transitSentence(policy: ShopPolicy): Bilingual | null {
  if (policy.deliveryEstimate) return policy.deliveryEstimate;
  if (!policy.transitDays) return null;
  const [min, max] = policy.transitDays;
  const range = min === max ? `${min}` : `${min}–${max}`;
  const c = carrier(policy);
  return {
    en: `The shop's estimate for time in transit is ${range} working ${max === 1 ? "day" : "days"} with ${c.obj.en}.`,
    uk: `Крамниця оцінює час у дорозі в ${range} робочих днів через ${c.obj.uk}.`,
  };
}

/* --------------------------------------------------------------------- FAQ */

export type FaqGroup = { id: string; heading: Bilingual; entries: FaqEntry[] };

/**
 * Every answer opens with a sentence that answers its own question, so the
 * entry survives being read alone, in a search result or in a JSON-LD block.
 */
export function faqGroups(cfg: StorefrontConfig | null, policy: ShopPolicy = shopPolicy()): FaqGroup[] {
  const flat = cfg ? biMoney(cfg.shipping.flat_cad) : null;
  const free = cfg ? biMoney(cfg.shipping.free_over_cad) : null;
  const pay = joinBilingual(paymentParts(cfg));
  const taxCodes = cfg?.tax.configured_provinces ?? [];
  const taxNames = provinceNames(taxCodes);
  const hold = cfg?.hold_minutes ?? 60;
  const excluded = cfg?.shipping.excluded_provinces ?? [];
  const excludedFaq: Bilingual = excluded.length
    ? { en: ` except in ${provinceNames(excluded).en} for now`, uk: ` (крім провінції ${provinceNames(excluded).uk} поки що)` }
    : { en: "", uk: "" };
  const pickupOn = cfg?.pickup.enabled ?? false;
  const pickupCopy = pickupInput(cfg);
  const contact = cfg?.contact_email ?? null;
  const mail = mailNotice(cfg);
  const proc = policy.processingDays;
  const procRange = proc.min === proc.max ? `${proc.min}` : `${proc.min}–${proc.max}`;
  const transit = transitSentence(policy);

  const ordering: FaqEntry[] = [
    {
      id: "how-to-order",
      question: { en: "How do I place an order?", uk: "Як оформити замовлення?" },
      answer: {
        en: "Choose the size or option on the product page, add the piece to the bag, and open checkout. Checkout asks for your email, your name, a delivery choice and a payment method, then shows the total with shipping and tax before anything is placed.",
        uk: "Оберіть розмір або варіант на сторінці товару, додайте річ до кошика та відкрийте оформлення. Там ви вкажете пошту, ім'я, спосіб доставки й спосіб оплати, а сума з доставкою та податком з'явиться ще до того, як замовлення буде оформлене.",
      },
      link: { label: { en: "Shop", uk: "Крамниця" }, path: "/shop" },
    },
    {
      id: "payment-methods",
      question: { en: "How can I pay?", uk: "Як можна заплатити?" },
      answer: pay.en
        ? {
            en: `The shop accepts ${pay.en}. An order is created unpaid and waits for the money; packing starts once the payment lands.`,
            uk: `Крамниця приймає: ${pay.uk}. Замовлення створюється неоплаченим і чекає на гроші; пакування починається, коли оплата надходить.`,
          }
        : {
            en: "The shop is not taking payments yet. Ask us how to pay before you order.",
            uk: "Крамниця ще не приймає оплату. Запитайте в нас, як заплатити, перш ніж замовляти.",
          },
    },
    {
      id: "unpaid-order",
      question: { en: "What happens between placing an order and paying for it?", uk: "Що відбувається між оформленням і оплатою?" },
      answer: {
        en: `The order sits as unpaid and keeps its number, its prices and its total. Placing it sets the pieces aside for ${hold} minutes while you pay; after that an unpaid order holds nothing aside, so a one-of-a-kind piece goes to whoever pays first.`,
        uk: `Замовлення лежить неоплаченим і зберігає свій номер, ціни та суму. Оформлення відкладає речі на ${hold} хв, поки ви платите; після цього неоплачене замовлення нічого не резервує, тож унікальна річ дістанеться тому, хто заплатить першим.`,
      },
    },
    {
      id: "cancel-order",
      question: { en: "Can I cancel an order?", uk: "Чи можна скасувати замовлення?" },
      answer: {
        en: "Yes, while it is unpaid: open the order status page with the order number and the email you used, then press Cancel this order." +
          (contact ? ` After a payment has arrived, write to ${contact} with the order number.` : " After a payment has arrived, only the shop can cancel it, and this demonstration shop has no contact address yet."),
        uk: "Так, поки воно неоплачене: відкрийте сторінку стану замовлення за номером і поштою, які ви вказували, і натисніть «Скасувати замовлення»." +
          (contact ? ` Коли оплата вже надійшла, напишіть на ${contact} й вкажіть номер замовлення.` : " Після оплати скасувати замовлення може лише крамниця, а ця демонстраційна крамниця ще не має контактної адреси."),
      },
      link: { label: { en: "Order status", uk: "Стан замовлення" }, path: "/order" },
    },
    {
      id: "find-order",
      question: { en: "Where do I see the state of my order?", uk: "Де подивитися стан замовлення?" },
      answer: {
        en: "The order status page shows it: enter the order number and the email you used at checkout. The page carries the state, the items, the totals, the payment instructions while payment is due, and the tracking number once the parcel is handed over.",
        uk: "На сторінці стану замовлення: введіть номер замовлення та пошту, яку вказали при оформленні. Там видно стан, товари, суми, платіжні вказівки, поки оплата очікується, і трек-номер, щойно посилку передано.",
      },
      link: { label: { en: "Order status", uk: "Стан замовлення" }, path: "/order" },
    },
  ];

  const shipping: FaqEntry[] = [
    {
      id: "shipping-cost",
      question: { en: "What does shipping cost?", uk: "Скільки коштує доставка?" },
      answer:
        flat && free
          ? {
              en: `Shipping is a flat ${flat.en} anywhere in Canada, and it is free once the bag reaches ${free.en}. Checkout shows the exact amount before you place the order.`,
              uk: `Доставка коштує ${flat.uk} у будь-яку точку Канади, а від ${free.uk} у кошику вона безкоштовна. Точну суму видно на сторінці оформлення ще до підтвердження замовлення.`,
            }
          : {
              en: "Checkout shows the shipping amount before you place the order.",
              uk: "Суму доставки видно на сторінці оформлення до підтвердження замовлення.",
            },
      link: { label: { en: "Shipping and pickup", uk: "Доставка та самовивіз" }, path: "/shipping" },
    },
    {
      id: "where-we-ship",
      question: { en: "Where do you ship?", uk: "Куди ви відправляєте?" },
      answer: {
        en: `Checkout accepts Canadian addresses${excludedFaq.en}, and parcels leave${fromBase("en", policy.basePlace)} with ${carrier(policy).obj.en}.` +
          (contact ? ` For an address outside Canada, write to ${contact} before ordering.` : " Addresses outside Canada are not accepted."),
        uk: `Оформлення приймає канадські адреси${excludedFaq.uk}, а посилки вирушають${fromBase("uk", policy.basePlace)} через ${carrier(policy).obj.uk}.` +
          (contact ? ` Щодо адреси поза Канадою напишіть на ${contact} до замовлення.` : " Адреси поза Канадою не приймаються."),
      },
    },
    {
      id: "how-long",
      question: { en: "How long does an order take?", uk: "Скільки часу займає замовлення?" },
      answer: {
        en: `An order in stock leaves within ${procRange} working ${proc.max === 1 ? "day" : "days"} of the payment arriving${handlingIsSet() ? "" : ` — ${UNCONFIRMED.en}`}. ` +
          (transit
            ? `${transit.en} A piece embroidered to order takes the time its product page names in the origin note.`
            : `Transit time after that belongs to ${carrier(policy).obj.en}, and the tracking number appears on your order page the moment the parcel is handed over. A piece embroidered to order takes the time its product page names in the origin note.`),
        uk: `Замовлення з наявних речей вирушає протягом ${procRange} робочих днів після надходження оплати${handlingIsSet() ? "" : ` — ${UNCONFIRMED.uk}`}. ` +
          (transit
            ? `${transit.uk} Річ, яку вишивають на замовлення, потребує стільки часу, скільки вказано в примітці про походження на її сторінці.`
            : `Час у дорозі далі залежить від ${carrier(policy).obj.uk}, а трек-номер з'являється на сторінці вашого замовлення, щойно посилку передано. Річ, яку вишивають на замовлення, потребує стільки часу, скільки вказано в примітці про походження на її сторінці.`),
      },
      link: { label: { en: "Shipping and pickup", uk: "Доставка та самовивіз" }, path: "/shipping" },
    },
    {
      // What this answer may promise is decided in lib/i18n.pickup.ts, from the live
      // config: where the locker is, when the code is issued, how it reaches the buyer on
      // a shop that cannot send email, how long it lives, and what to do when it expires.
      // While no address is configured the answer says pickup is unavailable and points
      // at the courier, which is exactly what the checkout does.
      id: "pickup",
      question: { en: "Can I pick the order up instead?", uk: "Чи можна забрати замовлення особисто?" },
      answer: pickupCopy ? pickupAnswer(pickupCopy) : PICKUP_UNKNOWN,
      link: pickupOn ? { label: { en: "Shipping and pickup", uk: "Доставка та самовивіз" }, path: "/shipping" } : undefined,
    },
    {
      id: "tax",
      question: { en: "Is tax added to the price?", uk: "Чи додається податок до ціни?" },
      answer: taxCodes.length
        ? {
            en: `Sales tax is added at checkout for ${taxNames.en}, and the line appears in the order summary before you place the order. Prices on product pages are shown without it.`,
            uk: `Податок із продажу додається під час оформлення для таких провінцій: ${taxNames.uk}; рядок з'являється в підсумку замовлення ще до підтвердження. Ціни на сторінках товарів показані без нього.`,
          }
        : {
            en: "No sales tax is added at checkout at the moment.",
            uk: "Наразі податок із продажу при оформленні не додається.",
          },
    },
  ];

  const pieces: FaqEntry[] = [
    {
      id: "provenance-marks",
      question: { en: "What do the marks beside a product name mean?", uk: "Що означають знаки біля назви товару?" },
      answer: {
        en: "They say how the piece was made, in three levels that we keep apart: a red cross means it was embroidered or made by hand in a named Ukrainian workshop, a running stitch means it was produced in Ukraine with machine embroidery, and a dotted square means Ukrainian design produced abroad. The same mark stands on the tile, on the product page and in the bag.",
        uk: "Вони кажуть, як зроблено річ, за трьома рівнями, які ми не змішуємо: червоний хрестик — вишито або зроблено руками в конкретній українській майстерні, стібок уперед голку — виготовлено в Україні з машинною вишивкою, пунктирний квадрат — український дизайн, виготовлений за кордоном. Той самий знак стоїть на плитці, на сторінці товару та в кошику.",
      },
      link: { label: { en: "How it works", uk: "Як це працює" }, path: "/about" },
    },
    {
      id: "sizing",
      question: { en: "How do I choose a size?", uk: "Як обрати розмір?" },
      answer: {
        en: "Sizes are lettered as the workshop cut them, and the product page lists the ones it can ship. Measurements per size are absent from the catalogue for now" +
          (contact ? `, so write to ${contact} with the piece and your measurements and we ask the workshop for its numbers.` : ", and this demonstration shop has no contact address yet to ask for them."),
        uk: "Розміри позначені літерами так, як їх кроїла майстерня, а сторінка товару показує ті, що є в наявності. Мірок за розмірами в каталозі поки немає" +
          (contact ? `, тож напишіть на ${contact}, назвіть річ і свої мірки — ми запитаємо числа в майстерні.` : ", а ця демонстраційна крамниця ще не має контактної адреси, щоб їх запитати."),
      },
    },
    {
      id: "made-to-order",
      question: { en: "Why does one piece take weeks?", uk: "Чому одна річ робиться тижнями?" },
      answer: {
        en: "Hand embroidery is counted stitch by stitch, and a blouse can hold weeks of work. The origin note under the price carries the workshop's own timing for that piece, and it is the number we work to.",
        uk: "Ручна вишивка робиться хрестик за хрестиком, і в блузі можуть бути тижні роботи. Примітка про походження під ціною містить власний строк майстерні для цієї речі — саме на нього ми й орієнтуємось.",
      },
    },
    {
      id: "chart-instead-of-photo",
      question: { en: "Is the picture on a product a photograph of that piece?", uk: "Чи є зображення на товарі фотографією саме цієї речі?" },
      answer: {
        en: "While the shop runs on the demonstration assortment, each product carries a generated image of the kind of piece described, and the line above the footer says so on every page. A piece with no picture at all shows a cross-stitch chart drawn from its name. Both give way to the workshop's own photograph as soon as it arrives.",
        uk: "Поки крамниця працює на демонстраційному асортименті, кожен товар має згенероване зображення того типу речі, який описано, і рядок над підвалом каже про це на кожній сторінці. Річ зовсім без зображення показує схему для хрестика, побудовану з її назви. І те, і те поступається власній фотографії майстерні, щойно вона надійде.",
      },
    },
    {
      id: "care-short",
      question: { en: "How do I wash an embroidered piece?", uk: "Як прати вишиту річ?" },
      answer: {
        en: "Follow the care line on the product page: it comes from the workshop that made the piece, and it differs between hand-embroidered linen and machine-embroidered cloth. The care page groups those lines by material family.",
        uk: "Дотримуйтесь рядка догляду на сторінці товару: він походить від майстерні, яка зробила річ, і відрізняється для ручної вишивки на льоні та машинної вишивки. Сторінка догляду збирає ці рядки за родинами матеріалів.",
      },
      link: { label: { en: "Care", uk: "Догляд" }, path: "/care" },
    },
  ];

  const afterwards: FaqEntry[] = [
    {
      id: "returns",
      question: { en: "Can I return something?", uk: "Чи можна повернути річ?" },
      answer:
        policy.returnWindowDays !== null
          ? {
              en: `Yes: a piece can be returned within ${policy.returnWindowDays} ${daysWord(policy.returnWindowDays).en} of delivery, unworn and in the state it arrived in${demoNote("en")}.` +
                (contact ? ` Write to ${contact} with the order number first, so the return travels with an answer.` : " This demonstration shop has no contact address yet."),
              uk: `Так: річ можна повернути протягом ${policy.returnWindowDays} ${daysWord(policy.returnWindowDays).uk} після отримання, неношеною й у тому стані, в якому вона прийшла${demoNote("uk")}.` +
                (contact ? ` Спершу напишіть на ${contact} із номером замовлення, щоб повернення йшло разом із відповіддю.` : " Ця демонстраційна крамниця ще не має контактної адреси."),
            }
          : {
              en: "A return window is not published yet, so the answer comes from us case by case." +
                (contact ? ` Write to ${contact} with the order number and what is wrong, and you get an answer about that order.` : " This demonstration shop has no contact address yet."),
              uk: "Строк повернення ще не опубліковано, тож відповідь ми даємо в кожному випадку окремо." +
                (contact ? ` Напишіть на ${contact}, вкажіть номер замовлення й що саме не так — і отримаєте відповідь щодо цього замовлення.` : " Ця демонстраційна крамниця ще не має контактної адреси."),
            },
      link: { label: { en: "Terms", uk: "Умови" }, path: "/terms" },
    },
    {
      id: "damaged",
      question: { en: "The parcel arrived damaged. What now?", uk: "Посилка прийшла пошкодженою. Що робити?" },
      answer: {
        en: "Photograph the parcel and the piece before unpacking further" +
          (contact ? `, then send the photographs to ${contact} with the order number.` : ", and keep them with the order number; this demonstration shop has no contact address yet to send them to.") +
          " The photographs are what a carrier claim is built on, so they matter more than the description.",
        uk: "Сфотографуйте посилку й саму річ, перш ніж розпаковувати далі" +
          (contact ? `, а тоді надішліть фото на ${contact} із номером замовлення.` : ", і збережіть їх разом із номером замовлення; ця демонстраційна крамниця ще не має контактної адреси, куди їх надіслати.") +
          " Саме на фотографіях будується претензія до перевізника, тож вони важливіші за опис словами.",
      },
    },
    {
      id: "handmade-variation",
      question: { en: "Will my piece look exactly like the photograph?", uk: "Чи буде моя річ точно як на фото?" },
      answer: {
        en: "A hand-made piece differs from its photograph in small ways: the weave of home-woven linen, the exact placement of a motif, the shade of the thread. A machine-made piece from the everyday range repeats closely.",
        uk: "Ручна робота трохи відрізняється від фотографії: переплетення домотканого льону, точне розташування мотиву, відтінок нитки. Річ машинного виробництва з повсякденної лінійки повторюється майже точно.",
      },
    },
    {
      id: "privacy-short",
      question: { en: "What do you do with my email and address?", uk: "Що ви робите з моєю поштою та адресою?" },
      answer: {
        en: mail.email
          ? "They are used to fulfil the order and to answer you about it: the address goes on the parcel label, the email carries the order number and the payment instructions. The privacy page says who else sees the data and how long it is kept."
          : "They are used to fulfil the order: the address goes on the parcel label, and the email identifies the order on its status page. The shop sends no email yet. The privacy page says who else sees the data and how long it is kept.",
        uk: mail.email
          ? "Ними користуються, щоб виконати замовлення й відповісти вам щодо нього: адреса потрапляє на наліпку посилки, пошта несе номер замовлення та платіжні вказівки. Сторінка приватності пояснює, хто ще бачить ці дані та скільки вони зберігаються."
          : "Ними користуються, щоб виконати замовлення: адреса потрапляє на наліпку посилки, а пошта разом із номером відкриває сторінку стану замовлення. Листів крамниця поки не надсилає. Сторінка приватності пояснює, хто ще бачить ці дані та скільки вони зберігаються.",
      },
      link: { label: { en: "Privacy", uk: "Приватність" }, path: "/privacy" },
    },
  ];

  return [
    { id: "ordering", heading: { en: "Ordering and payment", uk: "Замовлення та оплата" }, entries: ordering },
    { id: "delivery", heading: { en: "Delivery and pickup", uk: "Доставка та самовивіз" }, entries: shipping },
    { id: "pieces", heading: { en: "The pieces themselves", uk: "Про самі речі" }, entries: pieces },
    { id: "afterwards", heading: { en: "After the parcel arrives", uk: "Після отримання" }, entries: afterwards },
  ];
}

/** Flat list for a FAQPage JSON-LD builder. */
export function faqEntries(cfg: StorefrontConfig | null, policy: ShopPolicy = shopPolicy()): FaqEntry[] {
  return faqGroups(cfg, policy).flatMap((group) => group.entries);
}

export function faqDoc(cfg: StorefrontConfig | null, policy: ShopPolicy = shopPolicy()): PolicyDoc {
  return {
    id: "faq",
    title: { en: "Questions and answers", uk: "Питання та відповіді" },
    lede: {
      en: "What people ask before they buy: how an order is paid, when it leaves Ottawa, what the marks mean, and what happens when something is wrong.",
      uk: "Те, що питають перед покупкою: як оплатити замовлення, коли воно вирушає з Оттави, що означають знаки та що робити, якщо щось не так.",
    },
    // The description is what a search result shows, so it names locker pickup only
    // while the checkout will take a pickup order. Offering a method the shop refuses
    // is the same lie in a snippet as it is on the page.
    description: (cfg?.pickup.enabled ?? false)
      ? {
          en: "Answers about ordering, payment, delivery in Canada, locker pickup, sizing and returns at UA Market.",
          uk: "Відповіді про замовлення, оплату, доставку по Канаді, самовивіз із локера, розміри та повернення в UA Market.",
        }
      : {
          en: "Answers about ordering, payment, delivery in Canada, sizing and returns at UA Market.",
          uk: "Відповіді про замовлення, оплату, доставку по Канаді, розміри та повернення в UA Market.",
        },
    sections: faqGroups(cfg, policy).map((group) => ({
      id: group.id,
      heading: group.heading,
      blocks: [{ kind: "qa", entries: group.entries }],
    })),
  };
}

/* ---------------------------------------------------------------- shipping */

export function shippingDoc(cfg: StorefrontConfig | null, policy: ShopPolicy = shopPolicy()): PolicyDoc {
  const contact = cfg?.contact_email ?? null;
  const mail = mailNotice(cfg);
  const proc = policy.processingDays;
  const procRange = proc.min === proc.max ? `${proc.min}` : `${proc.min}–${proc.max}`;
  const transit = transitSentence(policy);
  const taxCodes = cfg?.tax.configured_provinces ?? [];
  const taxNames = provinceNames(taxCodes);
  const taxIsGstHst = cfg?.tax.mode === "gst_hst_registered";
  const gstNumber = cfg?.tax.gst_number ?? null;
  const excluded = cfg?.shipping.excluded_provinces ?? [];
  const pickupOn = cfg?.pickup.enabled ?? false;
  const pickupCopy = pickupInput(cfg);
  const pickup = pickupCopy && pickupOn ? pickupPolicy(pickupCopy) : null;

  const rateRows: PolicyRow[] = cfg
    ? [
        {
          label: { en: "Flat rate within Canada", uk: "Фіксований тариф по Канаді" },
          value: biMoney(cfg.shipping.flat_cad),
        },
        {
          label: { en: "Free once the bag reaches", uk: "Безкоштовно від суми кошика" },
          value: biMoney(cfg.shipping.free_over_cad),
        },
        {
          label: { en: "Ships to", uk: "Куди відправляємо" },
          value: countryNames(cfg.shipping.countries),
        },
        // Stated here and refused at checkout: a province the shop does not ship to yet.
        ...(excluded.length
          ? [{
              label: { en: "Not shipped to yet", uk: "Поки не доставляємо" },
              value: provinceNames(excluded),
              note: joinBilingual(excluded.map((code) => cfg.shipping.excluded_reasons?.[code] ?? { en: "", uk: "" }).filter((r) => r.en)),
            }]
          : []),
        {
          label: { en: "Leaves from", uk: "Звідки вирушає" },
          value: policy.basePlace ?? { en: "Not published yet", uk: "Ще не опубліковано" },
        },
        // A figure the owner has never set is not a figure. While SHOP_CARRIER
        // is unset the prose above describes the carrier and the table stays
        // quiet, the way the return window already does.
        ...(carrierIsSet()
          ? [{ label: { en: "Carrier", uk: "Перевізник" }, value: { en: policy.carrier, uk: policy.carrier } }]
          : []),
      ]
    : [];

  const sections: PolicySection[] = [
    {
      id: "rates",
      heading: { en: "What delivery costs", uk: "Скільки коштує доставка" },
      blocks: [
        {
          kind: "text",
          body: cfg
            ? {
                en: `Delivery inside Canada is a flat ${money(cfg.shipping.flat_cad, "en")} and becomes free once the bag reaches ${money(cfg.shipping.free_over_cad, "en")}. Checkout prints the amount before the order is placed, and the order page keeps it afterwards.`,
                uk: `Доставка в межах Канади коштує ${money(cfg.shipping.flat_cad, "uk")} і стає безкоштовною, щойно кошик сягає ${money(cfg.shipping.free_over_cad, "uk")}. Сторінка оформлення друкує суму до підтвердження замовлення, а сторінка замовлення зберігає її потім.`,
              }
            : {
                en: "Checkout prints the delivery amount before the order is placed.",
                uk: "Сторінка оформлення друкує суму доставки до підтвердження замовлення.",
              },
        },
        ...(rateRows.length ? ([{ kind: "rows", layout: "figures", rows: rateRows }] as PolicyBlock[]) : []),
      ],
    },
    {
      id: "timing",
      heading: { en: "When the parcel leaves", uk: "Коли посилка вирушає" },
      blocks: [
        {
          kind: "text",
          body: {
            // The same window reaches an answer engine as "1–3 business days …
            // not confirmed yet". A customer read
            // it as a flat commitment, so the clause travels here too.
            en: `An order held in stock is packed and handed over within ${procRange} working ${proc.max === 1 ? "day" : "days"} of the payment arriving${handlingIsSet() ? "" : ` — ${UNCONFIRMED.en}`}. A piece embroidered to order follows the timing in the origin note on its product page, which comes from the workshop.`,
            uk: `Замовлення з наявних речей пакується й передається перевізнику протягом ${procRange} робочих днів після надходження оплати${handlingIsSet() ? "" : ` — ${UNCONFIRMED.uk}`}. Річ, яку вишивають на замовлення, іде за строком із примітки про походження на її сторінці — цей строк називає майстерня.`,
          },
        },
        {
          kind: "text",
          body: transit
            ? {
                en: `${transit.en} The tracking number appears on your order page as soon as the parcel is handed to the courier, and the carrier's own estimate travels with that number.`,
                uk: `${transit.uk} Трек-номер з'являється на сторінці вашого замовлення, щойно посилку передано кур'єру, а власна оцінка перевізника йде разом із цим номером.`,
              }
            : {
                en: `Time in transit after that belongs to ${carrier(policy).obj.en}, so this page publishes no transit promise. The tracking number appears on your order page as soon as the parcel is handed to the courier, and the carrier's own estimate travels with that number.`,
                uk: `Час у дорозі далі залежить від ${carrier(policy).obj.uk}, тож ця сторінка не обіцяє строку доставки. Трек-номер з'являється на сторінці вашого замовлення, щойно посилку передано кур'єру, а власна оцінка перевізника йде разом із цим номером.`,
              },
        },
      ],
    },
    {
      id: "pickup",
      heading: { en: "Locker pickup", uk: "Самовивіз із локера" },
      // The whole section is built from the live config in lib/i18n.pickup.ts. The
      // address, the hours and the door note are printed as the owner typed them and are
      // absent while unset; the code sentence tells the truth about how a code reaches a
      // buyer on a shop that cannot send email; and a shop with no address configured
      // gets the "pickup is unavailable" section instead, matching its checkout.
      blocks: pickup
        ? ([
            { kind: "text", body: pickup.intro },
            { kind: "rows", layout: "notes", rows: pickup.facts },
            { kind: "text", body: pickup.code },
            { kind: "text", body: pickup.expiry },
            {
              kind: "text",
              body:
                policy.lockerHoldDays !== null
                  ? {
                      en: `A bay holds a packed order for ${policy.lockerHoldDays} ${daysWord(policy.lockerHoldDays).en}. After that the order returns to the shelf and we write to you.`,
                      uk: `Комірка тримає спаковане замовлення ${policy.lockerHoldDays} ${daysWord(policy.lockerHoldDays).uk}. Після цього замовлення повертається на полицю, а ми вам пишемо.`,
                    }
                  : {
                      en: "The length of time a bay holds a packed order is not published yet." +
                        (contact ? ` Ask when the code arrives, or write to ${contact}.` : " Ask when the code arrives."),
                      uk: "Скільки часу комірка тримає спаковане замовлення, ще не опубліковано." +
                        (contact ? ` Запитайте, коли прийде код, або напишіть на ${contact}.` : " Запитайте, коли прийде код."),
                    },
            },
            { kind: "text", body: pickup.labelled },
          ] as PolicyBlock[])
        : [{ kind: "text", body: pickupCopy ? pickupUnavailable(pickupCopy) : PICKUP_UNKNOWN }],
    },
    {
      id: "tracking",
      heading: { en: "Tracking and delays", uk: "Відстеження та затримки" },
      blocks: [
        {
          kind: "text",
          body: {
            en: "Your order page is the place where the state of a parcel is visible: open it with the order number and the email you used, and it shows the state, the totals and the tracking number once a shipment exists.",
            uk: "Стан посилки видно на сторінці вашого замовлення: відкрийте її за номером і поштою, які ви вказували, і побачите стан, суми та трек-номер, щойно з'явиться відправлення.",
          },
        },
        {
          kind: "text",
          body: {
            en: `If the tracking stops moving${contact ? `, write to ${contact} with the order number` : ", note the order number"} and the last scan you can see. That is what a claim to ${carrier(policy).obj.en} is built on.${contact ? "" : " This demonstration shop has no contact address yet."}`,
            uk: `Якщо відстеження зупинилося${contact ? `, напишіть на ${contact}, вказавши номер замовлення` : ", збережіть номер замовлення"} та останнє сканування, яке ви бачите. Саме на цьому будується претензія до ${carrier(policy).obj.uk}.${contact ? "" : " Ця демонстраційна крамниця ще не має контактної адреси."}`,
          },
        },
      ],
    },
    {
      id: "tax",
      heading: { en: "Tax at checkout", uk: "Податок при оформленні" },
      blocks: [
        {
          kind: "text",
          body: taxCodes.length
            ? {
                en: taxIsGstHst
                  ? `GST or HST is added at checkout by the province the parcel goes to, as a named line (for example GST 5% in Alberta, HST 13% in Ontario). The line appears in the order summary before you place the order, and the order page and email keep it.${gstNumber ? ` GST/HST registration: ${gstNumber}.` : ""}`
                  : `Sales tax is added at checkout for ${taxNames.en}. The line appears in the order summary, and the order page keeps it.`,
                uk: taxIsGstHst
                  ? `GST або HST додається при оформленні за провінцією, куди їде посилка, окремим рядком (наприклад, GST 5% в Альберті, HST 13% в Онтаріо). Рядок видно в підсумку ще до підтвердження замовлення, а сторінка замовлення й лист його зберігають.${gstNumber ? ` Реєстрація GST/HST: ${gstNumber}.` : ""}`
                  : `Податок із продажу додається при оформленні для таких провінцій: ${taxNames.uk}. Рядок з'являється в підсумку замовлення, а сторінка замовлення його зберігає.`,
              }
            : {
                en: "No sales tax is added at checkout at the moment.",
                uk: "Наразі податок із продажу при оформленні не додається.",
              },
        },
      ],
    },
  ];

  return {
    id: "shipping",
    title: { en: "Shipping and pickup", uk: "Доставка та самовивіз" },
    // The lede used to promise "how the Ottawa locker works" on every deployment,
    // including one where pickup is switched off and the section says so.
    lede: pickupOn
      ? {
          en: `What delivery costs, when a parcel leaves${fromBase("en", policy.basePlace)}, and how the locker works.`,
          uk: `Скільки коштує доставка, коли посилка вирушає${fromBase("uk", policy.basePlace)}, і як працює локер.`,
        }
      : {
          en: `What delivery costs, when a parcel leaves${fromBase("en", policy.basePlace)}, and how a shipment is tracked.`,
          uk: `Скільки коштує доставка, коли посилка вирушає${fromBase("uk", policy.basePlace)}, і як відстежити відправлення.`,
        },
    description: pickupOn
      ? {
          en: "Delivery rates inside Canada, the free-shipping threshold, packing times, locker pickup, tracking and tax.",
          uk: "Тарифи доставки по Канаді, поріг безкоштовної доставки, строки пакування, самовивіз із локера, відстеження та податок.",
        }
      : {
          en: "Delivery rates inside Canada, the free-shipping threshold, packing times, tracking and tax.",
          uk: "Тарифи доставки по Канаді, поріг безкоштовної доставки, строки пакування, відстеження та податок.",
        },
    sections,
  };
}

/* -------------------------------------------------------------------- care */

export type MaterialFamily = {
  id: string;
  heading: Bilingual;
  body: Bilingual;
  /** Matched against the product's category first, then its material line. */
  categories?: string[];
  match?: RegExp;
};

/**
 * The families the catalogue actually contains. The page explains the family;
 * the rule for a piece always comes from that piece's own care line in the API.
 */
export const MATERIAL_FAMILIES: MaterialFamily[] = [
  {
    id: "wound-cloth",
    heading: { en: "Wound cloth: motanky", uk: "Намотана тканина: мотанки" },
    body: {
      en: "A motanka is wound from cloth and thread, and its technique line says the rest: wound, not sewn, with no needle in the doll. Nothing about washing came from the workshop with these pieces, so this page states no rule for them.",
      uk: "Мотанка намотана з тканини й ниток, а решту каже рядок техніки: намотана, не пошита, голка ляльки не торкається. Правил прання майстерня з цими речами не передала, тож ця сторінка їх і не вигадує.",
    },
    categories: ["dolls"],
  },
  {
    id: "clay",
    heading: { en: "Opishnia clay", uk: "Опішнянська глина" },
    body: {
      en: "Opishnia pieces are red earthenware under a lead-free glaze, thrown on the wheel and painted by hand before firing. The care line on each piece says how it takes a dishwasher and what heat does to it.",
      uk: "Опішнянські вироби — це червона глина під поливою без свинцю, витягнута на гончарному крузі й розписана руками до випалу. Рядок догляду на кожній речі каже, як вона переносить посудомийку і що з нею робить різкий нагрів.",
    },
    categories: ["ceramics"],
    match: /clay|глин/i,
  },
  {
    id: "linen",
    heading: { en: "Linen and linen blends", uk: "Льон і суміші з льоном" },
    body: {
      en: "Linen is the ground most embroidered pieces here are worked on: home-woven flax in the hand-made range, mill linen and linen blends in the everyday one. Linen creases, softens with each wash and carries embroidery thread that can shrink at its own rate, which is why the temperature on each piece comes from the workshop that embroidered it.",
      uk: "Льон — основа, на якій вишита більшість тутешніх речей: домоткане полотно в ручній лінійці, фабричний льон і суміші — у повсякденній. Льон мнеться, з кожним пранням м'якшає й тримає вишивальну нитку, яка може сідати у своєму темпі, тому температуру для кожної речі називає та майстерня, що її вишивала.",
    },
    match: /linen|льон/i,
  },
  {
    id: "cotton",
    heading: { en: "Cotton", uk: "Бавовна" },
    body: {
      en: "Cotton covers the children's shirts and dresses and the printed canvas. It takes a warmer machine wash than hand-embroidered linen, and the exact temperature stands on the product page.",
      uk: "Бавовна — це дитячі сорочки й сукні та друкований канвас. Вона витримує тепліше машинне прання, ніж вишитий вручну льон, а точну температуру вказано на сторінці товару.",
    },
    match: /cotton|бавовн/i,
  },
  {
    id: "made-goods",
    heading: { en: "Enamel, metal and paper", uk: "Емаль, метал і папір" },
    body: {
      en: "Pins are zinc alloy under hard enamel, and cards are uncoated board with kraft envelopes. No washing rule came with them from the workshop, and the page lists them below as they stand.",
      uk: "Значки — цинковий сплав під твердою емаллю, листівки — картон без покриття з крафтовими конвертами. Правил прання майстерня для них не передала, і нижче вони перелічені так, як є.",
    },
    match: /enamel|alloy|card|paper|емал|сплав|картон|папір/i,
  },
];

export function familyFor(product: Pick<Product, "category" | "material"> | ProductSummary & { material?: string | null }): MaterialFamily | null {
  const material = ("material" in product ? product.material : null) || "";
  for (const family of MATERIAL_FAMILIES) {
    if (family.categories?.includes(product.category)) return family;
  }
  for (const family of MATERIAL_FAMILIES) {
    if (family.match?.test(material)) return family;
  }
  return MATERIAL_FAMILIES[MATERIAL_FAMILIES.length - 1] ?? null;
}

function careRow(product: Product): PolicyRow {
  return {
    label: { en: product.title, uk: product.title_uk || product.title },
    value: {
      en: [product.material, product.care].filter(Boolean).join(" — "),
      uk: [product.material_uk || product.material, product.care_uk || product.care].filter(Boolean).join(" — "),
    },
    href: `/product/${product.slug}`,
  };
}

/**
 * The care page is built from the catalogue: the material families are ours,
 * every rule inside them is the workshop's own care line as the API serves it.
 */
export function careDoc(cfg: StorefrontConfig | null, products: Product[], policy: ShopPolicy = shopPolicy()): PolicyDoc {
  void policy;
  const contact = cfg?.contact_email ?? null;
  const withCare = products.filter((p) => (p.care || "").trim().length > 0);
  const withoutCare = products.filter((p) => (p.care || "").trim().length === 0);

  const sections: PolicySection[] = [
    {
      id: "where-rules-come-from",
      heading: { en: "Where these rules come from", uk: "Звідки ці правила" },
      blocks: [
        {
          kind: "text",
          body: {
            en: "Every product page carries the care line of the workshop that made the piece. This page groups those lines by material family so a whole family can be read at once, and it adds nothing to them.",
            uk: "Кожна сторінка товару містить рядок догляду від майстерні, яка зробила річ. Ця сторінка групує ці рядки за родинами матеріалів, щоб родину було видно цілком, і нічого до них не додає.",
          },
        },
        {
          kind: "text",
          body: {
            en: "Where a piece has no care line, this page says so and asks you to write, which is what the catalogue actually holds today.",
            uk: "Де в речі немає рядка догляду, сторінка так і каже й просить написати нам — саме такий стан каталогу сьогодні.",
          },
        },
      ],
    },
  ];

  for (const family of MATERIAL_FAMILIES) {
    const rows = withCare.filter((p) => familyFor(p)?.id === family.id).map((p) => careRow(p));
    const blocks: PolicyBlock[] = [{ kind: "text", body: family.body }];
    if (rows.length) blocks.push({ kind: "rows", layout: "notes", rows });
    sections.push({ id: family.id, heading: family.heading, blocks });
  }

  if (withoutCare.length) {
    sections.push({
      id: "no-care-line",
      heading: { en: "Pieces with no care line yet", uk: "Речі, для яких правил ще немає" },
      blocks: [
        {
          kind: "text",
          body: {
            en: "These pieces reached the catalogue without a care line from their workshop." +
              (contact ? ` Write to ${contact} before you clean one and the question goes to the workshop that made it.` : " Follow the care label, and ask the workshop that made it once the shop publishes a contact address."),
            uk: "Ці речі потрапили в каталог без рядка догляду від майстерні." +
              (contact ? ` Напишіть на ${contact}, перш ніж чистити таку річ, і питання піде до майстерні, яка її зробила.` : " Дотримуйтеся етикетки догляду, а питання до майстерні стане можливим, коли крамниця опублікує контактну адресу."),
          },
        },
        {
          kind: "rows",
          layout: "notes",
          rows: withoutCare.map((p) => ({
            label: { en: p.title, uk: p.title_uk || p.title },
            value: {
              en: p.material || "",
              uk: p.material_uk || p.material || "",
            },
            href: `/product/${p.slug}`,
          })),
        },
      ],
    });
  }

  sections.push({
    id: "embroidery",
    heading: { en: "Embroidery, whatever the cloth", uk: "Вишивка, хай яка тканина" },
    blocks: [
      {
        kind: "list",
        items: [
          {
            en: "Iron from the reverse: the stitch keeps its relief and the thread keeps its sheen.",
            uk: "Прасуйте з вивороту: стібок зберігає рельєф, а нитка — блиск.",
          },
          {
            en: "Dry a washed piece flat, so a wet embroidered panel carries no weight of its own.",
            uk: "Випрану річ сушіть горизонтально, щоб мокре вишите полотнище не тягнуло себе вагою.",
          },
          {
            // The catalogue carries a free-text care line and no record that a
            // test was ever run, so the page says where the number came from.
            en: "The temperature on the product page is the one the workshop gave for that piece; a hotter wash is your own experiment.",
            uk: "Температура зі сторінки товару — та, яку для цієї речі назвала майстерня; гарячіше прання буде вашим власним експериментом.",
          },
        ],
      },
    ],
  });

  return {
    id: "care",
    title: { en: "Care", uk: "Догляд" },
    lede: {
      en: "The workshops' own care lines, grouped by what the piece is made of.",
      uk: "Власні правила догляду від майстерень, зібрані за матеріалом речі.",
    },
    description: {
      en: "How to wash, dry and iron linen, cotton, clay and wound-cloth pieces from UA Market, with each workshop's own care line.",
      uk: "Як прати, сушити та прасувати льон, бавовну, глину й мотанки з UA Market — із власним правилом догляду від кожної майстерні.",
    },
    sections,
  };
}

/* ----------------------------------------------------------------- privacy */

export function privacyDoc(cfg: StorefrontConfig | null, policy: ShopPolicy = shopPolicy()): PolicyDoc {
  const contact = cfg?.contact_email ?? null;
  const methods = cfg?.payment_methods ?? [];
  const processors = cfg?.processors ?? [];

  const sections: PolicySection[] = [
    {
      id: "collected",
      heading: { en: "What the shop holds", uk: "Що зберігає крамниця" },
      blocks: [
        {
          kind: "text",
          body: {
            en: "The shop holds what you type into checkout, what an order produces afterwards, and one technical detail the rows below name. Nothing is asked of you beyond the checkout form.",
            uk: "Крамниця зберігає те, що ви вводите під час оформлення, те, що виникає із замовлення далі, і одну технічну деталь, названу в рядках нижче. Понад форму оформлення у вас нічого не запитують.",
          },
        },
        {
          kind: "rows",
          layout: "notes",
          rows: [
            {
              label: { en: "From checkout", uk: "Із форми оформлення" },
              value: {
                en: "Your name, email, phone if you give one, the delivery choice, the shipping address when the order travels, and any note you write.",
                uk: "Ім'я, пошта, телефон, якщо ви його вкажете, спосіб доставки, адреса доставки для відправлення та примітка, яку ви залишите.",
              },
            },
            {
              label: { en: "From the order itself", uk: "Із самого замовлення" },
              value: {
                en: "The order number, its items and prices, the totals, the payment state and the tracking number when a parcel exists.",
                uk: "Номер замовлення, його товари й ціни, суми, стан оплати та трек-номер, коли з'являється посилка.",
              },
            },
            {
              label: { en: "In your browser", uk: "У вашому браузері" },
              value: {
                en: "The bag lives in your browser's local storage and stays on your device. It is not sent anywhere until you place an order.",
                uk: "Кошик живе в локальному сховищі браузера й залишається на вашому пристрої. Він нікуди не надсилається, доки ви не оформите замовлення.",
              },
            },
            {
              // The API rate-limits order placement and order lookup on the
              // caller's IP address, so the shop processes one piece of
              // technical data the itemised list did not name.
              label: { en: "Technical data", uk: "Технічні дані" },
              value: {
                en: "Your IP address reaches the shop with each request and is used briefly to limit repeated attempts at placing an order and at opening an order page. It is not stored with the order.",
                uk: "IP-адреса приходить із кожним запитом і коротко використовується, щоб обмежити повторні спроби оформити замовлення чи відкрити сторінку замовлення. Разом із замовленням вона не зберігається.",
              },
            },
            {
              label: { en: "Trackers", uk: "Трекери" },
              value: {
                en: "The storefront loads no analytics script, no advertising pixel and no third-party tag.",
                uk: "Вітрина не завантажує жодного скрипта аналітики, рекламного пікселя чи стороннього тега.",
              },
            },
          ],
        },
      ],
    },
    {
      id: "why",
      heading: { en: "What it is used for", uk: "Для чого це використовується" },
      blocks: [
        {
          kind: "list",
          items: [
            // The locker half of this line is printed only where a buyer could have
            // chosen a bay. With pickup off, the checkout takes an address and nothing else.
            (cfg?.pickup.enabled ?? false)
              ? { en: "Packing your order and getting it to the address or the locker bay you chose.", uk: "Спакувати замовлення й доправити його на вказану адресу або в бокс локера." }
              : { en: "Packing your order and getting it to the address you gave.", uk: "Спакувати замовлення й доправити його на вказану адресу." },
            { en: "Answering you about that order and matching a payment to it.", uk: "Відповісти вам щодо цього замовлення та зіставити з ним оплату." },
            { en: "Keeping the books: a sold order is an accounting record.", uk: "Вести облік: продане замовлення — це бухгалтерський запис." },
          ],
        },
        {
          kind: "text",
          body: {
            en: "Your address is used for your parcel. The shop runs no mailing list from checkout addresses.",
            uk: "Ваша адреса використовується для вашої посилки. Розсилки з адрес, зібраних при оформленні, крамниця не веде.",
          },
        },
      ],
    },
    {
      id: "who-sees",
      heading: { en: "Who else sees it", uk: "Хто ще це бачить" },
      blocks: [
        {
          kind: "rows",
          layout: "notes",
          rows: [
            {
              label: { en: "The carrier", uk: "Перевізник" },
              value: {
                en: `Your name, address and phone go onto the parcel label and into the system of ${carrier(policy).obj.en}, because that is what moves the parcel.`,
                uk: `Ваше ім'я, адреса й телефон потрапляють на наліпку посилки та в систему ${carrier(policy).obj.uk}, бо саме це рухає посилку.`,
              },
            },
            // The services below are the ones this deployment actually uses, read from the API
            // (/v1/storefront/config `processors`): a service that is not configured is not named.
            ...processors
              .filter((p) => p.kind === "shipping")
              .map((p) => ({
                label: { en: `The label service: ${p.name}`, uk: `Сервіс наліпок: ${p.name}` },
                value: {
                  en: "The same address goes to the service that buys the postage and prints the label. That service runs outside Canada, so a delivery address leaves the country to become a label.",
                  uk: "Та сама адреса йде до сервісу, який купує поштову оплату й друкує наліпку. Цей сервіс працює поза Канадою, тож адреса доставки залишає країну, щоб стати наліпкою.",
                },
              })),
            ...processors
              .filter((p) => p.kind === "email")
              .map((p) => ({
                label: { en: `Order email: ${p.name}`, uk: `Листи про замовлення: ${p.name}` },
                value: {
                  en: "Your email address, your name and the contents of the order pass through the mail service that delivers the shop's order emails.",
                  uk: "Ваша пошта, ім'я та вміст замовлення проходять через поштовий сервіс, який доставляє листи крамниці про замовлення.",
                },
              })),
            ...processors
              .filter((p) => p.kind === "hosting")
              .map((p) => ({
                label: p.name ? { en: `Hosting: ${p.name}`, uk: `Хостинг: ${p.name}` } : { en: "Hosting", uk: "Хостинг" },
                value: p.name
                  ? {
                      en: "The servers the shop runs on hold everything listed above.",
                      uk: "Сервери, на яких працює крамниця, зберігають усе перелічене вище.",
                    }
                  : {
                      en: "The servers the shop runs on hold everything listed above. The hosting provider is not published yet.",
                      uk: "Сервери, на яких працює крамниця, зберігають усе перелічене вище. Хостинг-провайдера ще не опубліковано.",
                    },
              })),
            ...(methods.includes("ETRANSFER")
              ? [
                  {
                    label: { en: "Your bank", uk: "Ваш банк" },
                    value: {
                      en: "An Interac e-Transfer carries your name and your message to us through your own bank, on Interac's terms.",
                      uk: "Interac e-Transfer передає нам ваше ім'я та повідомлення через ваш банк, на умовах Interac.",
                    },
                  },
                ]
              : []),
            ...(methods.includes("PAYPAL")
              ? [
                  {
                    label: { en: "PayPal", uk: "PayPal" },
                    value: {
                      en: "A PayPal payment is approved in PayPal's own window; the shop receives the order and payment ids, never your PayPal password or card.",
                      uk: "Оплату PayPal ви підтверджуєте у власному вікні PayPal; крамниця отримує ідентифікатори замовлення й платежу, а не ваш пароль PayPal чи картку.",
                    },
                  },
                ]
              : []),
            ...(methods.includes("STRIPE") && !cfg?.payment_test_mode
              ? [
                  {
                    label: { en: "Stripe", uk: "Stripe" },
                    value: {
                      en: "A card payment happens on Stripe's own page; the card number never reaches this shop.",
                      uk: "Оплата карткою відбувається на сторінці Stripe; номер картки до цієї крамниці не потрапляє.",
                    },
                  },
                ]
              : []),
          ],
        },
        {
          kind: "text",
          body: {
            en: "The shop sells no data and passes nothing to an advertiser.",
            uk: "Крамниця не продає дані й нічого не передає рекламодавцям.",
          },
        },
      ],
    },
    {
      id: "how-long",
      heading: { en: "How long it is kept", uk: "Скільки це зберігається" },
      blocks: [
        {
          kind: "rows",
          layout: "figures",
          rows: [
            {
              label: { en: "Paid orders and their invoices", uk: "Оплачені замовлення та рахунки до них" },
              value: years(policy.orderRecordYears),
              note: orderRecordYearsIsSet() ? undefined : UNCONFIRMED,
            },
            // No contact address and no outgoing mail: there is no correspondence to keep.
            ...(contact || mailNotice(cfg).email
              ? [
                  {
                    label: { en: "Email threads with customers", uk: "Листування з покупцями" },
                    value: months(policy.messageRetentionMonths),
                    note: messageRetentionIsSet() ? undefined : UNCONFIRMED,
                  },
                ]
              : []),
            {
              // This row used to borrow the email-thread setting, so it
              // published a period no setting governed even nominally.
              label: { en: "Cancelled unpaid orders", uk: "Скасовані неоплачені замовлення" },
              value: months(policy.cancelledRetentionMonths),
              note: cancelledRetentionIsSet() ? undefined : UNCONFIRMED,
            },
          ],
        },
        {
          kind: "text",
          body: {
            en: `A period marked above as not confirmed yet is our proposal, long enough for bookkeeping and for a warranty question about an old order. We'll confirm it before the shop opens. ${contact ? `Ask at ${contact} for the period that applies to your order.` : "This demonstration shop has no contact address yet."}`,
            uk: `Строк із позначкою «ще не підтверджено» — наша пропозиція, розрахована на облік і на питання щодо давнього замовлення. Ми підтвердимо його до відкриття крамниці. ${contact ? `Строк для вашого замовлення запитайте на ${contact}.` : "Ця демонстраційна крамниця ще не має контактної адреси."}`,
          },
        },
      ],
    },
    {
      id: "your-copy",
      heading: { en: "Getting a copy, a correction or a deletion", uk: "Копія, виправлення або видалення" },
      blocks: [
        {
          kind: "text",
          body: {
            en: contact
              ? `Write to ${contact} from the email address on the order and name the order number. You can ask for a copy of everything held about that order, a correction of a wrong detail, or deletion of what bookkeeping no longer needs.`
              : "A copy of what is held, a correction, or a deletion of what bookkeeping no longer needs will be requested by email from the address on the order. This demonstration shop has no contact address yet, so the request has nowhere to go for now.",
            uk: contact
              ? `Напишіть на ${contact} з тієї пошти, що вказана в замовленні, і назвіть номер замовлення. Ви можете попросити копію всього, що зберігається про це замовлення, виправлення помилкової деталі або видалення того, що вже не потрібне для обліку.`
              : "Копію збережених даних, виправлення або видалення того, що вже не потрібне для обліку, можна буде попросити листом із пошти, вказаної в замовленні. Ця демонстраційна крамниця ще не має контактної адреси, тож запит поки нема куди надіслати.",
          },
        },
        {
          kind: "text",
          body: {
            en: "A record that a tax authority may ask for stays until its period above runs out; everything else can go earlier.",
            uk: "Запис, який може знадобитися податковій, лишається до кінця вказаного вище строку; решту можна видалити раніше.",
          },
        },
      ],
    },
  ];

  return {
    id: "privacy",
    title: { en: "Privacy", uk: "Приватність" },
    lede: {
      en: "What the shop holds about you, who else sees it, and how long it stays.",
      uk: "Що крамниця зберігає про вас, хто ще це бачить і скільки воно лишається.",
    },
    description: {
      en: "The data UA Market collects at checkout, who it is shared with, how long it is kept, and how to ask for a copy or a deletion.",
      uk: "Які дані UA Market збирає при оформленні, кому їх передають, скільки вони зберігаються та як попросити копію або видалення.",
    },
    sections,
  };
}

/* ------------------------------------------------------------------- terms */

export function termsDoc(cfg: StorefrontConfig | null, policy: ShopPolicy = shopPolicy()): PolicyDoc {
  const contact = cfg?.contact_email ?? null;
  const pay = joinBilingual(paymentParts(cfg, !cfg?.etransfer_email));
  const currency = cfg?.currency ?? "CAD";
  const currencyPhrase: Bilingual =
    currency === "CAD" ? { en: "Canadian dollars (CAD)", uk: "канадських доларах (CAD)" } : { en: currency, uk: currency };
  const taxCodes = cfg?.tax.configured_provinces ?? [];
  const taxNames = provinceNames(taxCodes);

  const sections: PolicySection[] = [
    {
      id: "seller",
      heading: { en: "Who you are buying from", uk: "У кого ви купуєте" },
      blocks: [
        {
          kind: "text",
          body: {
            en: policy.sellerIsLegalName
              ? `${policy.seller.en} sells the goods on this site${fromBase("en", policy.basePlace)}.${contact ? ` Written questions go to ${contact}.` : ""}`
              : `The shop trades as ${policy.seller.en}${fromBase("en", policy.basePlace)}. The registered name of the seller is not published on this page yet.${contact ? ` Written questions go to ${contact}.` : ""}`,
            uk: policy.sellerIsLegalName
              ? `${policy.seller.uk} продає товари цього сайту${fromBase("uk", policy.basePlace)}.${contact ? ` Письмові питання — на ${contact}.` : ""}`
              : `Крамниця працює під назвою ${policy.seller.uk}${fromBase("uk", policy.basePlace)}. Зареєстровану назву продавця на цій сторінці поки не опубліковано.${contact ? ` Письмові питання — на ${contact}.` : ""}`,
          },
        },
      ],
    },
    {
      id: "prices",
      heading: { en: "Prices and totals", uk: "Ціни та суми" },
      blocks: [
        {
          kind: "text",
          body: {
            en: `Prices are in ${currencyPhrase.en} and stand as shown on the product page. Delivery is added at checkout unless the bag passes the free threshold, and sales tax is added${taxCodes.length ? ` for ${taxNames.en}` : " only where a rate is shown at checkout"}.`,
            uk: `Ціни вказано в ${currencyPhrase.uk} і діють так, як показано на сторінці товару. Доставка додається при оформленні, якщо кошик не сягнув безкоштовного порогу, а податок із продажу додається${taxCodes.length ? ` для таких провінцій: ${taxNames.uk}` : " лише там, де ставку показано при оформленні"}.`,
          },
        },
        {
          kind: "text",
          body: {
            en: "The total shown on the checkout page is the amount you owe. An order keeps the prices it was placed with, even if a price changes afterwards.",
            uk: "Сума, показана на сторінці оформлення, — це те, що ви сплачуєте. Замовлення зберігає ціни, з якими його оформили, навіть якщо ціна потім зміниться.",
          },
        },
      ],
    },
    {
      id: "order",
      heading: { en: "How an order is formed", uk: "Як формується замовлення" },
      blocks: [
        {
          kind: "text",
          body: {
            en: "Placing an order creates it in the unpaid state with its own number. Stock is checked at that moment and again when the order is packed.",
            uk: "Оформлення створює замовлення в неоплаченому стані з власним номером. Наявність перевіряється в цей момент і ще раз під час пакування.",
          },
        },
        {
          kind: "text",
          body: {
            // The software sends three kinds of mail — placed, paid, handoff.
            // A delayed order and a refund send none, and there is no refund
            // mechanism in the code at all, so the terms describe what the shop
            // can perform: the status page shows the delay and a person settles
            // it. See docs/OWNER-ACTIONS.md.
            en: `An unpaid order holds its pieces aside for ${cfg?.hold_minutes ?? 60} minutes after it is placed and nothing after that. If a piece turns out to be unavailable after payment, the order moves to a delayed state, which its own status page shows, and the shop settles it by hand${contact ? ` — write to ${contact} with the order number to ask for a replacement, a wait or your money back for that line` : " — the shop settles a replacement, a wait or a refund for that line; this demonstration shop has no contact address yet"}.`,
            uk: `Неоплачене замовлення відкладає речі на ${cfg?.hold_minutes ?? 60} хв після оформлення, а далі нічого не резервує. Якщо після оплати виявиться, що речі немає, замовлення переходить у стан затримки — його показує власна сторінка замовлення, — і крамниця залагоджує це вручну${contact ? `: напишіть на ${contact}, вказавши номер замовлення, і попросіть заміну, очікування або повернення грошей за цей рядок` : ": заміну, очікування або повернення грошей за цей рядок вирішує крамниця; ця демонстраційна крамниця ще не має контактної адреси"}.`,
          },
        },
      ],
    },
    {
      id: "payment",
      heading: { en: "Payment", uk: "Оплата" },
      blocks: [
        {
          kind: "text",
          body: pay.en
            ? {
                en: `The shop accepts ${pay.en}. Packing starts once the payment arrives, and nothing is dispatched before it.`,
                uk: `Крамниця приймає: ${pay.uk}. Пакування починається після надходження оплати, і до неї нічого не відправляється.`,
              }
            : {
                en: "The shop is not taking payments yet.",
                uk: "Крамниця ще не приймає оплату.",
              },
        },
        ...(cfg?.etransfer_email
          ? ([
              {
                kind: "text",
                body: {
                  en: `An Interac e-Transfer goes to ${cfg.etransfer_email} with the order number as the message, which is how a payment is matched to an order.`,
                  uk: `Interac e-Transfer надсилається на ${cfg.etransfer_email}, а в повідомленні вказується номер замовлення — саме так оплата зіставляється із замовленням.`,
                },
              },
            ] as PolicyBlock[])
          : []),
      ],
    },
    {
      id: "cancelling",
      heading: { en: "Cancelling", uk: "Скасування" },
      blocks: [
        {
          kind: "text",
          body: {
            en: `An unpaid order can be cancelled from its status page at any time before payment. After the payment has arrived, cancellation goes through us${contact ? `: write to ${contact} with the order number` : ", and this demonstration shop has no contact address yet"}, and a piece already packed or handed to the courier follows the return route instead.`,
            uk: `Неоплачене замовлення можна скасувати на сторінці стану будь-коли до оплати. Після надходження оплати скасування йде через нас${contact ? `: напишіть на ${contact} з номером замовлення` : ", а ця демонстраційна крамниця ще не має контактної адреси"}, а річ, уже спакована чи передана кур'єру, іде шляхом повернення.`,
          },
        },
      ],
    },
    {
      id: "returns",
      heading: { en: "Returns and refunds", uk: "Повернення та відшкодування" },
      blocks: [
        {
          kind: "text",
          body:
            policy.returnWindowDays !== null
              ? {
                  en: `A piece can be returned within ${policy.returnWindowDays} ${daysWord(policy.returnWindowDays).en} of delivery, unworn and in the state it arrived in${demoNote("en")}.` +
                    (policy.refundBusinessDays !== null
                      ? ` A refund follows within ${businessDays(policy.refundBusinessDays).en} of the piece arriving back, by the route the payment came in.`
                      : " The refund goes back by the route the payment came in."),
                  uk: `Річ можна повернути протягом ${policy.returnWindowDays} ${daysWord(policy.returnWindowDays).uk} після отримання, неношеною й у тому стані, в якому вона прийшла${demoNote("uk")}.` +
                    (policy.refundBusinessDays !== null
                      ? ` Гроші повертаються протягом ${businessDays(policy.refundBusinessDays).uk} після надходження речі назад, тим самим шляхом, яким прийшла оплата.`
                      : " Гроші повертаються тим самим шляхом, яким прийшла оплата."),
                }
              : {
                  en: "A return window is not published yet, so this page states none." +
                    (contact ? ` Write to ${contact} with the order number and what is wrong, and the answer covers your order.` : " This demonstration shop has no contact address yet."),
                  uk: "Строк повернення ще не опубліковано, тож ця сторінка його не називає." +
                    (contact ? ` Напишіть на ${contact} з номером замовлення й описом проблеми — відповідь стосуватиметься саме вашого замовлення.` : " Ця демонстраційна крамниця ще не має контактної адреси."),
                },
        },
        {
          kind: "text",
          body: {
            en: "A piece that arrives damaged or differs from what you ordered is our matter to settle, whatever a return window says. Photographs of the parcel and the piece are what the settlement is built on.",
            uk: "Річ, яка прийшла пошкодженою або відрізняється від замовленої, — це наша справа, хай який строк повернення. Фотографії посилки й самої речі — те, на чому будується вирішення.",
          },
        },
        {
          kind: "text",
          body: {
            en: "Hand-made pieces vary between copies: the weave of home-woven linen, the placement of a motif, the shade of a thread. That variation is the nature of the goods and stands apart from a fault.",
            uk: "Речі ручної роботи різняться між примірниками: переплетення домотканого льону, розташування мотиву, відтінок нитки. Ця відмінність — природа таких речей, і вона стоїть окремо від дефекту.",
          },
        },
      ],
    },
    {
      id: "law",
      heading: { en: "Law and changes", uk: "Право та зміни" },
      blocks: [
        {
          kind: "text",
          body: {
            en: `These terms are read under the law of ${policy.governingPlace.en}${envRaw("SHOP_GOVERNING_PLACE") ? "" : ` (${UNCONFIRMED.en})`}. This version was written on ${writtenDate("en")}, and an order is held to the version in force on the day it was placed.`,
            uk: `Ці умови читаються за правом ${policy.governingPlace.uk === "Онтаріо, Канада" ? "Онтаріо (Канада)" : policy.governingPlace.uk}${envRaw("SHOP_GOVERNING_PLACE") ? "" : ` (${UNCONFIRMED.uk})`}. Ця версія написана ${writtenDate("uk")}, а замовлення підпорядковується тій версії, що діяла в день оформлення.`,
          },
        },
      ],
    },
  ];

  return {
    id: "terms",
    title: { en: "Terms of sale", uk: "Умови продажу" },
    lede: {
      en: "How an order is formed, paid, cancelled and returned.",
      uk: "Як замовлення оформлюється, оплачується, скасовується та повертається.",
    },
    description: {
      en: "Terms of sale at UA Market: prices, payment, how an order is formed, cancelling, returns and the law they are read under.",
      uk: "Умови продажу UA Market: ціни, оплата, формування замовлення, скасування, повернення та право, за яким вони читаються.",
    },
    sections,
  };
}
