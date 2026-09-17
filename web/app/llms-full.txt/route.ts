/**
 * `/llms-full.txt` — the whole shop in one fetch.
 *
 * Same map as /llms.txt, extended with every product on one line (title,
 * origin, maker, region, technique, material, price, availability, canonical
 * URL) and every maker on one line (name, region, country, craft, product
 * count, URL). An agent that fetches this single file can answer "who made it
 * and what is it made of" without walking the catalogue page by page.
 *
 * It costs one request per product to build, because technique and material
 * live on the product detail payload and not on the summary. That is why the
 * snapshot is loaded with detail and why GEO_CACHE_CONTROL holds the result for
 * fifteen minutes; above GEO_DETAIL_LIMIT products the detail pass is skipped
 * and the file says so in its own header.
 */
import { GEO_CACHE_CONTROL, buildLlmsFullTxt, geoText, loadSnapshot } from "@/lib/geo";
import { isLang } from "@/lib/i18n";
import type { Lang } from "@/lib/i18n";

export const dynamic = "force-dynamic";

function langOf(req: Request): Lang {
  const raw = new URL(req.url).searchParams.get("lang") ?? "en";
  return isLang(raw) ? raw : "en";
}

export async function GET(req: Request) {
  const lang = langOf(req);
  const snapshot = await loadSnapshot({ detail: true });

  if (!snapshot.ok) {
    return new Response(`${geoText(lang).unavailable}\n`, {
      status: 503,
      headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store", "retry-after": "60" },
    });
  }

  return new Response(buildLlmsFullTxt(snapshot, lang), {
    headers: {
      "content-type": "text/plain; charset=utf-8",
      "cache-control": GEO_CACHE_CONTROL,
      "content-language": lang === "uk" ? "uk" : "en-CA",
      vary: "Accept-Encoding",
    },
  });
}
