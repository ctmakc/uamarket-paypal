import { NextResponse } from "next/server";
import { SESSION_COOKIE, cookieOptions, csrfOk, currentSession } from "@/lib/admin/session";

export async function POST(req: Request) {
  const session = await currentSession();
  if (session && !csrfOk(req, session)) return NextResponse.json({ code: "csrf" }, { status: 403 });
  const res = NextResponse.json({ ok: true, next: "/admin/login" });
  res.cookies.set(SESSION_COOKIE, "", cookieOptions(0));
  return res;
}
