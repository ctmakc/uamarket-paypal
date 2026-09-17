import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { api, ApiError } from "@/lib/api";
import { orderCookieName, plausibleKey, visitorFrom } from "@/lib/visitor";

/** A new card payment session for an unpaid order. */
export async function POST(req: Request, ctx: { params: Promise<{ number: string }> }) {
  const { number } = await ctx.params;
  const jar = await cookies();
  let key = plausibleKey(jar.get(orderCookieName(number))?.value);
  if (!key) {
    try { key = plausibleKey((await req.json())?.key); } catch { key = null; }
  }
  if (!key) return NextResponse.json({ code: "not_found", message: "Order not found" }, { status: 404 });
  try {
    return NextResponse.json(await api.retryPayment(number, key, visitorFrom(req.headers)));
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ code: e.code, message: e.message }, { status: e.status });
    return NextResponse.json({ code: "error", message: "Payment could not be started" }, { status: 502 });
  }
}
