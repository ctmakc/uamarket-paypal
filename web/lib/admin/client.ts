"use client";

/** Browser-side calls to /admin/api/…, which adds the API key on the server. */
export type Result<T> = { ok: boolean; status: number; data: T; message: string };

function csrf(): string {
  return document.querySelector('meta[name="admin-csrf"]')?.getAttribute("content") || "";
}

function messageOf(body: unknown, status: number, lang: "en" | "uk"): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => `${(d as { loc?: string[] }).loc?.slice(-1)[0] ?? ""}: ${(d as { msg?: string }).msg ?? ""}`).join("; ");
  }
  const d = detail as { message?: string; message_uk?: string } | undefined;
  if (d?.message) return lang === "uk" && d.message_uk ? d.message_uk : d.message;
  return status >= 400 ? `Error ${status}` : "";
}

export async function adminCall<T = unknown>(
  path: string,
  opts: { method?: string; json?: unknown; form?: FormData; body?: BodyInit; contentType?: string; lang?: "en" | "uk" } = {},
): Promise<Result<T>> {
  const method = (opts.method || (opts.json !== undefined || opts.form || opts.body ? "POST" : "GET")).toUpperCase();
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["x-csrf-token"] = csrf();
  let body: BodyInit | undefined;
  if (opts.json !== undefined) {
    headers["content-type"] = "application/json";
    body = JSON.stringify(opts.json);
  } else if (opts.form) {
    body = opts.form;
  } else if (opts.body !== undefined) {
    body = opts.body;
    if (opts.contentType) headers["content-type"] = opts.contentType;
  }
  let res: Response;
  try {
    res = await fetch(`/admin/api/${path.replace(/^\//, "")}`, { method, headers, body, credentials: "same-origin" });
  } catch {
    return { ok: false, status: 0, data: null as T, message: opts.lang === "uk" ? "Немає зв'язку із сервером" : "No connection to the server" };
  }
  if (res.status === 401) {
    window.location.assign("/admin/login");
  }
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text.slice(0, 300) };
  }
  return { ok: res.ok, status: res.status, data: data as T, message: res.ok ? "" : messageOf(data, res.status, opts.lang || "en") };
}
