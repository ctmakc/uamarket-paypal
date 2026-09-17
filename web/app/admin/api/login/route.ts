import { NextResponse } from "next/server";
import {
  SESSION_COOKIE, accountDelayMs, adminConfig, clearFailures, clientKey, cookieOptions, lockedFor, newSessionValue, registerFailure,
  sameOrigin, verifyPassword,
} from "@/lib/admin/session";

export const dynamic = "force-dynamic";

const noStore = { "cache-control": "no-store" };

/**
 * Password sign-in. JSON in, JSON out, so a lock answers 429 with Retry-After.
 * A cross-site form cannot reach it: the Origin must be this site and the request must
 * carry the x-admin-login header, which a plain HTML form cannot set.
 */
export async function POST(req: Request) {
  if (!sameOrigin(req) || req.headers.get("x-admin-login") !== "1") {
    return NextResponse.json({ code: "forbidden", message: "Cross-site sign-in refused" }, { status: 403, headers: noStore });
  }
  const cfg = adminConfig();
  if (!cfg.ok) return NextResponse.json({ code: "not_configured", missing: cfg.missing }, { status: 503, headers: noStore });
  const client = await clientKey(req);
  const wait = lockedFor(client);
  if (wait > 0) {
    return NextResponse.json({ code: "locked", retry_after: wait }, { status: 429, headers: { ...noStore, "retry-after": String(wait) } });
  }
  let password = "";
  try {
    const body = (await req.json()) as { password?: unknown };
    password = typeof body.password === "string" ? body.password.slice(0, 500) : "";
  } catch {
    password = "";
  }
  const delay = accountDelayMs();
  if (delay > 0) await new Promise((r) => setTimeout(r, delay));
  if (!password || !verifyPassword(password, cfg.hash)) {
    const locked = registerFailure(client);
    if (locked > 0) {
      return NextResponse.json({ code: "locked", retry_after: locked }, { status: 429, headers: { ...noStore, "retry-after": String(locked) } });
    }
    return NextResponse.json({ code: "wrong_password" }, { status: 401, headers: noStore });
  }
  clearFailures(client);
  const session = newSessionValue(cfg);
  const res = NextResponse.json({ ok: true, next: "/admin" }, { headers: noStore });
  res.cookies.set(SESSION_COOKIE, session.value, cookieOptions(session.maxAge));
  return res;
}
