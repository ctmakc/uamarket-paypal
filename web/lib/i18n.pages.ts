/**
 * Strings and description builders for the storefront's own pages.
 *
 * `web/lib/i18n.ts` belongs to the orchestrator and `web/lib/i18n.seo.ts` holds
 * the social-card wording, so the page-level SEO strings live here, in English
 * and Ukrainian.
 *
 * Every description a page hands to a search engine is assembled from data the
 * shop already publishes on the page itself: a product's subtitle, technique
 * and workshop; a maker's craft, region and story; a collection's lede. The
 * fixed sentences below repeat only what the shared dictionary and DESIGN.md
 * already state — Ottawa base, Canada-wide shipping — and none of them counts,
 * prices or otherwise describes the seeded assortment as the shop's real stock.
 * The carrier is named here only once the owner has named it, through
 * `shipPhrase()`: these strings used to hard-code "Canada Post", so an owner who
 * set SHOP_CARRIER got a site that said one thing and search snippets that said
 * another.
 *
 * Locker pickup follows the same rule, and it is the reason two of these take a
 * `pickup` flag. A description is a promise made where nobody can read the rest
 * of the page, and this deployment's checkout refuses a pickup order while no
 * locker address is configured — so /shop and /about offered a method the shop
 * answered 400 to. The flag comes from `pickup.enabled` on the live storefront
 * config, the same key the checkout, the FAQ and the shipping page branch on. It
 * defaults to false: a caller that could not read the config promises nothing.
 */
import type { Maker, Product } from "@/lib/api";
import { carrierIsSet, fromBase, say, shopPolicy } from "@/lib/content";
import { catalogueStatus } from "@/lib/geo";
import type { Lang } from "@/lib/i18n";
import { pick, t } from "@/lib/i18n";

/**
 * A search result renders roughly 155–160 characters and cuts the rest with an
 * ellipsis. The limit was 200, so 45 of the 98 pages — every maker page in both
 * languages and most product pages — lost the end of their last sentence, which
 * is where the region and the workshop's story sat. Cutting here instead means
 * the shop chooses which half survives.
 */
export const DESCRIPTION_LIMIT = 155;

/**
 * How a description names the way a parcel travels. While SHOP_CARRIER is
 * unset the shop has not chosen a carrier — the fulfillment core reads one back
 * off the postage rate it buys — so the phrase says shipping instead.
 */
export function shipPhrase(lang: Lang): string {
  const name = shopPolicy().carrier;
  return carrierIsSet()
    ? say(lang, { en: `${name}${fromBase("en")} across Canada`, uk: `${name}${fromBase("uk")} по всій Канаді` })
    : say(lang, { en: `Shipping${fromBase("en")} across Canada`, uk: `Доставка${fromBase("uk")} по всій Канаді` });
}

/** The same phrase inside a sentence. A carrier's name keeps its capital. */
export function shipPhraseInline(lang: Lang): string {
  const phrase = shipPhrase(lang);
  return carrierIsSet() ? phrase : phrase.charAt(0).toLowerCase() + phrase.slice(1);
}

/** Collapse whitespace, cut on a word boundary, mark the cut. */
export function clampText(text: string, limit: number = DESCRIPTION_LIMIT): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= limit) return clean;
  const cut = clean.slice(0, limit - 1);
  const space = cut.lastIndexOf(" ");
  const kept = space > limit * 0.6 ? cut.slice(0, space) : cut;
  return `${kept.replace(/[\s,.;:·—-]+$/u, "")}…`;
}

/** End a fragment as a sentence, unless it already ends as one. */
function sentence(text: string): string {
  const clean = text.trim();
  if (!clean) return "";
  return /[.!?…»"']$/u.test(clean) ? clean : `${clean}.`;
}

const strings = {
  en: {
    /** aria-label of the breadcrumb row. */
    crumbLabel: "Breadcrumb",
    /** First step of every breadcrumb trail. */
    home: "Home",
    shopDescription:
      "Vyshyvanky, rushnyky, motanky and Opishnia clay from named Ukrainian workshops. Every piece names its maker, its region and how it was made.",
    searchDescription: (query: string) => `Shop search for “${query}” at UA Market.`,
    categoryDescription: (title: string, ship: string, pickup = false) =>
      pickup
        ? `${title} from named Ukrainian workshops. ${ship}, or pickup from the locker.`
        : `${title} from named Ukrainian workshops. ${ship}.`,
    makerFilterDescription: (name: string) => `Everything in the shop made by ${name}.`,
    madeBy: (name: string, region: string) => `Made by ${name} in ${region}.`,
    aboutDescription: (ship: string, pickup = false) =>
      pickup
        ? `Where the goods come from, what the three origin marks mean, how ${ship} and locker pickup work, and how you pay.`
        : `Where the goods come from, what the three origin marks mean, how ${ship} works, and how you pay.`,
    bagDescription: "The pieces you have put in your bag, with the subtotal.",
    checkoutDescription: "Contact details, delivery choice and payment method for your order.",
    orderLookupDescription: "Open an order's status page with the order number from your email and the email you used.",
    orderStatusDescription: "Status, items, payment and tracking for one order.",
  },
  uk: {
    crumbLabel: "Навігаційний ланцюжок",
    home: "Головна",
    shopDescription:
      "Вишиванки, рушники, мотанки та опішнянська глина від українських майстерень. Кожна річ називає майстра, регіон і те, як її зроблено.",
    searchDescription: (query: string) => `Пошук «${query}» у крамниці UA Market.`,
    categoryDescription: (title: string, ship: string, pickup = false) =>
      pickup
        ? `${title} від українських майстерень із іменами. ${ship} або самовивіз із локера.`
        : `${title} від українських майстерень із іменами. ${ship}.`,
    makerFilterDescription: (name: string) => `Усе в крамниці, що зробила майстерня «${name}».`,
    madeBy: (name: string, region: string) => `Майстерня «${name}», ${region}.`,
    aboutDescription: (ship: string, pickup = false) =>
      pickup
        ? `Звідки речі, як читати три знаки походження, як працюють ${ship} і самовивіз із локера, і як оплатити замовлення.`
        : `Звідки речі, як читати три знаки походження, як працює ${ship}, і як оплатити замовлення.`,
    bagDescription: "Речі, які ви поклали в кошик, і сума за них.",
    checkoutDescription: "Контакти, спосіб доставки та спосіб оплати для вашого замовлення.",
    orderLookupDescription: "Відкрийте сторінку стану замовлення за номером із листа та поштою, яку ви вказали.",
    orderStatusDescription: "Стан, товари, оплата та трекінг одного замовлення.",
  },
};

export type PageStrings = typeof strings.en;

export function tp(lang: Lang): PageStrings {
  return lang === "uk" ? (strings.uk as PageStrings) : strings.en;
}

/**
 * A product, described with the product's own words: what the shop calls it in
 * one line, who made it and where, and the technique on the tag.
 */
export function productDescription(lang: Lang, p: Product): string {
  const lead = pick(lang, p.subtitle, p.subtitle_uk) || pick(lang, p.description, p.description_uk);
  const maker = p.maker
    ? tp(lang).madeBy(pick(lang, p.maker.name, p.maker.name_uk), pick(lang, p.maker.region, p.maker.region_uk))
    : "";
  const technique = pick(lang, p.technique, p.technique_uk);
  return clampText([sentence(lead), maker, sentence(technique)].filter(Boolean).join(" "));
}

/**
 * A workshop, described by its craft, its region and the start of its story.
 *
 * While the catalogue is the seeded one the description opens by naming the
 * workshop as made up: this string is what a link preview and an answer engine
 * quote, and neither of them sees the mark the page carries beside the name.
 */
export function makerDescription(lang: Lang, m: Maker): string {
  const craft = pick(lang, m.craft, m.craft_uk);
  const region = pick(lang, m.region, m.region_uk);
  const story = pick(lang, m.story, m.story_uk);
  const madeUp = catalogueStatus() === "placeholder" ? `${t(lang).makers.example}.` : "";
  return clampText([madeUp, sentence(craft), sentence(region), story].filter(Boolean).join(" "));
}

export default strings;
