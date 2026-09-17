/**
 * Who is asking, as far as the storefront server can prove it, and the buyer's order key.
 *
 * In production Caddy is the only way in. It writes the visitor's socket address into
 * X-Real-IP and adds X-Internal-Proxy-Secret; a request that carries the secret came through
 * Caddy, so its X-Real-IP is believed. Anything else (a header a visitor typed, a local run
 * without Caddy) gives no address, and the API counts the request under the web server's
 * own address. X-Forwarded-For is never read: anybody can write it.
 */
import type { Visitor } from "@/lib/api";

type HeaderBag = { get(name: string): string | null };

function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export function visitorFrom(headers: HeaderBag): Visitor {
  const secret = (process.env.INTERNAL_PROXY_SECRET || "").trim();
  const supplied = headers.get("x-internal-proxy-secret") || "";
  if (secret.length < 16 || !supplied || !safeEqual(supplied, secret)) return {};
  const ip = (headers.get("x-real-ip") || "").trim().slice(0, 120);
  return ip ? { ip } : {};
}

/**
 * The buyer's key to one order lives in an HttpOnly cookie scoped to that order, set by the
 * server when the order is placed or looked up. It expires after ORDER_COOKIE_HOURS; the
 * order email carries its own link (?key=) for later.
 */
export const ORDER_COOKIE_HOURS = 12;

export function orderCookieName(number: string): string {
  return `uam_order_${number.trim().toUpperCase().replace(/[^A-Z0-9-]/g, "")}`;
}

export function orderCookieOptions() {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: (process.env.WEB_BASE_URL || "").startsWith("https://"),
    path: "/",
    maxAge: ORDER_COOKIE_HOURS * 3600,
  };
}

/** A key that could be one: URL-safe base64, the length the API mints. */
export function plausibleKey(value: string | null | undefined): string | null {
  const v = (value || "").trim();
  return /^[A-Za-z0-9_-]{20,64}$/.test(v) ? v : null;
}
