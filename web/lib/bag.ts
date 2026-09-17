"use client";

/**
 * The bag lives in the browser (localStorage) and holds only what identifies a line: the SKU,
 * the product slug and the quantity. Everything printed about a line (title, variant label,
 * maker, photo, price, availability) is read from the API's quote at render time, in the
 * language the page is in, so switching to Ukrainian re-labels a full bag and an edit the
 * owner makes in /admin reaches a bag that was filled yesterday.
 */
import { useEffect, useState } from "react";
import type { Quote, QuoteLine } from "@/lib/api";
import { variantLabel } from "@/lib/i18n.buy";

export type BagItem = { sku: string; slug: string; qty: number };

const KEY = "uamarket.bag.v2";
/** The first bag stored titles and labels as they were written at add time, in one language. */
const LEGACY_KEY = "uamarket.bag.v1";
const EVENT = "uamarket:bag";
/** Fired with {sku, qty} when a line is added from a product page; the header toast listens. */
export const ADDED_EVENT = "uamarket:bag-added";
const MAX_QTY = 20;

function clean(raw: unknown): BagItem[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((i) => i && typeof i.sku === "string" && Number(i.qty) > 0)
    .map((i) => ({ sku: String(i.sku), slug: typeof i.slug === "string" ? i.slug : "", qty: Math.min(MAX_QTY, Math.floor(Number(i.qty))) }));
}

function read(): BagItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (raw !== null) return clean(JSON.parse(raw));
    const legacy = window.localStorage.getItem(LEGACY_KEY);
    if (legacy !== null) {
      const items = clean(JSON.parse(legacy));
      window.localStorage.setItem(KEY, JSON.stringify(items));
      window.localStorage.removeItem(LEGACY_KEY);
      return items;
    }
  } catch {
    /* private mode or a damaged value: an empty bag */
  }
  return [];
}

function write(items: BagItem[]) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(items));
  } catch {
    /* private mode: the bag is per-page then */
  }
  window.dispatchEvent(new CustomEvent(EVENT));
}

export const bag = {
  items: read,
  count: () => read().reduce((n, i) => n + i.qty, 0),
  add(item: { sku: string; slug: string }, qty = 1) {
    const items = read();
    const existing = items.find((i) => i.sku === item.sku);
    if (existing) existing.qty = Math.min(MAX_QTY, existing.qty + qty);
    else items.push({ sku: item.sku, slug: item.slug, qty: Math.min(MAX_QTY, qty) });
    write(items);
    window.dispatchEvent(new CustomEvent(ADDED_EVENT, { detail: { sku: item.sku, qty } }));
  },
  setQty(sku: string, qty: number) {
    const items = read().map((i) => (i.sku === sku ? { ...i, qty: Math.max(0, Math.min(MAX_QTY, qty)) } : i)).filter((i) => i.qty > 0);
    write(items);
  },
  remove(sku: string) {
    write(read().filter((i) => i.sku !== sku));
  },
  clear() {
    write([]);
  },
};

/** Subscribe a component to the bag. Returns [] on the server and on first paint (hydration-safe). */
export function useBag(): BagItem[] {
  const [items, setItems] = useState<BagItem[]>([]);
  useEffect(() => {
    const sync = () => setItems(read());
    sync();
    window.addEventListener(EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  return items;
}

/**
 * The quote for the bag's lines: prices, availability and what to print, re-read whenever the
 * bag, the delivery method or the province changes. `failed` is true when the shop could not
 * be asked, which a page must tell apart from an empty answer.
 */
export function useQuote(items: BagItem[], opts: { method?: "SHIP" | "PICKUP"; province?: string } = {}) {
  const [quote, setQuote] = useState<Quote | null>(null);
  const [failed, setFailed] = useState(false);
  const lines = JSON.stringify(items.map((i) => ({ sku: i.sku, qty: i.qty })));
  const method = opts.method ?? "SHIP";
  const province = opts.province;
  useEffect(() => {
    const parsed = JSON.parse(lines) as { sku: string; qty: number }[];
    if (!parsed.length) { setQuote(null); setFailed(false); return; }
    const ctrl = new AbortController();
    fetch("/api/quote", {
      method: "POST",
      headers: { "content-type": "application/json" },
      signal: ctrl.signal,
      body: JSON.stringify({ lines: parsed, fulfillment_method: method, ...(province ? { ship_to: { province } } : {}) }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((q: Quote) => { setQuote(q); setFailed(false); })
      .catch((e) => { if ((e as Error).name !== "AbortError") setFailed(true); });
    return () => ctrl.abort();
  }, [lines, method, province]);
  return { quote, failed };
}

/** The printable facts of one bag line, in the page's language, from the quote. */
export function lineFacts(lang: "en" | "uk", item: BagItem, line: QuoteLine | undefined) {
  const uk = lang === "uk";
  const title = (uk && line?.title_uk) || line?.title || item.slug.replace(/-/g, " ");
  const label = variantLabel(lang, line?.label, line?.label_uk);
  const maker = (uk && line?.maker_uk) || line?.maker || null;
  return { title, label, maker, slug: line?.slug || item.slug, origin: line?.origin ?? null, image: line?.image_url ?? null, price: line?.unit_price_cad ?? null };
}

export function idempotencyKey(): string {
  const k = `web-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  return k;
}
