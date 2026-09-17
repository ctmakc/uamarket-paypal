/**
 * `/api/catalog` — the public JSON feed of the catalogue.
 *
 * Same facts as /llms.txt and /llms-full.txt, built from the same snapshot, for
 * a consumer that would rather parse than read: an answer engine's crawler, a
 * price comparison, or the Google Merchant feed the shop may want later. Both
 * languages travel in one payload, so nobody can pair an English title with a
 * Ukrainian price from two separate reads.
 *
 * Query:
 *   ?detail=full     (default) technique, material, care, description, variants
 *   ?detail=summary  the light version, one request to the catalogue API
 *
 * Read-only, no cookies, no customer data. `generated_at` is in the body so a
 * cached copy can always be dated. The response is cacheable by a CDN for
 * GEO_CACHE_CONTROL's window; `access-control-allow-origin: *` is set because a
 * public product feed with no credentials is meant to be read from anywhere.
 *
 * NOTE for whoever owns web/app/robots.ts: that file disallows `/api/` for
 * every crawler, which closes this feed to the answer engines it exists for.
 * Adding `/api/catalog` to the `allow` list of both rules opens it — a more
 * specific Allow beats a broader Disallow. See docs/GEO.md.
 */
import { NextResponse } from "next/server";
import { GEO_CACHE_CONTROL, buildCatalogFeed, loadSnapshot } from "@/lib/geo";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const detail = new URL(req.url).searchParams.get("detail");
  const snapshot = await loadSnapshot({ detail: detail !== "summary" });

  if (!snapshot.ok) {
    return NextResponse.json(
      { error: "catalogue_unavailable", message: "The catalogue could not be read. Try again in a minute." },
      { status: 503, headers: { "cache-control": "no-store", "retry-after": "60" } },
    );
  }

  return NextResponse.json(buildCatalogFeed(snapshot), {
    headers: {
      "cache-control": GEO_CACHE_CONTROL,
      "access-control-allow-origin": "*",
      vary: "Accept-Encoding",
    },
  });
}
