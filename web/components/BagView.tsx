"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { StorefrontConfig } from "@/lib/api";
import { money } from "@/lib/api";
import { bag, lineFacts, useBag, useQuote } from "@/lib/bag";
import type { Lang } from "@/lib/i18n";
import { href, t } from "@/lib/i18n";
import { tb } from "@/lib/i18n.buy";
import { to } from "@/lib/i18n.order";
import { tu } from "@/lib/i18n.ui";
import { RowsSkeleton, LoadingStatus } from "./Skeleton";
import StitchMark from "./StitchMark";

/**
 * The bag: one row per line, read from the quote in the page's language.
 *
 * The browser keeps SKU, slug and quantity only. Title, variant label, maker, price and
 * availability come back from /api/quote, so the Ukrainian page prints Ukrainian labels and
 * a bag filled on the English page re-labels itself after the language switch.
 */
export default function BagView({ lang, config, demo = false }: {
  lang: Lang;
  config: StorefrontConfig | null;
  /** The catalogue is the seeded one: a bag line names its workshop as an example. */
  demo?: boolean;
}) {
  const d = t(lang);
  const u = tu(lang);
  const o = to(lang);
  const b = tb(lang);
  const items = useBag();
  const { quote, failed } = useQuote(items);
  /** SKUs whose quantity the shop just lowered to what it can send; the line says so. */
  const [clamped, setClamped] = useState<Set<string>>(() => new Set());
  const [ready, setReady] = useState(false);
  /**
   * Taking a line out unmounts the button that was focused, so the focus lands
   * on <body> and nothing is announced. The removal is therefore stated in a
   * live region that exists before the change, and the focus is moved by hand
   * to the next line's Remove button — or to the bag heading when the list
   * empties.
   */
  const [announce, setAnnounce] = useState("");
  const headingRef = useRef<HTMLHeadingElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const focusAfter = useRef<number | null>(null);

  function removeLine(sku: string, title: string, index: number) {
    const left = items.length - 1;
    setAnnounce(u.bag.removed(title, left));
    focusAfter.current = left === 0 ? -1 : Math.min(index, left - 1);
    bag.remove(sku);
  }

  useEffect(() => {
    const at = focusAfter.current;
    if (at === null) return;
    focusAfter.current = null;
    if (at === -1) { headingRef.current?.focus(); return; }
    const buttons = listRef.current?.querySelectorAll<HTMLButtonElement>("[data-remove]");
    buttons?.[at]?.focus();
  }, [items]);

  useEffect(() => setReady(true), []);

  // A line the shop can only partly send is set to the most it can send, once, and the line
  // keeps a sentence saying why its number changed.
  useEffect(() => {
    if (!quote) return;
    const reduce = quote.lines.filter((l) => l.status === "reduce" && l.max_qty > 0);
    if (!reduce.length) return;
    setClamped((prev) => new Set([...prev, ...reduce.map((l) => l.sku)]));
    for (const l of reduce) bag.setQty(l.sku, l.max_qty);
  }, [quote]);

  if (!ready) {
    return (
      <div className="stack">
        <LoadingStatus />
        <h1 className="h1">{b.bagHeading}</h1>
        <RowsSkeleton rows={2} />
      </div>
    );
  }
  if (!items.length) {
    return (
      <div className="stack">
        <p className="sr-only" role="status">{announce}</p>
        <h1 className="h1" ref={headingRef} tabIndex={-1}>{b.bagHeading}</h1>
        <p className="lede">{d.bag.empty}</p>
        <div className="cta-row">
          <Link href={href(lang, "/shop")} className="btn btn--red btn--lg">{d.bag.continue}</Link>
          <Link href={href(lang, "/makers")} className="thread-link ui">{d.nav.makers} →</Link>
        </div>
      </div>
    );
  }
  const count = items.reduce((n, i) => n + i.qty, 0);
  const priced = new Map((quote?.lines || []).map((l) => [l.sku, l]));
  const freeOver = config?.shipping.free_over_cad;
  const resolved = Boolean(quote);

  return (
    <div className="split">
      <div className="split__a stack">
        <p className="sr-only" role="status" aria-label={u.bag.changes}>{announce}</p>
        <div className="bag-head">
          <h1 className="h1" ref={headingRef} tabIndex={-1}>
            {b.bagHeading} <span className="bag-head__count" data-bag-count>· {b.bagCount(count)}</span>
          </h1>
        </div>
        {failed && !quote ? <p className="notice notice--warn" role="status">{b.bagQuoteFailed}</p> : null}
        {!resolved && !failed ? <RowsSkeleton rows={Math.min(items.length, 4)} /> : null}
        <div ref={listRef} hidden={!resolved && !failed}>
          {items.map((i, index) => {
            const live = priced.get(i.sku);
            const facts = lineFacts(lang, i, live);
            const unavailable = quote ? !live || live.status === "sold_out" : false;
            const unit = live?.unit_price_cad ?? null;
            const wasClamped = clamped.has(i.sku) && !unavailable;
            const title = facts.title;
            return (
              <div key={i.sku} className={`bag-line ${unavailable ? "bag-line--out" : ""}`} data-bag-line={i.sku}>
                {/* The photo and the provenance mark share the first cell: the cut list gets
                    the piece it is about, and the mark stays beside it. One cell, so the phone
                    rules below keep counting the same four children. */}
                <span className="bag-line__cell" aria-hidden="true">
                  {facts.image ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img className="bag-line__photo" src={facts.image} alt="" width={56} height={56} loading="lazy" decoding="async" />
                  ) : null}
                  {facts.origin ? <StitchMark origin={facts.origin} lang={lang} /> : null}
                </span>
                <span>
                  <Link href={href(lang, `/product/${facts.slug}`)} className="thread-link" style={{ fontWeight: 500 }}>{title}</Link>
                  <span className="mono mono--sm muted" style={{ display: "block" }} data-bag-label>
                    {[facts.label, facts.maker ? `${facts.maker}${demo ? ` (${d.makers.exampleShort})` : ""}` : null, unavailable ? o.clampSoldOut : null].filter(Boolean).join(" · ")}
                  </span>
                  {wasClamped ? <span className="bag-line__clamp" role="status" data-clamp>{o.clampReduce}</span> : null}
                </span>
                {/* aria-label is ignored on a generic element, so the wrapper
                    is a named group and every control names its own line. */}
                <span className="qty" role="group" aria-label={u.bag.quantity(title)}>
                  <button
                    type="button"
                    onClick={() => (i.qty > 1 ? bag.setQty(i.sku, i.qty - 1) : removeLine(i.sku, title, index))}
                    aria-label={i.qty > 1 ? u.bag.less(title) : u.bag.remove(title)}
                  >
                    −
                  </button>
                  <output>{i.qty}</output>
                  <button type="button" onClick={() => bag.setQty(i.sku, i.qty + 1)} aria-label={u.bag.more(title)}>+</button>
                </span>
                <span style={{ textAlign: "right" }}>
                  <span className="mono" style={{ display: "block" }}>{unit === null ? "—" : money(unit * i.qty, lang)}</span>
                  <button type="button" data-remove className="thread-link mono mono--sm muted" onClick={() => removeLine(i.sku, title, index)} aria-label={u.bag.remove(title)}>{d.bag.remove}</button>
                </span>
              </div>
            );
          })}
        </div>
        <p><Link href={href(lang, "/shop")} className="thread-link ui tap">← {d.bag.continue}</Link></p>
      </div>
      <div className="split__b">
        <div className="receipt sticky">
          <div className="receipt__row"><span>{d.bag.subtotal}</span><span>{quote ? money(quote.subtotal_cad, lang) : "…"}</span></div>
          <div className="receipt__row"><span>{d.bag.shipping}</span><span className="muted">{d.bag.shippingNote}</span></div>
          {freeOver ? <div className="receipt__row"><span className="muted mono--sm">{d.bag.freeOver(money(freeOver, lang))}</span><span /></div> : null}
          {/* Shipping and tax are settled at checkout, so the last row is the
              goods on their own and carries its own label. */}
          <div className="receipt__row receipt__row--total"><span>{u.bag.goodsTotal}</span><span>{quote ? money(quote.subtotal_cad, lang) : "…"}</span></div>
          <p style={{ marginTop: "calc(var(--st) * 2)" }}>
            <Link href={href(lang, "/checkout")} className="btn btn--red btn--lg btn--wide">{d.bag.checkout}</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
