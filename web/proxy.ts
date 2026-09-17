import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { catchingUpHtml } from "@/lib/down";

/**
 * Locale routing without changing English URLs.
 *
 * English is served WITHOUT a prefix (/product/x) and rewritten internally to
 * /en/product/x; Ukrainian lives under /uk/... . A request that names /en
 * explicitly is redirected to the bare address so one page never has two URLs.
 * Static files, the API bridge and Next internals pass through untouched.
 *
 * The list is the whole set of addresses that exist outside a language: the API
 * bridge, Next internals, the fonts and images, the card renderer at /og, and
 * the four files a crawler or an agent fetches by their exact name. /og and the
 * two llms files carry no extension, so without naming them here they fall to
 * the rewrite below and 404 as /en/og — which is what happened until 2026-09-02
 * and left every og:image on the site dead.
 *
 * /admin (the owner's screens, one language chosen by a cookie) and /media (product photos
 * from the API's media volume) are not localized pages; the matcher below keeps this proxy
 * off them entirely, so a photo upload is never buffered by it.
 */
const PASS = /^\/(api|admin|media|_next|fonts|images|og|favicon\.ico|icon\.svg|apple-icon\.png|robots\.txt|sitemap\.xml|llms\.txt|llms-full\.txt)(\/|$)/;

/**
 * Pages that are nothing without the catalogue. While the API cannot be read they answer
 * 503 "catching up" (lib/down.ts) instead of rendering an empty shop. The policy pages, FAQ
 * and order lookup still render: they say what they can without it.
 */
const CATALOGUE = /^\/(?:uk\/?)?(?:$|shop(?:\/|$)|product\/|makers(?:\/|$)|bag$|checkout$)/;
const HEALTH_TTL_MS = 3000;
let health: { ok: boolean; at: number } | null = null;

async function apiUp(): Promise<boolean> {
  const now = Date.now();
  if (health && now - health.at < HEALTH_TTL_MS) return health.ok;
  const base = (process.env.API_URL || "http://127.0.0.1:8010").replace(/\/$/, "");
  let ok = false;
  try {
    const res = await fetch(`${base}/health`, { cache: "no-store", signal: AbortSignal.timeout(1500) });
    ok = res.ok;
  } catch {
    ok = false;
  }
  health = { ok, at: now };
  return ok;
}

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (PASS.test(pathname) || /\.[a-z0-9]+$/i.test(pathname)) return NextResponse.next();
  if (request.method === "GET" && CATALOGUE.test(pathname) && !(await apiUp())) {
    const lang = pathname === "/uk" || pathname.startsWith("/uk/") ? "uk" : "en";
    return new NextResponse(catchingUpHtml(lang, pathname + request.nextUrl.search), {
      status: 503,
      headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store", "retry-after": "60" },
    });
  }
  if (pathname === "/uk" || pathname.startsWith("/uk/")) return NextResponse.next();
  if (pathname === "/en" || pathname.startsWith("/en/")) {
    const url = request.nextUrl.clone();
    url.pathname = pathname.slice(3) || "/";
    return NextResponse.redirect(url, 308);
  }
  const url = request.nextUrl.clone();
  url.pathname = `/en${pathname === "/" ? "" : pathname}`;
  return NextResponse.rewrite(url);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|admin|media/).*)"],
};
