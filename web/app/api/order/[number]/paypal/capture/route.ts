import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { api, ApiError } from "@/lib/api";
import { orderCookieName, plausibleKey, visitorFrom } from "@/lib/visitor";

/** Capture the payment the buyer approved in PayPal (the button's onApprove). */
export async function POST(req: Request, ctx: { params: Promise<{ number: string }> }) {
  const { number } = await ctx.params;
  const jar = await cookies();
  let body: { paypal_order_id?: string; key?: string } = {};
  try { body = await req.json(); } catch { body = {}; }
  const key = plausibleKey(jar.get(orderCookieName(number))?.value) || plausibleKey(body.key);
  const paypalOrderId = String(body.paypal_order_id || "");
  if (!key) return NextResponse.json({ code: "not_found", message: "Order not found" }, { status: 404 });
  if (!/^[A-Z0-9]{10,40}$/.test(paypalOrderId)) return NextResponse.json({ code: "payment_method", message: "No PayPal payment" }, { status: 400 });
  try {
    const view = await api.paypalCapture(number, key, paypalOrderId, visitorFrom(req.headers));
    return NextResponse.json(view);
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ code: e.code, message: e.message, details: e.details }, { status: e.status });
    return NextResponse.json({ code: "error", message: "PayPal could not capture the payment" }, { status: 502 });
  }
}
