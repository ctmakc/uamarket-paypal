/**
 * Server-side calls from the /admin screens to the fulfillment API.
 *
 * ADMIN_API_KEY is read here, on the Next.js server, and added to the outgoing request.
 * Nothing in this file is imported by a client component, and no response the browser
 * receives echoes the key.
 */
import { API_URL } from "@/lib/api";

export class AdminApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown) {
    const detail = (body as { detail?: unknown })?.detail;
    const message =
      typeof detail === "string" ? detail : (detail as { message?: string } | undefined)?.message || `API error ${status}`;
    super(message);
    this.status = status;
    this.body = body;
  }
}

export function adminKey(): string {
  return (process.env.ADMIN_API_KEY || "").trim();
}

export async function adminGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { headers: { "x-api-key": adminKey() }, cache: "no-store" });
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = { detail: text };
  }
  if (!res.ok) throw new AdminApiError(res.status, body);
  return body as T;
}

/** Which API paths the browser may reach through /admin/api/…, and with which methods. */
const ALLOWED: [RegExp, string[]][] = [
  [/^v1\/admin\/.+/, ["GET", "POST", "PATCH", "PUT", "DELETE"]],
  [/^v1\/orders\/[^/]+\/(mark-paid|reserve|ship)$/, ["POST"]],
  [/^v1\/orders\/[^/]+\/mail\/[a-z_]+\/preview$/, ["GET"]],
  [/^v1\/exceptions\/[^/]+\/resolve$/, ["POST"]],
  [/^v1\/packages\/[^/]+\/shipping\/easypost\/buy$/, ["POST"]],
  [/^v1\/(dashboard|inventory)$/, ["GET"]],
];

export function allowedPath(path: string, method: string): boolean {
  return ALLOWED.some(([re, methods]) => re.test(path) && methods.includes(method));
}

/**
 * The API path, or null when a segment could step outside the allowlist once the URL is
 * normalised: "." / ".." (also double-encoded, `%252e%252e`), empty segments, slashes or
 * backslashes hidden inside a segment, or a `%` left after decoding.
 */
export function safeJoin(path: string[]): string | null {
  const out: string[] = [];
  for (const raw of path) {
    let seg: string;
    try {
      seg = decodeURIComponent(raw);
    } catch {
      return null;
    }
    if (!seg || seg === "." || seg === ".." || /[\\/%\u0000-\u001f]/.test(seg)) return null;
    out.push(encodeURIComponent(seg));
  }
  const joined = out.join("/");
  // Belt and braces: the URL the fetch will use must keep exactly this path.
  try {
    if (new URL(`http://api.invalid/${joined}`).pathname !== `/${joined}`) return null;
  } catch {
    return null;
  }
  return joined;
}
