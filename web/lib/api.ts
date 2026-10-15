/**
 * Server-side client for the fulfillment API (FastAPI, app/).
 * Runs on the Next.js server only; the browser talks to /api/* route handlers.
 */

export const API_URL = (process.env.API_URL || "http://127.0.0.1:8010").replace(/\/$/, "");

export type Availability = { in_stock: boolean; low: boolean };
export type Variant = {
  sku: string;
  label: string;
  /** The Ukrainian option label entered in /admin; null for older rows. */
  label_uk?: string | null;
  options: Record<string, string>;
  price_cad: number;
  weight_g: number | null;
  availability: Availability;
};
export type MakerRef = { slug: string; name: string; name_uk: string | null; region: string; region_uk: string | null };
export type ProductSummary = {
  slug: string;
  title: string;
  title_uk: string | null;
  subtitle: string | null;
  subtitle_uk: string | null;
  category: string;
  collection: string;
  origin: "HANDMADE_UA" | "MADE_UA" | "DESIGNED_UA";
  origin_label: string;
  origin_label_uk: string;
  origin_note: string | null;
  origin_note_uk: string | null;
  maker: MakerRef | null;
  price_from_cad: number;
  price_to_cad: number;
  image_url: string | null;
  images: string[];
  /** Uploaded photos with their alt text and resized widths (srcset). Empty for legacy URL images. */
  photos?: { id: string; src: string; srcset: string; width: number; height: number; alt: string; alt_uk: string }[];
  featured: boolean;
  in_stock: boolean;
  variant_count: number;
};
export type Product = ProductSummary & {
  description: string;
  description_uk: string | null;
  technique: string | null;
  technique_uk: string | null;
  material: string | null;
  material_uk: string | null;
  care: string | null;
  care_uk: string | null;
  attributes: Record<string, string | number>;
  variants: Variant[];
  related: ProductSummary[];
};
export type Maker = {
  slug: string;
  name: string;
  name_uk: string | null;
  region: string;
  region_uk: string | null;
  country: string;
  craft: string;
  craft_uk: string | null;
  story: string;
  story_uk: string | null;
  image_url: string | null;
  founded_year: number | null;
  product_count?: number;
  products?: ProductSummary[];
};
export type Collection = { slug: string; title: string; title_uk: string; lede: string; lede_uk: string; count: number };
export type Category = { slug: string; title: string; title_uk: string; count: number };
/**
 * Locker pickup as the shop has it configured.
 *
 * `enabled` is the only key anything may branch on: the API sets it true only when the
 * PICKUP_ENABLED switch is on AND an address exists, because a bay code with no building
 * to walk to is nothing a buyer can act on. `switch_on` and `address_configured` say which
 * of the two is missing, and exist so a page can tell the two silences apart. `address`,
 * `hours` and `note` are printable text the owner wrote; `null` means unpublished, and a
 * page prints nothing in its place.
 */
export type PickupConfig = {
  enabled: boolean;
  switch_on: boolean;
  address_configured: boolean;
  label: string;
  label_uk: string;
  province: string;
  address: string | null;
  hours: string | null;
  note: string | null;
  /** How many hours a customer's bay code opens the bay. */
  code_valid_hours: number;
};
/** One named sales-tax line (GST, HST, QST, PST, RST, or TAX in custom mode). */
export type TaxLine = { code: string; label: string; label_uk: string; rate: number; amount_cad: number };
/** Who sells, for the terms, privacy and how-it-works pages. null = not published yet. */
export type BusinessIdentity = {
  legal_name: string | null;
  legal_name_uk: string | null;
  address: string | null;
  contact_email: string | null;
  privacy_email: string | null;
  gst_number: string | null;
};
export type PayPalConfig = { client_id: string; env: "sandbox" | "live"; sdk_url: string; currency: string };
export type PayPalOpened = { id: string; status: string; approve_url: string | null };
export type Processor = { kind: "email" | "payments" | "shipping" | "hosting"; name: string | null; data: string };
export type StorefrontConfig = {
  currency: string;
  locales: string[];
  shipping: {
    flat_cad: number;
    free_over_cad: number;
    countries: string[];
    /** Provinces the shop does not ship to, with the sentence that says why. */
    excluded_provinces?: string[];
    excluded_reasons?: Record<string, { en: string; uk: string }>;
  };
  pickup: PickupConfig;
  tax: { configured_provinces: string[]; mode?: "unregistered" | "gst_hst_registered" | "custom"; gst_number?: string | null };
  business?: BusinessIdentity;
  processors?: Processor[];
  payment_methods: ("PAYPAL" | "STRIPE" | "ETRANSFER" | "INVOICE")[];
  /** PayPal JS SDK v6 settings: the browser-safe client id, sandbox or live, and the SDK URL. */
  paypal?: PayPalConfig | null;
  /** False while no payment method can be completed: checkout shows "not taking orders yet". */
  taking_orders?: boolean;
  /** Minutes placing an order sets its stock aside while the buyer pays. */
  hold_minutes?: number;
  /** True when card payments go to the local test page and no money moves. */
  payment_test_mode?: boolean;
  catalogue?: "placeholder" | "live";
  etransfer_email: string | null;
  contact_email: string | null;
};
/** ok: the shop can send the quantity · reduce: it can send max_qty · sold_out: none. */
export type LineStatus = "ok" | "reduce" | "sold_out";
export type QuoteLine = {
  sku: string;
  qty: number;
  unit_price_cad: number | null;
  status: LineStatus;
  max_qty: number;
  /** What the bag prints, in both languages. Absent for a SKU the shop no longer sells. */
  slug?: string | null;
  title?: string | null;
  title_uk?: string | null;
  label?: string | null;
  label_uk?: string | null;
  maker?: string | null;
  maker_uk?: string | null;
  origin?: "HANDMADE_UA" | "MADE_UA" | "DESIGNED_UA" | null;
  image_url?: string | null;
};
export type Quote = {
  lines: QuoteLine[];
  subtotal_cad: number;
  shipping_cad: number;
  tax_cad: number;
  tax_rate: number | null;
  tax_lines?: TaxLine[];
  tax_province: string | null;
  total_cad: number;
  /** Set when the chosen province is one the shop does not ship to. */
  ship_blocked?: { province: string; message: string; message_uk: string } | null;
};
/**
 * Where one buyer's parcel is in the locker, and what may be printed about it.
 *
 * `state` is what a page renders off — never the presence of `code`, because a code is
 * absent in five of the six states for five different reasons, and each one needs its own
 * sentence. `message`/`message_uk` is that sentence, written by the API so it can never
 * imply a code the shop has not minted. `code` is six digits and is non-null in `ready`
 * alone. `valid_until_text` is the instant already formatted with the zone beside it
 * ("2026-09-06 18:40 EDT"); `valid_until` is the same instant for machines.
 */
export type PickupState = "preparing" | "ready" | "opened" | "withdrawn" | "expired" | "collected";
export type OrderPickup = {
  state: PickupState;
  label: string;
  label_uk: string;
  address: string | null;
  hours: string | null;
  note: string | null;
  bay: string | null;
  code: string | null;
  valid_from: string | null;
  valid_until: string | null;
  valid_until_text: string | null;
  valid_hours: number;
  message: string;
  message_uk: string;
};
export type OrderView = {
  order_number: string;
  created_at: string | null;
  status: { key: string; label: string; label_uk: string; raw: string };
  customer: { email: string | null; name: string | null; phone: string | null };
  fulfillment_method: "SHIP" | "PICKUP" | null;
  ship_to: Record<string, string>;
  /** Null for a SHIP order, and for an order placed before this block existed. */
  pickup?: OrderPickup | null;
  lines: { sku: string | null; title: string; title_uk: string | null; label: string | null; label_uk?: string | null; maker?: string | null; maker_uk?: string | null; product_slug: string | null; image_url: string | null; origin: "HANDMADE_UA" | "MADE_UA" | "DESIGNED_UA" | null; qty: number; unit_price_cad: number; line_total_cad: number }[];
  totals: { subtotal_cad: number | null; shipping_cad: number | null; tax_cad: number | null; tax_rate: number | null; tax_lines?: TaxLine[]; total_cad: number };
  /** The shop's GST/HST registration number, when it has one. */
  gst_number?: string | null;
  /** Returned only to the request that placed the order; the web server keeps it in a cookie. */
  access_token?: string;
  payment: { method: string; due: boolean; demo?: boolean; test_mode?: boolean; amount_cad?: number; recipient_email?: string | null; message?: string; checkout_url?: string | null; contact_email?: string | null;
    paypal?: { order_id: string | null; capture_id?: string | null; status: string | null; sandbox: boolean } | null };
  /** Placed while the catalogue was demonstration data: no money should be sent. */
  demo?: boolean;
  paid_at: string | null;
  tracking: { carrier: string | null; code: string | null } | null;
  note: string;
  duplicate?: boolean;
};

export class ApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;
  constructor(status: number, body: unknown) {
    const detail = (body as { detail?: unknown })?.detail;
    const d = typeof detail === "object" && detail ? (detail as Record<string, unknown>) : {};
    super(typeof detail === "string" ? detail : String(d.message || "API error"));
    this.status = status;
    this.code = String(d.code || "error");
    this.details = (d.details as Record<string, unknown>) || {};
  }
}

/**
 * The API could not be reached, or answered with a server error. A loader that catches this
 * knows the catalogue is not empty, only unreadable: the page answers 503 "catching up"
 * (see lib/down.ts) rather than an empty shop.
 */
export class ApiDown extends Error {
  /** Survives Next's production error sanitising, so the error page can say "catching up". */
  digest = "UAM_API_DOWN";
  constructor(message = "API unavailable") {
    super(message);
    this.name = "ApiDown";
  }
}

export function isApiDown(e: unknown): boolean {
  return e instanceof ApiDown || (e instanceof ApiError && e.status >= 500);
}

/** Cache tag on every cached API read; `/admin/api` writes revalidate it (see app/admin/api/[...path]/route.ts). */
export const CATALOG_TAG = "catalog";

async function call<T>(path: string, init: RequestInit & { revalidate?: number } = {}): Promise<T> {
  const { revalidate, ...rest } = init;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...rest,
      headers: { "content-type": "application/json", ...(rest.headers || {}) },
      // Every cached read carries CATALOG_TAG, so an admin save can drop them all at once.
      next: revalidate === undefined ? undefined : { revalidate, tags: [CATALOG_TAG] },
      cache: revalidate === undefined ? "no-store" : undefined,
      signal: rest.signal ?? AbortSignal.timeout(8000),
    });
  } catch (e) {
    throw new ApiDown(e instanceof Error ? e.message : "fetch failed");
  }
  const text = await res.text();
  let body: unknown = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = { detail: text }; }
  if (!res.ok) throw new ApiError(res.status, body);
  return body as T;
}

export type ProductQuery = { category?: string; collection?: string; maker?: string; q?: string; featured?: boolean; in_stock?: boolean; sort?: string; limit?: number; offset?: number };

/**
 * Top-level domains that can never carry mail.
 *
 * `.local` is reserved for mDNS (RFC 6762); `.test`, `.invalid`, `.example`
 * and the `example.*` domains are reserved for documentation (RFC 2606,
 * RFC 6761). A seed value like `hello@uamarket.local` is a placeholder that a
 * page must not print as an address a customer should write to, and must not
 * print as the destination of an e-Transfer. `deliverableEmail` turns such a
 * value into null so every reader falls into the branch it already carries for
 * "the shop has not published an address".
 */
const UNROUTABLE = /(?:\.(?:local|localhost|test|invalid|example|internal)|@example\.(?:com|net|org))$/i;

export function deliverableEmail(value: string | null | undefined): string | null {
  const raw = (value ?? "").trim();
  if (!raw || !raw.includes("@")) return null;
  return UNROUTABLE.test(raw) ? null : raw;
}

/**
 * The config as the storefront may print it: a placeholder address is blanked
 * here rather than in each of the twelve places that read one, so no page can
 * forget the guard.
 */
function usableConfig(cfg: StorefrontConfig): StorefrontConfig {
  return {
    ...cfg,
    etransfer_email: deliverableEmail(cfg.etransfer_email),
    contact_email: deliverableEmail(cfg.contact_email),
    business: cfg.business
      ? { ...cfg.business, contact_email: deliverableEmail(cfg.business.contact_email), privacy_email: deliverableEmail(cfg.business.privacy_email) }
      : cfg.business,
  };
}

function usableOrder(order: OrderView): OrderView {
  return {
    ...order,
    payment: {
      ...order.payment,
      recipient_email: deliverableEmail(order.payment.recipient_email),
      contact_email: deliverableEmail(order.payment.contact_email),
    },
  };
}

export type TestPaymentSession = {
  session_id: string;
  order_number: string;
  locale: "en" | "uk";
  amount_cad: number;
  currency: string;
  state: string;
  paid: boolean;
  demo: boolean;
  return_url: string;
};

/**
 * Headers that tell the API who the visitor is. The storefront server passes the address
 * Caddy wrote into X-Real-IP, and proves it is the storefront with INTERNAL_PROXY_SECRET;
 * without the secret the API ignores the address (app/services/ratelimit.py).
 */
export type Visitor = { ip?: string | null };

function visitorHeaders(visitor?: Visitor, token?: string): Record<string, string> {
  const out: Record<string, string> = {};
  const secret = (process.env.INTERNAL_PROXY_SECRET || "").trim();
  if (visitor?.ip && secret) {
    out["x-client-ip"] = visitor.ip;
    out["x-internal-proxy-secret"] = secret;
  }
  if (token) out["x-order-token"] = token;
  return out;
}

const orderPath = (number: string) => `/v1/storefront/orders/${encodeURIComponent(number)}`;

export const api = {
  config: () => call<StorefrontConfig>("/v1/storefront/config", { revalidate: 60 }).then(usableConfig),
  products: (query: ProductQuery = {}) => {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== "" && v !== null) params.set(k, String(v));
    const qs = params.toString();
    return call<{ items: ProductSummary[]; total: number; suggestion?: { category: string; title: string; title_uk: string } | null }>(`/v1/catalog/products${qs ? `?${qs}` : ""}`, { revalidate: 30 });
  },
  product: (slug: string) => call<Product>(`/v1/catalog/products/${encodeURIComponent(slug)}`, { revalidate: 30 }),
  collections: () => call<{ items: Collection[] }>("/v1/catalog/collections", { revalidate: 60 }),
  categories: () => call<{ items: Category[] }>("/v1/catalog/categories", { revalidate: 60 }),
  makers: () => call<{ items: Maker[] }>("/v1/catalog/makers", { revalidate: 60 }),
  maker: (slug: string) => call<Maker>(`/v1/catalog/makers/${encodeURIComponent(slug)}`, { revalidate: 30 }),
  quote: (body: unknown) => call<Quote>("/v1/storefront/quote", { method: "POST", body: JSON.stringify(body) }),
  placeOrder: (body: unknown, visitor?: Visitor) => call<OrderView>("/v1/storefront/orders", { method: "POST", body: JSON.stringify(body), headers: visitorHeaders(visitor) }).then(usableOrder),
  lookup: (number: string, email: string, visitor?: Visitor) => call<{ order_number: string; access_token: string; locale: string }>("/v1/storefront/orders/lookup", { method: "POST", body: JSON.stringify({ order_number: number, email }), headers: visitorHeaders(visitor) }),
  order: (number: string, token: string, visitor?: Visitor) => call<OrderView>(orderPath(number), { headers: visitorHeaders(visitor, token) }).then(usableOrder),
  retryPayment: (number: string, token: string, visitor?: Visitor) => call<OrderView>(`${orderPath(number)}/pay`, { method: "POST", headers: visitorHeaders(visitor, token) }),
  testPayment: (session: string) => call<TestPaymentSession>(`/v1/payments/test/${encodeURIComponent(session)}`),
  completeTestPayment: (session: string) => call<TestPaymentSession>(`/v1/payments/test/${encodeURIComponent(session)}/complete`, { method: "POST" }),
  paypalOpen: (number: string, token: string, visitor?: Visitor) => call<PayPalOpened>(`${orderPath(number)}/paypal`, { method: "POST", headers: visitorHeaders(visitor, token), signal: AbortSignal.timeout(30000) }),
  paypalCapture: (number: string, token: string, paypalOrderId: string, visitor?: Visitor) => call<OrderView>(`${orderPath(number)}/paypal/capture`, { method: "POST", body: JSON.stringify({ paypal_order_id: paypalOrderId }), headers: visitorHeaders(visitor, token), signal: AbortSignal.timeout(30000) }).then(usableOrder),
  agentStatus: () => call<{ concierge: boolean; model: string | null; paypal: boolean; paypal_env: string }>("/v1/agent/status", { revalidate: 60 }),
  agentShop: (body: unknown, visitor?: Visitor) => call<AgentReply>("/v1/agent/shop", { method: "POST", body: JSON.stringify(body), headers: visitorHeaders(visitor), signal: AbortSignal.timeout(120000) }),
  cancelOrder: (number: string, token: string, visitor?: Visitor) => call<OrderView>(`${orderPath(number)}/cancel`, { method: "POST", headers: visitorHeaders(visitor, token) }).then(usableOrder),
};

export function money(v: number | null | undefined, locale: "en" | "uk" = "en"): string {
  const n = Number(v ?? 0);
  const s = n.toLocaleString(locale === "uk" ? "uk-UA" : "en-CA", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `CA$ ${s}`;
}

/** What the shopping concierge sends back for one turn (app/services/concierge.py). */
export type AgentLine = { sku: string; qty: number; title: string | null; title_uk: string | null; label: string | null; label_uk: string | null; maker: string | null; maker_uk: string | null; unit_price_cad: number | null; image_url: string | null; slug: string | null };
export type AgentCard =
  | { type: "products"; items: { slug: string; title: string; title_uk: string | null; maker: string | null; maker_uk: string | null; price_from_cad: number; price_to_cad: number; image_url: string | null; in_stock: boolean; origin: "HANDMADE_UA" | "MADE_UA" | "DESIGNED_UA"; origin_label: string; origin_label_uk: string }[] }
  | { type: "bag"; lines: AgentLine[]; subtotal_cad: number; shipping_cad: number; free_over_cad: number; budget_cad: number | null; note: string }
  | { type: "checkout"; payment_method: "PAYPAL"; sandbox: boolean; demo: boolean; lines: AgentLine[]; totals: { subtotal_cad: number; shipping_cad: number; tax_cad: number; tax_rate: number | null; tax_lines?: TaxLine[]; total_cad: number }; contact: { email: string; name: string; phone: string | null }; ship_to: Record<string, string | null> }
  | { type: "order"; order_number: string; status: { key: string; label: string; label_uk: string }; paid_at: string | null; total_cad: number };
export type AgentReply = { reply: string; cards: AgentCard[]; trace: { tool: string; args: Record<string, unknown>; ok: boolean }[]; budget_cad: number | null; model: string; sandbox: boolean };
