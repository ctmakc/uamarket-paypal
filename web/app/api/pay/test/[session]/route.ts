import { NextResponse } from "next/server";
import { api, ApiError } from "@/lib/api";

/** Complete a local test payment (PAYMENT_PROVIDER=fake only; the API refuses otherwise). */
export async function POST(_req: Request, ctx: { params: Promise<{ session: string }> }) {
  const { session } = await ctx.params;
  try {
    return NextResponse.json(await api.completeTestPayment(session));
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ code: e.code, message: e.message }, { status: e.status });
    return NextResponse.json({ code: "error", message: "Test payment failed" }, { status: 502 });
  }
}
