import { NextResponse } from "next/server";
import { api, ApiError } from "@/lib/api";
import { orderCookieName, orderCookieOptions, visitorFrom } from "@/lib/visitor";

/**
 * The order lookup form posts here (a plain HTML form, no script needed). The order number
 * and the email travel in the request body. A match sets the order's cookie and sends the
 * browser to /order/<number>; a miss goes back to the form with the number filled in. The
 * email never appears in an address.
 */
export async function POST(req: Request) {
  const form = await req.formData();
  const number = String(form.get("number") || "").trim().toUpperCase().slice(0, 32);
  const email = String(form.get("email") || "").trim().slice(0, 200);
  const lang = form.get("lang") === "uk" ? "uk" : "en";
  const prefix = lang === "uk" ? "/uk" : "";
  // A relative Location: behind Caddy the server's own idea of its host is not the shop's.
  const go = (path: string) => new NextResponse(null, { status: 303, headers: { location: path } });
  const back = (flag: string) => go(`${prefix}/order?number=${encodeURIComponent(number)}&${flag}=1`);
  if (!number || !email) return back("missing");
  try {
    const found = await api.lookup(number, email, visitorFrom(req.headers));
    const res = go(`${prefix}/order/${encodeURIComponent(found.order_number)}`);
    res.cookies.set(orderCookieName(found.order_number), found.access_token, orderCookieOptions());
    return res;
  } catch (e) {
    if (e instanceof ApiError && e.status === 429) return back("busy");
    if (e instanceof ApiError && e.status === 404) return back("missing");
    return back("down");
  }
}
