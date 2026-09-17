/**
 * `/llms.txt` — the short, linkable map of the shop for an agent.
 *
 * The convention (llmstxt.org) asks for one markdown file at the root that
 * tells a language model what a site is and where its real content lives. This
 * one is generated from the live catalogue and the shared content model rather
 * than written by hand, so a collection count here can never drift away from
 * the collection count on /shop.
 *
 * English is the default because that is the language an answer engine indexes
 * a Canadian shop in; `?lang=uk` returns the whole document in Ukrainian, and
 * both files link to each other.
 *
 * Served as text/plain: a crawler that follows a link to a `.txt` file expects
 * to read it, not download it. The body is markdown, which is what the
 * convention specifies.
 */
import { GEO_CACHE_CONTROL, buildLlmsTxt, geoText, loadSnapshot } from "@/lib/geo";
import { isLang } from "@/lib/i18n";
import type { Lang } from "@/lib/i18n";

// Read per request: the catalogue, the storefront config and every policy env
// var must be current. lib/api's own revalidate windows keep the API calls
// cheap, and GEO_CACHE_CONTROL caps how long a CDN may hold the answer.
export const dynamic = "force-dynamic";

function langOf(req: Request): Lang {
  const raw = new URL(req.url).searchParams.get("lang") ?? "en";
  return isLang(raw) ? raw : "en";
}

export async function GET(req: Request) {
  const lang = langOf(req);
  const snapshot = await loadSnapshot();

  if (!snapshot.ok) {
    return new Response(`${geoText(lang).unavailable}\n`, {
      status: 503,
      headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store", "retry-after": "60" },
    });
  }

  return new Response(buildLlmsTxt(snapshot, lang), {
    headers: {
      "content-type": "text/plain; charset=utf-8",
      "cache-control": GEO_CACHE_CONTROL,
      "content-language": lang === "uk" ? "uk" : "en-CA",
      vary: "Accept-Encoding",
    },
  });
}
