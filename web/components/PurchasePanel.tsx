"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import type { Product, Variant } from "@/lib/api";
import { money } from "@/lib/api";
import { bag } from "@/lib/bag";
import type { Lang } from "@/lib/i18n";
import { href, t } from "@/lib/i18n";
import { to } from "@/lib/i18n.order";
import { variantLabel } from "@/lib/i18n.buy";
import { listWords, tpd } from "@/lib/i18n.product";

/**
 * Variant picker, quantity and add-to-bag.
 *
 * Two rules run through it.
 *
 * HONESTY. Availability is never implied by a strike-through alone. A size that
 * is struck out says why in its accessible name, and the line under the picker
 * distinguishes the three cases the catalogue can produce: the combination
 * exists and is sold out, the combination is not offered in the chosen colour
 * (and then which colours do carry that size), or the size is not offered for
 * this piece at all. The add-to-bag control stays reachable when it cannot be
 * used, so a keyboard or screen-reader buyer hears the reason instead of
 * meeting a control that has vanished from the tab order.
 *
 * KEYBOARD. Each option axis is a real radio group: one tab stop, arrows move
 * and choose, Home/End jump to the ends. Before this, every swatch was its own
 * tab stop — eighteen of them on the everyday blouse.
 *
 * Below 1024px — the width at which the buy column stops sitting beside the
 * gallery — the panel raises a fixed bar carrying the price and the add-to-bag
 * button once the panel itself has scrolled away, so the two things a buyer
 * needs are never a scroll back up. The bar adds its own bottom padding to the
 * page while it is up, so it covers nothing.
 */

/** Fired with {sku} whenever the chosen variant changes; components/SelectedSku.tsx listens. */
export const SELECTED_EVENT = "uamarket:variant";

type OptionState = "ok" | "out" | "missing";
type Option = { value: string; label: string; state: OptionState; suffix?: string };

/** One axis of the picker: a radio group with roving focus. */
function OptionGroup({
  label,
  chosenLabel,
  options,
  value,
  onPick,
  wide = false,
}: {
  label: string;
  chosenLabel: string;
  options: Option[];
  value: string | undefined;
  onPick: (v: string) => void;
  wide?: boolean;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const current = options.findIndex((o) => o.value === value);

  function move(to: number) {
    const n = options.length;
    if (!n) return;
    const i = ((to % n) + n) % n;
    onPick(options[i].value);
    refs.current[i]?.focus();
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const from = current < 0 ? 0 : current;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); move(from + 1); }
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); move(from - 1); }
    else if (e.key === "Home") { e.preventDefault(); move(0); }
    else if (e.key === "End") { e.preventDefault(); move(options.length - 1); }
  }

  return (
    <div className="field">
      <span className="field__label">
        {label}: <span className="muted" style={{ fontWeight: 400 }}>{chosenLabel}</span>
      </span>
      <div className="swatches" role="radiogroup" aria-label={label} onKeyDown={onKeyDown}>
        {options.map((o, i) => {
          const on = o.value === value;
          const tab = current < 0 ? (i === 0 ? 0 : -1) : on ? 0 : -1;
          return (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={on}
              tabIndex={tab}
              ref={(el) => { refs.current[i] = el; }}
              className="swatch"
              data-on={on}
              data-out={o.state !== "ok"}
              onClick={() => onPick(o.value)}
              style={wide ? { paddingInline: "var(--st)" } : undefined}
            >
              {o.label}
              {o.suffix ? <span className="sr-only">, {o.suffix}</span> : null}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function PurchasePanel({
  product,
  lang,
  sizeGuideId,
}: {
  product: Product;
  lang: Lang;
  /** Anchor of the size guide further down the page, when the piece has sizes. */
  sizeGuideId?: string;
}) {
  const d = t(lang);
  const p = tpd(lang).picker;
  const variants = product.variants;

  const axes = useMemo(() => {
    const colours = Array.from(new Set(variants.map((v) => v.options.colour).filter(Boolean)));
    const sizes = Array.from(new Set(variants.map((v) => v.options.size).filter(Boolean)));
    return { colours, sizes, single: !colours.length && !sizes.length };
  }, [variants]);

  const firstInStock = variants.find((v) => v.availability.in_stock) || variants[0];
  const [colour, setColour] = useState<string | undefined>(firstInStock?.options.colour);
  const [size, setSize] = useState<string | undefined>(firstInStock?.options.size);
  const [single, setSingle] = useState<string | undefined>(firstInStock?.sku);
  const [qty, setQty] = useState(1);
  const [added, setAdded] = useState<string | null>(null);
  /** True when the shop could not send as many as the bag now asked for, and lowered it. */
  const [capped, setCapped] = useState(false);

  const colourLabel = (c: string) => {
    const v = variants.find((x) => x.options.colour === c);
    return lang === "uk" && v?.options.colour_uk ? v.options.colour_uk : c;
  };
  const singleLabel = (v: Variant) => (lang === "uk" && (v.label_uk || v.options.option_uk) ? (v.label_uk || v.options.option_uk) : variantLabel(lang, v.label, null));
  /** The whole variant label in the page's language ("Цегляна з чорним / S"). */
  const fullLabel = (v: Variant) => (axes.single ? singleLabel(v) : variantLabel(lang, v.label, v.label_uk));

  /** The variant for the current choice, or undefined when there is no such variant. */
  const selected: Variant | undefined = axes.single
    ? variants.find((v) => v.sku === single)
    : variants.find(
        (v) =>
          (!axes.colours.length || v.options.colour === colour) &&
          (!axes.sizes.length || v.options.size === size),
      );

  /** A size, inside the chosen colour: offered and in stock, offered and sold out, or absent. */
  function sizeState(s: string): OptionState {
    const inColour = variants.filter((v) => v.options.size === s && (!axes.colours.length || v.options.colour === colour));
    if (!inColour.length) return "missing";
    return inColour.some((v) => v.availability.in_stock) ? "ok" : "out";
  }
  function colourState(c: string): OptionState {
    const inColour = variants.filter((v) => v.options.colour === c);
    if (!inColour.length) return "missing";
    return inColour.some((v) => v.availability.in_stock) ? "ok" : "out";
  }
  /** Colours that carry a given size and have it in stock. */
  function coloursWith(s: string): string[] {
    return axes.colours.filter((c) => variants.some((v) => v.options.colour === c && v.options.size === s && v.availability.in_stock));
  }

  const canBuy = Boolean(selected && selected.availability.in_stock);
  const price = selected ? selected.price_cad : product.price_from_cad;
  const chosenName = selected ? fullLabel(selected) : null;

  /** The one true sentence about the current choice. */
  const status: { text: string; tone: string; detail: string | null } = (() => {
    const needsColour = axes.colours.length > 0 && !colour;
    const needsSize = axes.sizes.length > 0 && !size;
    if (needsColour || needsSize || (axes.single && !single)) {
      return { text: d.product.chooseOption, tone: "status--warn", detail: null };
    }
    if (!selected) {
      // The colour and the size are both chosen, and the catalogue has no such
      // variant. Say that, and say where the size does exist.
      const s = size ?? "";
      const also = coloursWith(s).map(colourLabel);
      const here = axes.colours.length && colour ? p.sizeNotInColour(s, colourLabel(colour)) : p.sizeNowhere(s);
      return {
        text: p.unavailableHere,
        tone: "status--warn",
        detail: also.length ? `${here} ${p.sizeComesIn(listWords(lang, also))}` : here,
      };
    }
    if (!selected.availability.in_stock) {
      return {
        text: d.product.soldOut,
        tone: "status--bad",
        detail: axes.colours.length && colour ? p.soldOutIn(colourLabel(colour)) : null,
      };
    }
    return {
      text: selected.availability.low ? d.product.lowStock : d.product.inStock,
      tone: selected.availability.low ? "status--warn" : "status--ok",
      detail: null,
    };
  })();

  /**
   * The confirmation clears itself after four seconds, which took the "View
   * bag" link out from under a keyboard user's focus (WCAG 2.2.1). The timer
   * now waits while the focus is inside the notice.
   */
  const noticeRef = useRef<HTMLDivElement>(null);
  const timer = useRef<number | null>(null);
  function scheduleClear() {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      if (noticeRef.current?.contains(document.activeElement)) { scheduleClear(); return; }
      setAdded(null);
      timer.current = null;
    }, 4000);
  }
  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);

  function add() {
    if (!selected || !canBuy) return;
    // The bag keeps the SKU and the slug; the toast and the bag read the words from the quote.
    bag.add({ sku: selected.sku, slug: product.slug }, qty);
    setAdded(selected.sku);
    setCapped(false);
    scheduleClear();
    // The picker caps the same way the bag does: ask the shop how many of this line it can
    // send, and lower the bag to that when it holds more.
    const sku = selected.sku;
    const inBag = bag.items().find((i) => i.sku === sku)?.qty ?? qty;
    fetch("/api/quote", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ lines: [{ sku, qty: inBag }], fulfillment_method: "SHIP" }),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((q: { lines?: { sku: string; status: string; max_qty: number }[] } | null) => {
        const line = q?.lines?.find((l) => l.sku === sku);
        if (line && line.status === "reduce" && line.max_qty > 0) {
          bag.setQty(sku, line.max_qty);
          setQty((n) => Math.min(n, line.max_qty));
          setCapped(true);
        }
      })
      .catch(() => {});
  }

  // The specification table further down prints the SKU of the current choice.
  useEffect(() => {
    window.dispatchEvent(new CustomEvent(SELECTED_EVENT, { detail: { sku: selected?.sku ?? null } }));
  }, [selected?.sku]);

  // The phone bar: up only once the panel's own buy row has scrolled up past the top of the
  // screen. While the row is still below the fold (the gallery comes first on a phone) the
  // bar stays down, so it never covers the photo a buyer is looking at.
  const anchor = useRef<HTMLDivElement>(null);
  const [barOn, setBarOn] = useState(false);
  useEffect(() => {
    const el = anchor.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    // Same breakpoint as the CSS above: single-column layout, bar allowed.
    const phone = window.matchMedia("(max-width: 1023px)");
    let above = false;
    const apply = () => setBarOn(phone.matches && above);
    const io = new IntersectionObserver((entries) => {
      const entry = entries[entries.length - 1];
      above = !entry.isIntersecting && entry.boundingClientRect.bottom <= 0;
      apply();
    });
    io.observe(el);
    phone.addEventListener("change", apply);
    return () => { io.disconnect(); phone.removeEventListener("change", apply); };
  }, []);
  useEffect(() => {
    document.body.classList.toggle("pd-bar-on", barOn);
    return () => document.body.classList.remove("pd-bar-on");
  }, [barOn]);

  const buyButton = (
    <button
      type="button"
      className="btn btn--red btn--lg"
      style={{ flex: 1 }}
      onClick={add}
      aria-disabled={!canBuy}
    >
      {canBuy ? d.product.addToBag : status.text}
    </button>
  );

  return (
    <div className="stack">
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      <div className="mono mono--price" aria-live="polite">{money(price, lang)}</div>

      {axes.colours.length ? (
        <OptionGroup
          label={d.product.colour}
          chosenLabel={colour ? colourLabel(colour) : d.product.chooseOption}
          value={colour}
          onPick={setColour}
          options={axes.colours.map((c) => {
            const state = colourState(c);
            return { value: c, label: colourLabel(c), state, suffix: state === "ok" ? undefined : p.colourAllSoldOut };
          })}
        />
      ) : null}

      {axes.sizes.length ? (
        <div className="stack--tight">
          <OptionGroup
            label={d.product.size}
            chosenLabel={size || d.product.chooseOption}
            value={size}
            onPick={setSize}
            options={axes.sizes.map((s) => {
              const state = sizeState(s);
              return {
                value: s,
                label: s,
                state,
                suffix: state === "out" ? d.product.soldOut : state === "missing" ? p.unavailableHere : undefined,
              };
            })}
          />
          {sizeGuideId ? (
            // A native anchor: <Link href="#…"> is a no-op on the current URL.
            <p className="ui"><a href={`#${sizeGuideId}`} className="thread-link tap">{tpd(lang).sizeGuide.link} ↓</a></p>
          ) : null}
        </div>
      ) : null}

      {axes.single && variants.length > 1 ? (
        <OptionGroup
          label={d.product.option}
          chosenLabel={selected ? singleLabel(selected) : d.product.chooseOption}
          value={single}
          onPick={setSingle}
          wide
          options={variants.map((v) => ({
            value: v.sku,
            label: `${singleLabel(v)} · ${money(v.price_cad, lang)}`,
            state: v.availability.in_stock ? "ok" : "out",
            suffix: v.availability.in_stock ? undefined : d.product.soldOut,
          }))}
        />
      ) : null}

      <div role="status" className="stack--tight">
        <p className="key" style={{ color: "var(--ink)" }}>
          <span className={`status ${status.tone}`}>{status.text}</span>
        </p>
        {status.detail ? <p className="mono mono--sm muted">{status.detail}</p> : null}
      </div>

      <div ref={anchor} style={{ display: "flex", gap: "var(--st)", alignItems: "stretch", flexWrap: "wrap" }}>
        {/* aria-label is ignored on a generic element: the wrapper is a group. */}
        <div className="qty" role="group" aria-label={d.product.qty}>
          <button type="button" onClick={() => setQty((q) => Math.max(1, q - 1))} aria-label={p.qtyLess}>−</button>
          <output aria-live="polite">{qty}</output>
          <button type="button" onClick={() => setQty((q) => Math.min(20, q + 1))} aria-label={p.qtyMore}>+</button>
        </div>
        {buyButton}
      </div>

      {/* The live region is mounted from the first render, so a screen reader
          is watching it before anything lands in it. */}
      <div role="status" ref={noticeRef}>
        {/* "Added" itself is said once, by the toast under the header (BagToast). The panel
            speaks only when the shop lowered the quantity. */}
        {added && capped ? (
          <p className="notice notice--warn">
            {to(lang).clampReduce} <Link href={href(lang, "/bag")} className="thread-link thread-link--on">{d.product.viewBag} →</Link>
          </p>
        ) : null}
      </div>

      {barOn ? (
        <div className="pd-bar" role="region" aria-label={p.buyBar}>
          <div className="pd-bar__in canvas">
            <div>
              <span className="mono pd-bar__price">{money(price, lang)}</span>
              {/* While the bar is up the panel's own confirmation has scrolled
                  away, so the bar carries it: the buyer sees that the tap
                  landed, and the way to the bag, without scrolling back. */}
              {added ? (
                <Link href={href(lang, "/bag")} className="thread-link thread-link--on ui pd-bar__name">{d.product.viewBag} →</Link>
              ) : chosenName ? (
                <span className="mono mono--sm muted pd-bar__name">{chosenName}</span>
              ) : null}
            </div>
            <button type="button" className="btn btn--red" onClick={add} aria-disabled={!canBuy}>
              {added ? d.product.added : canBuy ? d.product.addToBag : status.text}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/* The phone buy bar. Linen ground, one hairline, no radius, no shadow, no
   entrance animation — it is either there or it is not. */
const CSS = `
.pd-bar { position: fixed; left: 0; right: 0; bottom: 0; z-index: 25; background: var(--linen-bleached); border-top: 1px solid var(--thread-black); }
.pd-bar__in { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--st); align-items: center; padding-block: var(--st); }
.pd-bar__price { display: block; font-size: 20px; line-height: 24px; }
.pd-bar__name { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
body.pd-bar-on { padding-bottom: calc(var(--st) * 8); }
/* The buy column only moves beside the gallery at 1024 (.split in
   globals.css), so below that the page is one column and the bar is the
   only place the price and the button stay reachable. */
@media (min-width: 1024px) { .pd-bar { display: none; } body.pd-bar-on { padding-bottom: 0; } }
`;
