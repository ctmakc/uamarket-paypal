import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { api, ApiError } from "@/lib/api";
import { orderCookieName, plausibleKey, visitorFrom } from "@/lib/visitor";

/** The order key: the cookie set at checkout or lookup, or `key` sent by the order page. */
async function keyFor(req: Request, number: string): Promise<string | null> {
  const jar = await cookies();
  const fromCookie = plausibleKey(jar.get(orderCookieName(number))?.value);
  if (fromCookie) return fromCookie;
  try {
    const body = await req.clone().json();
    return plausibleKey(body?.key);
  } catch {
    return null;
  }
}

/** Cancel an unpaid order. */
export async function POST(req: Request, ctx: { params: Promise<{ number: string }> }) {
  const { number } = await ctx.params;
  const key = await keyFor(req, number);
  if (!key) return NextResponse.json({ code: "not_found", message: "Order not found" }, { status: 404 });
  try {
    const { access_token: _t, ...view } = await api.cancelOrder(number, key, visitorFrom(req.headers));
    return NextResponse.json(view);
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ code: e.code, message: e.message }, { status: e.status });
    return NextResponse.json({ code: "error", message: "Cancel failed" }, { status: 502 });
  }
}
