/**
 * Owner sign-in for /admin. Server only.
 *
 *   ADMIN_PASSWORD_HASH   scrypt:<N>:<r>:<p>:<salt b64>:<hash b64>, made by
 *                         `python3 tools/admin_password_hash.py`
 *   ADMIN_SESSION_SECRET  at least 32 characters, signs the session cookie
 *
 * The session is a signed cookie (HttpOnly, SameSite=Strict, path /admin, Secure on https):
 *   v1.<expires unix>.<nonce>.<password fingerprint>.<HMAC-SHA256>
 * The fingerprint is a hash of ADMIN_PASSWORD_HASH, so changing the password signs every
 * existing session out. Every state-changing request also carries x-csrf-token, which is an
 * HMAC of the session nonce and is only ever printed into the admin's own pages.
 */
import { createHash, createHmac, randomBytes, scryptSync, timingSafeEqual } from "node:crypto";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";

export const SESSION_COOKIE = "uam_admin";
const SESSION_HOURS = 12;

export type AdminConfig = { ok: true; secret: string; hash: string } | { ok: false; missing: string[] };

export function adminConfig(): AdminConfig {
  const secret = (process.env.ADMIN_SESSION_SECRET || "").trim();
  const hash = (process.env.ADMIN_PASSWORD_HASH || "").trim();
  const missing: string[] = [];
  if (secret.length < 32) missing.push("ADMIN_SESSION_SECRET");
  if (!/^scrypt:\d+:\d+:\d+:[A-Za-z0-9+/=]+:[A-Za-z0-9+/=]+$/.test(hash)) missing.push("ADMIN_PASSWORD_HASH");
  if (!(process.env.ADMIN_API_KEY || "").trim()) missing.push("ADMIN_API_KEY");
  return missing.length ? { ok: false, missing } : { ok: true, secret, hash };
}

function b64url(buf: Buffer): string {
  return buf.toString("base64url");
}

function sign(secret: string, payload: string): string {
  return b64url(createHmac("sha256", secret).update(payload).digest());
}

function fingerprint(hash: string): string {
  return b64url(createHash("sha256").update(hash).digest()).slice(0, 16);
}

function same(a: string, b: string): boolean {
  const x = Buffer.from(a);
  const y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}

export function verifyPassword(password: string, stored: string): boolean {
  const parts = stored.split(":");
  if (parts.length !== 6 || parts[0] !== "scrypt") return false;
  const [N, r, p] = [Number(parts[1]), Number(parts[2]), Number(parts[3])];
  const salt = Buffer.from(parts[4], "base64");
  const expected = Buffer.from(parts[5], "base64");
  if (!N || !r || !p || !expected.length) return false;
  try {
    const got = scryptSync(password.normalize("NFKC"), salt, expected.length, { N, r, p, maxmem: 256 * 1024 * 1024 });
    return got.length === expected.length && timingSafeEqual(got, expected);
  } catch {
    return false;
  }
}

export function newSessionValue(cfg: { secret: string; hash: string }): { value: string; maxAge: number } {
  const exp = Math.floor(Date.now() / 1000) + SESSION_HOURS * 3600;
  const nonce = b64url(randomBytes(18));
  const body = `v1.${exp}.${nonce}.${fingerprint(cfg.hash)}`;
  return { value: `${body}.${sign(cfg.secret, body)}`, maxAge: SESSION_HOURS * 3600 };
}

export type Session = { nonce: string; csrf: string; expires: number };

export function readSessionValue(value: string | undefined): Session | null {
  const cfg = adminConfig();
  if (!cfg.ok || !value) return null;
  const parts = value.split(".");
  if (parts.length !== 5 || parts[0] !== "v1") return null;
  const body = parts.slice(0, 4).join(".");
  if (!same(sign(cfg.secret, body), parts[4])) return null;
  const exp = Number(parts[1]);
  if (!Number.isFinite(exp) || exp * 1000 < Date.now()) return null;
  if (!same(parts[3], fingerprint(cfg.hash))) return null;
  return { nonce: parts[2], csrf: sign(cfg.secret, `csrf.${parts[2]}`), expires: exp };
}

export async function currentSession(): Promise<Session | null> {
  const jar = await cookies();
  return readSessionValue(jar.get(SESSION_COOKIE)?.value);
}

/** For pages: the session, or a redirect to the sign-in page. */
export async function requireSession(): Promise<Session> {
  const session = await currentSession();
  if (!session) redirect("/admin/login");
  return session;
}

export function secureCookies(): boolean {
  return (process.env.WEB_BASE_URL || "").trim().toLowerCase().startsWith("https://");
}

export function cookieOptions(maxAge: number) {
  return { httpOnly: true, sameSite: "strict" as const, secure: secureCookies(), path: "/admin", maxAge };
}

/**
 * A state-changing request is accepted only from this site: the Origin header (browsers send
 * it on every POST) must match the Host, and the request must carry the CSRF header.
 */
export function sameOrigin(req: Request): boolean {
  const origin = req.headers.get("origin");
  const host = req.headers.get("x-forwarded-host") || req.headers.get("host");
  if (!origin || !host) return false;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

export function csrfOk(req: Request, session: Session): boolean {
  const token = req.headers.get("x-csrf-token") || "";
  return sameOrigin(req) && token.length > 0 && same(token, session.csrf);
}

// ------------------------------------------------------------------ login rate limit
//
// Two layers, and neither can lock the owner out from everywhere:
//  - per address: 5 wrong passwords in 15 min lock that address for ADMIN_LOGIN_LOCK_SECONDS.
//    Someone guessing from another address never touches the owner's own address.
//  - per account (there is one password): wrong passwords from all addresses together slow
//    every check down, doubling from 0.5 s after 10 failures up to a 4 s ceiling. A
//    distributed guesser gets a handful of tries a minute; the owner waits seconds, never a lock.

type Bucket = { failures: number[]; lockedUntil: number };
const buckets = new Map<string, Bucket>();
const WINDOW_MS = 15 * 60 * 1000;
const PER_CLIENT = 5;
const ACCOUNT_FREE = 10;
const ACCOUNT_BASE_MS = 500;
const ACCOUNT_MAX_MS = 4000;
const MAX_TRACKED = 5000;
let accountFailures: number[] = [];

export function lockSeconds(): number {
  const raw = Number((process.env.ADMIN_LOGIN_LOCK_SECONDS || "").trim());
  return Number.isFinite(raw) && raw >= 10 ? Math.min(raw, 24 * 3600) : 900;
}

function bucket(key: string): Bucket {
  let b = buckets.get(key);
  if (!b) {
    if (buckets.size >= MAX_TRACKED) {
      // Forget idle addresses first so a spray of addresses cannot grow memory without end.
      const now = Date.now();
      for (const [k, v] of buckets) if (v.lockedUntil < now && !v.failures.some((t) => now - t < WINDOW_MS)) buckets.delete(k);
      if (buckets.size >= MAX_TRACKED) buckets.delete(buckets.keys().next().value as string);
    }
    b = { failures: [], lockedUntil: 0 };
    buckets.set(key, b);
  }
  const now = Date.now();
  b.failures = b.failures.filter((t) => now - t < WINDOW_MS);
  return b;
}

/** Seconds until this address may try again, or 0. Only this address is ever locked. */
export function lockedFor(client: string): number {
  const now = Date.now();
  const until = bucket(client).lockedUntil;
  return until > now ? Math.ceil((until - now) / 1000) : 0;
}

/** Milliseconds every password check waits now, from the account's recent failures. */
export function accountDelayMs(): number {
  const now = Date.now();
  accountFailures = accountFailures.filter((t) => now - t < WINDOW_MS);
  const over = accountFailures.length - ACCOUNT_FREE;
  if (over < 0) return 0;
  return Math.min(ACCOUNT_MAX_MS, ACCOUNT_BASE_MS * 2 ** Math.min(over, 8));
}

/** Count one failure; returns the lock in seconds when this failure locks the address. */
export function registerFailure(client: string): number {
  const now = Date.now();
  accountFailures.push(now);
  if (accountFailures.length > 1000) accountFailures = accountFailures.slice(-1000);
  const b = bucket(client);
  b.failures.push(now);
  if (b.failures.length >= PER_CLIENT) {
    b.lockedUntil = now + lockSeconds() * 1000;
    b.failures = [];
    return lockSeconds();
  }
  return 0;
}

/** A right password clears that address; the account slow-down fades by itself. */
export function clearFailures(client: string): void {
  buckets.delete(client);
}

/** The address the request came from, as the nearest proxy recorded it. */
export async function clientKey(req?: Request): Promise<string> {
  const h = req ? req.headers : await headers();
  // Behind a tunnel or CDN every request reaches us from the same hop, so the address it
  // vouches for is read from its own header (e.g. ADMIN_CLIENT_IP_HEADER=cf-connecting-ip).
  const trusted = (process.env.ADMIN_CLIENT_IP_HEADER || "").trim().toLowerCase();
  if (trusted) {
    const v = (h.get(trusted) || "").split(",")[0].trim();
    if (v) return v;
  }
  const fwd = h.get("x-forwarded-for");
  if (fwd) {
    const list = fwd.split(",").map((s) => s.trim()).filter(Boolean);
    // The right-most entry is the one our own server (or the proxy in front of it) wrote.
    if (list.length) return list[list.length - 1];
  }
  return h.get("x-real-ip") || "local";
}
