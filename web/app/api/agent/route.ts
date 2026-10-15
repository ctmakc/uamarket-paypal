import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { api, ApiError } from "@/lib/api";
import { orderCookieName, plausibleKey, visitorFrom } from "@/lib/visitor";

/**
 * One turn of the shopping concierge. The browser names the orders it placed from the chat
 * by number only; their keys are read here from the HttpOnly order cookies, so the agent can
 * report "paid" without the browser ever holding a key.
 */
export async function POST(req: Request) {
  let body: { messages?: unknown; locale?: string; budget_cad?: number | null; orders?: string[]; bag?: unknown } = {};
  try { body = await req.json(); } catch { return NextResponse.json({ code: "messages", message: "Bad request" }, { status: 400 }); }
  const jar = await cookies();
  const orders = (Array.isArray(body.orders) ? body.orders : []).slice(0, 10).flatMap((n) => {
    const number = String(n || "").toUpperCase();
    const token = plausibleKey(jar.get(orderCookieName(number))?.value);
    return token ? [{ order_number: number, token }] : [];
  });
  try {
    const reply = await api.agentShop({ messages: body.messages, locale: body.locale === "uk" ? "uk" : "en", budget_cad: body.budget_cad || null, orders, bag: Array.isArray(body.bag) ? body.bag : [] }, visitorFrom(req.headers));
    return NextResponse.json(reply);
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ code: e.code, message: e.message }, { status: e.status });
    return NextResponse.json({ code: "error", message: "The assistant is not answering right now" }, { status: 502 });
  }
}
