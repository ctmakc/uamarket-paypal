import { revalidateTag } from "next/cache";
import { NextResponse } from "next/server";
import { API_URL, CATALOG_TAG } from "@/lib/api";
import { adminKey, allowedPath, safeJoin } from "@/lib/admin/api";
import { csrfOk, currentSession } from "@/lib/admin/session";

export const dynamic = "force-dynamic";

/** The admin screens' only door to the API: session required, CSRF on writes, key added here. */
const MAX_BODY = 16 * 1024 * 1024;

async function forward(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const session = await currentSession();
  if (!session) return NextResponse.json({ detail: { code: "signed_out", message: "Sign in again" } }, { status: 401 });
  const method = req.method.toUpperCase();
  if (method !== "GET" && !csrfOk(req, session)) {
    return NextResponse.json({ detail: { code: "csrf", message: "This request did not come from the admin page" } }, { status: 403 });
  }
  const { path } = await ctx.params;
  const joined = safeJoin(path);
  if (joined === null || !allowedPath(joined, method)) {
    return NextResponse.json({ detail: { code: "not_found", message: "Not found" } }, { status: 404 });
  }

  const declared = Number(req.headers.get("content-length") || "0");
  if (declared > MAX_BODY) {
    return NextResponse.json(
      { detail: { code: "too_large", message: `The upload is ${(declared / 1048576).toFixed(1)} MB; the limit is 15 MB.`, message_uk: `Файл важить ${(declared / 1048576).toFixed(1)} МБ; межа — 15 МБ.` } },
      { status: 413 },
    );
  }
  const url = new URL(req.url);
  const headers: Record<string, string> = { "x-api-key": adminKey() };
  const type = req.headers.get("content-type");
  if (type) headers["content-type"] = type;
  let body: ArrayBuffer | undefined;
  if (method !== "GET" && method !== "HEAD") {
    body = await req.arrayBuffer();
    if (body.byteLength > MAX_BODY) {
      return NextResponse.json({ detail: { code: "too_large", message: "The upload is larger than the limit." } }, { status: 413 });
    }
  }
  let upstream: Response;
  try {
    upstream = await fetch(`${API_URL}/${joined}${url.search}`, { method, headers, body, cache: "no-store" });
  } catch {
    return NextResponse.json({ detail: { code: "api_down", message: "The shop API is not answering" } }, { status: 502 });
  }
  if (method !== "GET" && upstream.ok) {
    // A saved product, photo, maker, stock change or order shows on the storefront on the next
    // page view instead of after the 30–60 s cache window.
    revalidateTag(CATALOG_TAG, { expire: 0 });
  }
  const out = new Headers({ "cache-control": "no-store" });
  const upstreamType = upstream.headers.get("content-type") || "application/json";
  out.set("content-type", upstreamType);
  if (upstreamType.startsWith("text/html")) {
    // Email previews render in a sandbox: no scripts, no same-origin access to the admin.
    out.set("content-security-policy", "sandbox; default-src 'none'; img-src * data:; style-src 'unsafe-inline'");
  }
  return new NextResponse(await upstream.arrayBuffer(), { status: upstream.status, headers: out });
}

export { forward as GET, forward as POST, forward as PATCH, forward as PUT, forward as DELETE };
