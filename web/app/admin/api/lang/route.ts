import { NextResponse } from "next/server";
import { ADMIN_LANG_COOKIE } from "@/lib/admin/i18n";
import { secureCookies } from "@/lib/admin/session";

/** Switch the operator screens' language. Only a display preference; returns to the page it came from. */
export async function GET(req: Request) {
  const url = new URL(req.url);
  const to = url.searchParams.get("to") === "uk" ? "uk" : "en";
  const back = url.searchParams.get("back") || "/admin";
  const safe = back.startsWith("/admin") && !back.startsWith("//") ? back : "/admin";
  const res = new NextResponse(null, { status: 303, headers: { location: safe } });
  res.cookies.set(ADMIN_LANG_COOKIE, to, { path: "/admin", sameSite: "lax", secure: secureCookies(), maxAge: 365 * 24 * 3600 });
  return res;
}
