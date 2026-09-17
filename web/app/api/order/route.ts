import { NextResponse } from "next/server";
import { api, ApiError } from "@/lib/api";
import { orderCookieName, orderCookieOptions, visitorFrom } from "@/lib/visitor";

/**
 * Place an order. The API's access key for it goes into an HttpOnly cookie for this order
 * and is taken out of the JSON, so the browser moves to /order/<number> with nothing in the
 * address but the number.
 */
export async function POST(req: Request) {
  try {
    const body = await req.json();
    const order = await api.placeOrder(body, visitorFrom(req.headers));
    const { access_token: token, ...view } = order;
    const res = NextResponse.json(view, { status: 201 });
    if (token) res.cookies.set(orderCookieName(order.order_number), token, orderCookieOptions());
    return res;
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ code: e.code, message: e.message, details: e.details }, { status: e.status });
    return NextResponse.json({ code: "error", message: "Order failed" }, { status: 502 });
  }
}
