import type { MetadataRoute } from "next";
import { isIndexable, siteUrl } from "@/lib/seo";

// The env is read per request so a container built once behaves correctly in
// staging and in production.
export const dynamic = "force-dynamic";

/**
 * Paths that hold one shopper's own session or order and have nothing to offer
 * an index. English is unprefixed and Ukrainian sits under /uk, so each private
 * path is listed twice; /api is the bridge to the fulfillment core.
 */
const PRIVATE = ["/bag", "/checkout", "/order"];
// The owner's screens (/admin, one address in both languages) are disallowed separately below;
// they also answer noindex and X-Robots-Tag, and the sitemap never lists them.

/**
 * Filter parameters that multiply the shop into views no index will ever hold.
 * /shop offers a sort order, a price band, a stock toggle and free text; each
 * carries the filters already applied forward, so six collections × eight
 * categories × four price bands × four sort orders is thousands of crawlable
 * addresses for twenty-one products. The pages themselves already answer
 * noindex, follow (see components/shop/query.ts `indexable`); this stops the
 * fetch as well. Collection, category and origin stay crawlable: those are the
 * three rails the sitemap declares.
 *
 * Wildcards are honoured by Googlebot, Bingbot and the four answer engines
 * named below.
 */
const CRAWL_TRAPS = ["/*?*sort=", "/*?*price=", "/*?*in_stock=", "/*?*q="];

const DISALLOW = ["/api/", "/admin", ...PRIVATE, ...PRIVATE.map((p) => `/uk${p}`), ...CRAWL_TRAPS];

/**
 * The one path under /api that is public sales material rather than the bridge
 * to the fulfillment core. /llms.txt and /llms-full.txt both name it as a
 * machine surface, so closing it would advertise a door and lock it. Longest
 * match wins in Google's and OpenAI's parsers, so this Allow beats the
 * "Disallow: /api/" above for exactly this address.
 */
const ALLOW = ["/", "/api/catalog"];

/**
 * Answer engines get the catalogue.
 *
 * A shop is found today by being quotable: someone asks an assistant where to
 * buy a vyshyvanka in Canada, and the answer comes from pages the assistant was
 * allowed to read. GPTBot, ClaudeBot, PerplexityBot and Google-Extended
 * therefore get the same catalogue access as a search crawler, and the same
 * closed doors on bag, checkout, order and the API. The trade is deliberate:
 * product copy, maker stories and prices are public sales material already, and
 * the risk of an assistant paraphrasing them is smaller than the cost of being
 * absent from the answer. The named bots are the ones that publish a
 * user-agent token and honour robots.txt; nothing here is a security control.
 *
 * To reverse this, move a bot's name from ANSWER_ENGINES into a rule with
 * `disallow: "/"`.
 */
const ANSWER_ENGINES = ["GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended"];

export default function robots(): MetadataRoute.Robots {
  const base = siteUrl();

  // Until the owner switches WEB_INDEXABLE on, the deployment is a preview and
  // stays out of every index, which matches the noindex the pages carry.
  if (!isIndexable()) {
    // /admin is named as well, so the rule for the owner's screens reads the same in both modes.
    return { rules: [{ userAgent: "*", disallow: ["/", "/admin"] }] };
  }

  return {
    rules: [
      { userAgent: "*", allow: ALLOW, disallow: DISALLOW },
      { userAgent: ANSWER_ENGINES, allow: ALLOW, disallow: DISALLOW },
    ],
    sitemap: `${base}/sitemap.xml`,
  };
}
