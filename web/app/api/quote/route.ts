import { NextResponse } from "next/server";
import { api, ApiError } from "@/lib/api";

export async function POST(req: Request) {
  try {
    const body = await req.json();
    return NextResponse.json(await api.quote(body));
  } catch (e) {
    if (e instanceof ApiError) return NextResponse.json({ code: e.code, message: e.message, details: e.details }, { status: e.status });
    return NextResponse.json({ code: "error", message: "Quote failed" }, { status: 502 });
  }
}
