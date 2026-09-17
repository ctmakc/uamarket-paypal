"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { OrderView, StorefrontConfig } from "@/lib/api";
import { money } from "@/lib/api";
import { bag, idempotencyKey, lineFacts, useBag, useQuote } from "@/lib/bag";
import type { Lang } from "@/lib/i18n";
import { PROVINCES, href, pick, t } from "@/lib/i18n";
import { tb } from "@/lib/i18n.buy";
import { mailNotice, tm } from "@/lib/i18n.mail";
import { to } from "@/lib/i18n.order";
import { pickupOption } from "@/lib/i18n.pickup";

type Method = "SHIP" | "PICKUP";
type Field = "email" | "name" | "street1" | "city" | "postal" | "province" | "terms";

/** The order fields are checked in this order; the first one with a message takes the focus. */
const FIELD_ORDER: Field[] = ["email", "name", "street1", "city", "postal", "province", "terms"];
const POSTAL = /^[A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d$/;

export default function CheckoutForm({ lang, config, shipLabel, demo }: {
  lang: Lang;
  config: StorefrontConfig;
  /** "Ship by <carrier>", or a carrier-free label while none is configured. */
  shipLabel: string;
  /** The catalogue is demonstration data: the button carries the demo line beside it. */
  demo: boolean;
}) {
  const d = t(lang);
  const o = to(lang);
  const b = tb(lang);
  const takingOrders = config.taking_orders ?? config.payment_methods.length > 0;
  // Whether the shop can send email decides what the checkout is allowed to promise.
  const mail = mailNotice(config);
  const mt = tm(lang);
  const router = useRouter();
  const items = useBag();
  const [ready, setReady] = useState(false);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [method, setMethod] = useState<Method>("SHIP");
  const [street1, setStreet1] = useState("");
  const [street2, setStreet2] = useState("");
  const [city, setCity] = useState("");
  const [province, setProvince] = useState("ON");
  const [postal, setPostal] = useState("");
  const [payment, setPayment] = useState<string>(config.payment_methods[0] ?? "");
  const [note, setNote] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  /** The whole-form message (stock, rate limit, a server refusal). */
  const [error, setError] = useState<string | null>(null);
  /** One message per field. Typing in a field clears its own message. */
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<Field, string>>>({});
  // A failed submit that repeats the same message re-renders an identical
  // string, so the DOM never changes and role="alert" stays silent the second
  // time. The counter changes the alert's key, which remounts it and makes the
  // live region announce every attempt.
  const [attempt, setAttempt] = useState(0);
  const [key] = useState(() => idempotencyKey());
  const formRef = useRef<HTMLFormElement>(null);
  const { quote } = useQuote(items, { method, province: method === "SHIP" ? province : undefined });

  useEffect(() => setReady(true), []);

  function clearField(field: Field) {
    setFieldErrors((prev) => {
      if (!prev[field]) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
  }

  /** The ids described to one field: its own error first, then its hint. */
  function describedBy(field: Field, hintId?: string): string | undefined {
    const parts = [fieldErrors[field] ? `${field}-error` : null, hintId].filter(Boolean);
    return parts.length ? parts.join(" ") : undefined;
  }

  function FieldError({ field }: { field: Field }) {
    const message = fieldErrors[field];
    if (!message) return null;
    return <p id={`${field}-error`} className="error" data-field-error={field}>{message}</p>;
  }

  function focusFirst(errors: Partial<Record<Field, string>>) {
    const first = FIELD_ORDER.find((f) => errors[f]);
    if (!first) return;
    window.requestAnimationFrame(() => formRef.current?.querySelector<HTMLElement>(`#${first}`)?.focus());
  }

  const excluded = config.shipping.excluded_provinces ?? [];
  const blockedReason = method === "SHIP" && excluded.includes(province)
    ? (quote?.ship_blocked ? pick(lang, quote.ship_blocked.message, quote.ship_blocked.message_uk) : pick(lang, config.shipping.excluded_reasons?.[province]?.en, config.shipping.excluded_reasons?.[province]?.uk))
    : null;

  function validate(): Partial<Record<Field, string>> {
    const errors: Partial<Record<Field, string>> = {};
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) errors.email = d.checkout.errors.email;
    if (name.trim().length < 2) errors.name = d.checkout.errors.name;
    if (method === "SHIP") {
      if (!street1.trim()) errors.street1 = b.checkout.street1;
      if (!city.trim()) errors.city = b.checkout.city;
      if (!POSTAL.test(postal.trim())) errors.postal = b.checkout.postal;
      if (blockedReason) errors.province = blockedReason;
    }
    if (!accepted) errors.terms = b.checkout.acceptError;
    return errors;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length) {
      setAttempt((n) => n + 1);
      focusFirst(errors);
      return;
    }
    setBusy(true);
    try {
      const res = await fetch("/api/order", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({
          idempotency_key: key, email: email.trim(), name: name.trim(), phone: phone.trim() || null, locale: lang,
          fulfillment_method: method,
          ship_to: method === "SHIP" ? { name: name.trim(), street1: street1.trim(), street2: street2.trim() || null, city: city.trim(), province, postal_code: postal.trim(), country: "CA" } : null,
          payment_method: payment, note: note.trim() || null, lines: items.map((i) => ({ sku: i.sku, qty: i.qty })),
          terms_accepted: accepted,
        }),
      });
      const body = await res.json();
      if (!res.ok) {
        setBusy(false);
        const code = String(body?.code || "");
        if (code === "email" || code === "name") {
          const errs = { [code]: d.checkout.errors[code] } as Partial<Record<Field, string>>;
          setFieldErrors(errs); focusFirst(errs); setAttempt((n) => n + 1);
          return;
        }
        if (code === "ship_to") {
          const errs: Partial<Record<Field, string>> = { street1: d.checkout.errors.ship_to };
          setFieldErrors(errs); focusFirst(errs); setAttempt((n) => n + 1);
          return;
        }
        if (code === "province_excluded") {
          const message = lang === "uk" ? String(body?.details?.message_uk || body?.message) : String(body?.message);
          const errs: Partial<Record<Field, string>> = { province: message };
          setFieldErrors(errs); focusFirst(errs); setAttempt((n) => n + 1);
          return;
        }
        const shortLines = code === "out_of_stock" ? namedLines((body?.details?.lines || body?.details?.skus || []) as ({ sku: string } | string)[]) : [];
        const known = d.checkout.errors as Record<string, string>;
        setError(shortLines.length ? shortLines.map((title) => o.lineShort(title)).join(" ") : known[code] || d.checkout.errors.generic);
        setAttempt((n) => n + 1);
        return;
      }
      const order = body as OrderView;
      bag.clear();
      if (order.payment?.checkout_url) {
        window.location.assign(order.payment.checkout_url);
        return;
      }
      // The server set this order's key in an HttpOnly cookie: the address carries the number only.
      router.push(`${href(lang, `/order/${order.order_number}`)}?placed=1`);
    } catch {
      setError(d.checkout.errors.generic);
      setBusy(false);
    }
  }

  /** Bag titles for the SKUs the API named, in the buyer's language. */
  function namedLines(named: ({ sku: string } | string)[]): string[] {
    const priced = new Map((quote?.lines || []).map((l) => [l.sku, l]));
    return named
      .map((line) => (typeof line === "string" ? line : line.sku))
      .map((sku) => items.find((i) => i.sku === sku))
      .filter((i): i is NonNullable<typeof i> => Boolean(i))
      .map((i) => {
        const f = lineFacts(lang, i, priced.get(i.sku));
        return f.label ? `${f.title} (${f.label})` : f.title;
      });
  }

  if (!ready) return <p className="muted">{d.common.loading}</p>;
  if (!takingOrders) {
    // No method a buyer could complete: one plain state, and no button that would take an order.
    return (
      <div className="stack" data-checkout-closed>
        <h1 className="h1">{d.checkout.title}</h1>
        <div className="plate stack--tight closed-plate">
          <p className="h3">{o.closedTitle}</p>
          <p className="measure">{o.closedBody}</p>
          {config.contact_email ? <p className="mono mono--sm muted">{o.closedContact(config.contact_email)}</p> : null}
        </div>
        <p><Link href={href(lang, "/bag")} className="thread-link ui tap">← {o.backToBag}</Link></p>
      </div>
    );
  }
  if (!items.length) {
    return (
      <div className="stack">
        <h1 className="h1">{d.checkout.title}</h1>
        <p className="lede">{d.bag.empty}</p>
        <p><Link href={href(lang, "/shop")} className="btn btn--red">{d.bag.continue}</Link></p>
      </div>
    );
  }

  const pickup = pickupOption(config.pickup, lang, money(0, lang));
  const priced = new Map((quote?.lines || []).map((l) => [l.sku, l]));
  // Lines the shop cannot send in full right now, named before the buyer presses the button.
  const quoteShort = quote
    ? quote.lines
        .filter((l) => l.status && l.status !== "ok")
        .flatMap((l) => namedLines([l]).map((title) => (l.status === "sold_out" ? o.lineSoldOut(title) : o.lineShort(title))))
    : [];
  const payLabel = (m: string) => (m === "STRIPE" ? (config.payment_test_mode ? o.payTest : d.checkout.payStripe) : m === "ETRANSFER" ? d.checkout.payEtransfer : d.checkout.payInvoice);
  // The e-Transfer and by-arrangement lines in lib/i18n.ts promise a follow-up email.
  // With email switched off the order page takes over that job, and says so.
  const paySub = (m: string) => {
    if (m === "STRIPE") return config.payment_test_mode ? o.payTestSub : d.checkout.payStripeSub;
    if (m === "ETRANSFER") {
      const recipient = config.etransfer_email;
      if (!recipient) return mt.payEtransferNoRecipient;
      return mail.email ? d.checkout.payEtransferSub(recipient) : mt.payEtransferNoEmail(recipient);
    }
    return mail.email ? d.checkout.payInvoiceSub : mt.payInvoiceNoEmail(config.contact_email);
  };
  const excludedNames = excluded.map((code) => PROVINCES.find((p) => p.code === code)).filter(Boolean).map((p) => (lang === "uk" ? p!.uk : p!.en));
  const placeDisabled = busy || !accepted || quoteShort.length > 0 || Boolean(blockedReason);
  const input = (field: Field, set: (v: string) => void) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    set(e.target.value);
    clearField(field);
  };

  return (
    <form ref={formRef} className="split" onSubmit={submit} noValidate data-checkout>
      <div className="split__a stack--loose">
        <h1 className="h1">{d.checkout.title}</h1>

        <fieldset className="stack" style={{ border: 0, padding: 0, minInlineSize: 0 }}>
          <legend className="h3" style={{ marginBottom: "var(--st)" }}>{d.checkout.contact}</legend>
          <div className="field">
            <label className="field__label" htmlFor="email">{d.checkout.email}</label>
            <input id="email" className="input" type="email" autoComplete="email" inputMode="email" value={email} onChange={input("email", setEmail)} aria-invalid={Boolean(fieldErrors.email)} aria-describedby={describedBy("email", "email-hint")} required />
            <FieldError field="email" />
            <p id="email-hint" className="mono mono--sm muted">{mail.email ? mt.confirmTo(mail.from) : mt.noEmailAtCheckout}</p>
          </div>
          <div className="blocks" style={{ rowGap: "var(--st)" }}>
            <div className="field span-7"><label className="field__label" htmlFor="name">{d.checkout.name}</label><input id="name" className="input" autoComplete="name" value={name} onChange={input("name", setName)} aria-invalid={Boolean(fieldErrors.name)} aria-describedby={describedBy("name")} required /><FieldError field="name" /></div>
            <div className="field span-5"><label className="field__label" htmlFor="phone">{d.checkout.phone}</label><input id="phone" className="input" type="tel" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} /></div>
          </div>
        </fieldset>

        <fieldset className="stack" style={{ border: 0, padding: 0, minInlineSize: 0 }}>
          <legend className="h3" style={{ marginBottom: "var(--st)" }}>{d.checkout.delivery}</legend>
          <label className="choice" data-on={method === "SHIP"}>
            <input type="radio" name="method" checked={method === "SHIP"} onChange={() => setMethod("SHIP")} />
            <span>
              <span className="ui" style={{ display: "block" }}>{shipLabel}</span>
              <span className="mono mono--sm muted">{money(config.shipping.flat_cad, lang)} · {d.bag.freeOver(money(config.shipping.free_over_cad, lang))}</span>
              {excludedNames.length ? <span className="mono mono--sm muted" style={{ display: "block" }} data-excluded-note>{b.excluded(excludedNames.join(", "))}</span> : null}
            </span>
          </label>
          {/* Pickup as this deployment actually has it: `enabled` is true only when the shop
              has configured an address, so a shop that has not said where the locker is offers
              no pickup here at all. */}
          {config.pickup.enabled ? (
            <label className="choice" data-on={method === "PICKUP"}>
              <input type="radio" name="method" checked={method === "PICKUP"} onChange={() => setMethod("PICKUP")} />
              <span>
                <span className="ui" style={{ display: "block" }}>{pickup.label}</span>
                {pickup.lines.map((line) => (
                  <span key={line} className="mono mono--sm muted" style={{ display: "block" }}>{line}</span>
                ))}
              </span>
            </label>
          ) : null}
          {method === "SHIP" ? (
            <div className="stack" style={{ paddingTop: "var(--st)" }}>
              <div className="field"><label className="field__label" htmlFor="street1">{d.checkout.street1}</label><input id="street1" className="input" autoComplete="address-line1" value={street1} onChange={input("street1", setStreet1)} aria-invalid={Boolean(fieldErrors.street1)} aria-describedby={describedBy("street1")} /><FieldError field="street1" /></div>
              <div className="field"><label className="field__label" htmlFor="street2">{d.checkout.street2}</label><input id="street2" className="input" autoComplete="address-line2" value={street2} onChange={(e) => setStreet2(e.target.value)} /></div>
              <div className="blocks checkout-addr" style={{ rowGap: "var(--st)" }}>
                <div className="field span-5"><label className="field__label" htmlFor="city">{d.checkout.city}</label><input id="city" className="input" autoComplete="address-level2" value={city} onChange={input("city", setCity)} aria-invalid={Boolean(fieldErrors.city)} aria-describedby={describedBy("city")} /><FieldError field="city" /></div>
                <div className="field span-4"><label className="field__label" htmlFor="province">{d.checkout.province}</label>
                  <select id="province" className="select" autoComplete="address-level1" value={province} onChange={input("province", setProvince)} aria-invalid={Boolean(blockedReason)} aria-describedby={blockedReason ? "province-error" : undefined}>
                    {PROVINCES.map((p) => <option key={p.code} value={p.code}>{lang === "uk" ? p.uk : p.en}</option>)}
                  </select>
                </div>
                <div className="field span-3"><label className="field__label" htmlFor="postal">{d.checkout.postal}</label><input id="postal" className="input mono" autoComplete="postal-code" placeholder="K1A 0B1" value={postal} onChange={input("postal", (v) => setPostal(v.toUpperCase()))} aria-invalid={Boolean(fieldErrors.postal)} aria-describedby={describedBy("postal")} /><FieldError field="postal" /></div>
              </div>
              {blockedReason ? <p id="province-error" className="error" role="alert" data-province-blocked>{blockedReason}</p> : null}
            </div>
          ) : null}
        </fieldset>

        <fieldset className="stack" style={{ border: 0, padding: 0, minInlineSize: 0 }}>
          <legend className="h3" style={{ marginBottom: "var(--st)" }}>{d.checkout.payment}</legend>
          {config.payment_methods.map((m) => (
            <label key={m} className="choice" data-on={payment === m}>
              <input type="radio" name="payment" checked={payment === m} onChange={() => setPayment(m)} />
              <span>
                <span className="ui" style={{ display: "block" }}>{payLabel(m)}</span>
                <span className="mono mono--sm muted">{paySub(m)}</span>
              </span>
            </label>
          ))}
        </fieldset>

        <div className="field">
          <label className="field__label" htmlFor="note">{d.checkout.note}</label>
          <textarea id="note" className="textarea" value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} />
        </div>
      </div>

      <div className="split__b">
        <div className="receipt sticky">
          <div className="h3" style={{ fontFamily: "var(--face-display)", marginBottom: "var(--st)" }}>{d.checkout.summary}</div>
          {items.map((i) => {
            const f = lineFacts(lang, i, priced.get(i.sku));
            const unit = priced.get(i.sku)?.unit_price_cad;
            return (
              <div key={i.sku} className="receipt__row" data-summary-line={i.sku}>
                <span>{i.qty} × {f.title} {f.label ? <span className="muted">{f.label}</span> : null}</span>
                <span>{unit == null ? "…" : money(unit * i.qty, lang)}</span>
              </div>
            );
          })}
          <div className="receipt__row" style={{ marginTop: "var(--st)" }}><span>{d.bag.subtotal}</span><span>{quote ? money(quote.subtotal_cad, lang) : "…"}</span></div>
          <div className="receipt__row"><span>{d.bag.shipping}</span><span>{quote ? money(quote.shipping_cad, lang) : "…"}</span></div>
          {quote?.tax_lines?.length
            ? quote.tax_lines.map((line) => (
                <div key={line.code} className="receipt__row" data-tax-line={line.code}><span>{pick(lang, line.label, line.label_uk)}</span><span>{money(line.amount_cad, lang)}</span></div>
              ))
            : quote && quote.tax_rate ? <div className="receipt__row"><span>{d.bag.tax} ({Math.round(quote.tax_rate * 100)}%)</span><span>{money(quote.tax_cad, lang)}</span></div> : null}
          <div className="receipt__row receipt__row--total"><span>{d.bag.total}</span><span>{quote && !blockedReason ? money(quote.total_cad, lang) : "…"}</span></div>
          {quoteShort.length && !error ? (
            <p className="error" role="status" style={{ marginTop: "var(--st)" }}>{quoteShort.join(" ")}</p>
          ) : null}
          {error ? <p key={attempt} className="error" role="alert" style={{ marginTop: "var(--st)" }}>{error}</p> : null}
          {blockedReason ? <p className="error" style={{ marginTop: "var(--st)" }}>{blockedReason}</p> : null}
          {demo ? <p id="demo-line" className="demo-line" data-demo-line>{o.demoAtCheckout}</p> : null}
          <div className="accept" style={{ marginTop: "calc(var(--st) * 2)" }}>
            <label className="accept__row" htmlFor="terms">
              <input id="terms" type="checkbox" checked={accepted} onChange={(e) => { setAccepted(e.target.checked); clearField("terms"); }} aria-invalid={Boolean(fieldErrors.terms)} aria-describedby={fieldErrors.terms ? "terms-error" : undefined} data-accept-terms />
              <span className="ui" style={{ fontWeight: 400 }}>
                {b.checkout.accept}{" "}
                <a href={href(lang, "/terms")} target="_blank" rel="noopener" className="thread-link thread-link--on">{b.checkout.terms}</a>{" "}
                {b.checkout.and}{" "}
                <a href={href(lang, "/privacy")} target="_blank" rel="noopener" className="thread-link thread-link--on">{b.checkout.privacy}</a>
              </span>
            </label>
            <FieldError field="terms" />
          </div>
          <p style={{ marginTop: "calc(var(--st) * 2)" }}>
            <button type="submit" className="btn btn--red btn--lg btn--wide" disabled={placeDisabled} aria-describedby={demo ? "demo-line" : undefined} data-place-order>{busy ? d.checkout.placing : d.checkout.place}</button>
          </p>
          <p className="mono mono--sm muted" style={{ marginTop: "var(--st)" }}>{d.checkout.agree}</p>
        </div>
      </div>
    </form>
  );
}
