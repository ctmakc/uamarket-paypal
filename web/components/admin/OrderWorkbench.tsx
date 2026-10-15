"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { adminCall } from "@/lib/admin/client";
import { adminDict, adminMoney, adminTime, mailStateText, pickLang, timelineText, type AdminLang } from "@/lib/admin/i18n";
import type { OrderDetail } from "@/lib/admin/types";

type Flash = { tone: "ok" | "bad"; text: string } | null;

function statusTone(state: string): string {
  if (state === "HANDOFF_COMPLETE") return "ok";
  if (state === "CANCELLED") return "quiet";
  if (state === "OUT_OF_STOCK") return "bad";
  if (state === "AWAITING_PAYMENT") return "wait";
  return "ok";
}

const STATE_LABEL: Record<string, [string, string]> = {
  AWAITING_PAYMENT: ["Awaiting payment", "Чекає оплати"],
  PAID: ["Paid", "Оплачено"],
  PICK_PLANNED: ["Paid, reserved", "Оплачено, зарезервовано"],
  PICKING: ["Scanning", "Скануємо"],
  PICK_VERIFIED: ["Scanned, to pack", "Скановано, пакувати"],
  PACKING: ["Packed", "Запаковано"],
  LABEL_VERIFIED: ["Label checked", "Етикетку перевірено"],
  READY_FOR_PICKUP: ["In the locker", "У локері"],
  HANDOFF_COMPLETE: ["Shipped", "Відправлено"],
  OUT_OF_STOCK: ["Paid, out of stock", "Оплачено, немає товару"],
  CANCELLED: ["Cancelled", "Скасовано"],
};

export default function OrderWorkbench({ initial, lang }: { initial: OrderDetail; lang: AdminLang }) {
  const d = adminDict(lang);
  const o = d.order;
  const [order, setOrder] = useState<OrderDetail>(initial);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<Flash>(null);
  const [scanResult, setScanResult] = useState<Flash>(null);
  const scanRef = useRef<HTMLInputElement>(null);
  const kind = order.next.kind;

  useEffect(() => {
    if (kind === "scan") scanRef.current?.focus();
  }, [kind]);

  async function refresh() {
    const r = await adminCall<OrderDetail>(`v1/admin/orders/${order.id}`, { lang });
    if (r.ok) setOrder(r.data);
  }

  async function act(path: string, json: unknown, after?: (data: unknown) => void): Promise<boolean> {
    if (busy) return false;
    setBusy(true);
    setFlash(null);
    const r = await adminCall(path, { json, lang });
    setBusy(false);
    if (!r.ok) {
      setFlash({ tone: "bad", text: r.message || d.common.error });
      return false;
    }
    after?.(r.data);
    await refresh();
    return true;
  }

  async function scan(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const input = scanRef.current;
    const code = (input?.value || "").trim();
    if (!code || busy) return;
    setBusy(true);
    const r = await adminCall<{ sku?: string; detail?: OrderDetail }>(`v1/admin/orders/${order.id}/scan`, { json: { barcode: code }, lang });
    setBusy(false);
    if (input) {
      input.value = "";
      input.focus();
    }
    if (r.ok) {
      setScanResult({ tone: "ok", text: o.scan.ok(r.data.sku || code) });
      if (r.data.detail) setOrder(r.data.detail);
    } else {
      setScanResult({ tone: "bad", text: r.message || d.common.error });
      await refresh();
    }
  }

  const unpicked = order.lines.reduce((n, l) => n + (l.picked ? 0 : 1), 0);
  const reserved = order.lines.some((l) => l.missions.length > 0);
  const steps = [
    true,
    Boolean(order.paid_at),
    reserved,
    reserved && unpicked === 0,
    Boolean(order.package?.weight_g),
    order.state === "HANDOFF_COMPLETE",
  ];
  const nowIndex = order.state === "CANCELLED" ? -1 : steps.findIndex((s) => !s);
  const label = STATE_LABEL[order.state]?.[lang === "uk" ? 1 : 0] || order.state;

  return (
    <div className="adm-order" data-state={order.state} data-next={kind}>
      <Link href="/admin" className="adm-crumb">← {o.back}</Link>
      <div className="adm-head" style={{ marginBottom: "var(--st)" }}>
        <div>
          <h1 className="h1 mono" style={{ fontFamily: "var(--face-mono)", fontWeight: 500, letterSpacing: 0 }}>{order.order_number}</h1>
          <p className="mono mono--sm muted">{o.placed} {adminTime(order.created_at)} · {o.method[order.payment_method || ""] || order.payment_method || order.channel}</p>
        </div>
        <p className="adm-actions">
          <span className={`adm-status adm-status--${statusTone(order.state)}`} data-testid="order-status">{label}</span>
          {order.demo ? <span className="adm-tag">{d.common.demo}</span> : null}
        </p>
      </div>
      <ol className="adm-steps" aria-label={o.next} style={{ marginBottom: "calc(var(--st) * 2)" }}>
        {o.steps.map((s, i) => (
          <li key={s} data-done={steps[i] ? "true" : undefined} data-now={i === nowIndex ? "true" : undefined}>
            <span aria-hidden="true">{steps[i] ? "✕" : "○"}</span> {s}
          </li>
        ))}
      </ol>

      <div className="adm-bench">
        <div>
          <NextSlab
            order={order}
            lang={lang}
            busy={busy}
            act={act}
            scan={scan}
            scanRef={scanRef}
            scanResult={scanResult}
            unpicked={unpicked}
          />
          <p className={`adm-msg adm-msg--${flash?.tone || "ok"}`} role="status" aria-live="polite" data-testid="order-flash">{flash?.text}</p>

          <section className="adm-section">
            <h2 className="adm-section__title">{o.items}</h2>
            <div className="adm-sheet">
              {order.lines.map((l) => (
                <div key={l.id} className="adm-line" data-sku={l.sku || ""}>
                  {l.photo ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img className="adm-line__img" src={l.photo.src} alt={pickLang(lang, l.photo.alt, l.photo.alt_uk)} />
                  ) : <span className="adm-line__ph" aria-hidden="true" />}
                  <div>
                    <p className="ui">{pickLang(lang, l.title, l.title_uk)}</p>
                    <p className="muted" style={{ fontSize: "var(--fs-ui)" }}>{pickLang(lang, l.label, l.label_uk)} · ×{l.qty}</p>
                    <p className="mono mono--sm muted adm-line__code">{l.sku}</p>
                    {l.barcode ? <p className="mono mono--sm muted adm-line__code">{o.barcode} <span data-testid="line-barcode">{l.barcode}</span></p> : null}
                    {l.missions.length ? (
                      <p className="adm-picked" data-on={l.picked ? "true" : undefined}>
                        <span>{l.picked ? `✓ ${o.picked}` : o.notPicked}</span>
                        {!l.picked && order.next.kind === "scan" ? (
                          <button
                            type="button"
                            className="adm-link adm-byhand"
                            disabled={busy}
                            data-testid="confirm-by-hand"
                            onClick={() => { if (window.confirm(o.byHandAsk(l.sku || l.title))) act(`v1/admin/orders/${order.id}/lines/${l.id}/confirm`, {}); }}
                          >{o.byHand}</button>
                        ) : null}
                      </p>
                    ) : null}
                  </div>
                  <p className="adm-row__money">{adminMoney(l.line_total_cad)}</p>
                </div>
              ))}
            </div>
            <dl className="adm-kv adm-sheet" style={{ gridTemplateColumns: "1fr auto" }}>
              <dt>{o.totals.subtotal}</dt><dd className="adm-row__money">{adminMoney(order.totals.subtotal_cad)}</dd>
              <dt>{o.totals.shipping}</dt><dd className="adm-row__money">{adminMoney(order.totals.shipping_cad)}</dd>
              <dt>{o.totals.tax}</dt><dd className="adm-row__money">{adminMoney(order.totals.tax_cad)}</dd>
              <dt><strong>{o.totals.total}</strong></dt><dd className="adm-row__money"><strong>{adminMoney(order.totals.total_cad)}</strong></dd>
            </dl>
          </section>

          {order.exceptions.length ? (
            <section className="adm-section">
              <h2 className="adm-section__title">{o.problems}</h2>
              {[...order.exceptions].sort((a, b) => (a.state === "OPEN" ? -1 : 1) - (b.state === "OPEN" ? -1 : 1)).map((e) => (
                <ExceptionCard key={e.id} e={e} lang={lang} onResolved={refresh} />
              ))}
            </section>
          ) : null}

          <section className="adm-section">
            <h2 className="adm-section__title">{o.timeline}</h2>
            <ol className="adm-timeline adm-sheet" data-testid="timeline">
              {order.timeline.map((t, i) => (
                <li key={`${t.at}-${i}`} data-kind={t.kind}>
                  <time dateTime={t.at || undefined}>{adminTime(t.at)}</time>
                  <span>{timelineText(t, lang, order.mail_captured)}</span>
                </li>
              ))}
            </ol>
            <NoteForm lang={lang} onSubmit={(body) => act(`v1/admin/orders/${order.id}/notes`, { body })} busy={busy} />
          </section>
        </div>

        <aside>
          <section className="adm-section">
            <h2 className="adm-section__title">{order.fulfillment_method === "PICKUP" ? o.pickup : o.shipTo}</h2>
            <address className="adm-sheet" style={{ fontStyle: "normal", fontSize: "var(--fs-ui)" }}>
              {order.fulfillment_method === "PICKUP" ? (
                <p>{order.customer.name}</p>
              ) : (
                <>
                  <p>{order.ship_to.name || order.customer.name}</p>
                  <p>{order.ship_to.street1}</p>
                  {order.ship_to.street2 ? <p>{order.ship_to.street2}</p> : null}
                  <p>{order.ship_to.city} {order.ship_to.province} {order.ship_to.postal_code}</p>
                  <p className="mono mono--sm muted">{order.ship_to.country}</p>
                </>
              )}
            </address>
          </section>
          <section className="adm-section">
            <h2 className="adm-section__title">{o.customer}</h2>
            <dl className="adm-kv adm-sheet">
              <dt>{o.contact.email}</dt><dd>{order.customer.email ? <a className="adm-link" href={`mailto:${order.customer.email}`}>{order.customer.email}</a> : "—"}</dd>
              <dt>{o.contact.phone}</dt><dd>{order.customer.phone || "—"}</dd>
              <dt>{o.contact.language}</dt><dd>{(order.customer.locale || "en").toUpperCase()}</dd>
            </dl>
          </section>
          <section className="adm-section">
            <h2 className="adm-section__title">{o.payment}</h2>
            <dl className="adm-kv adm-sheet">
              <dt>{o.method[order.payment_method || ""] || order.payment_method}</dt>
              <dd>{order.payment.paid_at ? adminTime(order.payment.paid_at) : <span className="adm-status adm-status--wait">{STATE_LABEL.AWAITING_PAYMENT[lang === "uk" ? 1 : 0]}</span>}</dd>
              {order.payment.reference ? (<><dt>Ref</dt><dd className="mono mono--sm">{order.payment.reference}</dd></>) : null}
              {order.payment.paypal ? (<>
                <dt>PayPal</dt><dd className="mono mono--sm" data-paypal-order>{order.payment.paypal.order_id || "—"}{order.payment.paypal.sandbox ? " · sandbox" : ""}</dd>
                <dt>{lang === "uk" ? "Статус" : "Status"}</dt><dd className="mono mono--sm">{order.payment.paypal.status || "—"}</dd>
                {order.payment.paypal.capture_id ? (<><dt>{lang === "uk" ? "Платіж" : "Capture"}</dt><dd className="mono mono--sm">{order.payment.paypal.capture_id}</dd></>) : null}
                {order.state === "HANDOFF_COMPLETE" ? (<><dt>{lang === "uk" ? "Трекінг у PayPal" : "Tracking in PayPal"}</dt><dd className="mono mono--sm" data-paypal-tracking>{order.payment.paypal.tracking_id || (lang === "uk" ? "ще ні" : "not yet")}</dd></>) : null}
                {order.payment.paypal.refund_id ? (<><dt>{lang === "uk" ? "Повернення" : "Refund"}</dt><dd className="mono mono--sm">{order.payment.paypal.refund_id}</dd></>) : null}
              </>) : null}
            </dl>
            {order.payment.paypal?.refundable ? (
              <p><button type="button" className="btn btn--red" disabled={busy} data-paypal-refund
                onClick={() => act(`v1/admin/orders/${order.id}/paypal/refund`, {})}>{lang === "uk" ? `Повернути ${adminMoney(order.totals.total_cad)} через PayPal` : `Refund ${adminMoney(order.totals.total_cad)} through PayPal`}</button></p>
            ) : null}
            {order.payment.paypal?.capture_id && order.state === "HANDOFF_COMPLETE" && !order.payment.paypal.tracking_id ? (
              <p><button type="button" className="btn btn--ghost" disabled={busy} data-paypal-push-tracking
                onClick={() => act(`v1/admin/orders/${order.id}/paypal/tracking`, {})}>{lang === "uk" ? "Надіслати трекінг у PayPal" : "Send tracking to PayPal"}</button></p>
            ) : null}
            {order.demo ? <p className="mono mono--sm muted">{o.demo}</p> : null}
          </section>
          {order.note ? (
            <section className="adm-section">
              <h2 className="adm-section__title">{o.buyerNote}</h2>
              <p className="adm-sheet" style={{ fontSize: "var(--fs-ui)", whiteSpace: "pre-wrap" }}>{order.note}</p>
            </section>
          ) : null}
          {order.mail.length ? (
            <section className="adm-section">
              <h2 className="adm-section__title">{o.emails}</h2>
              <ul className="adm-sheet" data-testid="mail-list">
                {order.mail.map((m) => (
                  <li key={m.kind} style={{ display: "flex", justifyContent: "space-between", gap: "var(--st)", flexWrap: "wrap", fontSize: "var(--fs-ui)" }}>
                    <span>{o.mailKind[m.kind] || m.kind} <span className="mono mono--sm muted">· {mailStateText(m.state, lang, order.mail_captured)}</span></span>
                    <a className="adm-link" href={`/admin/api/v1/orders/${order.id}/mail/${m.kind}/preview`} target="_blank" rel="noopener">{d.common.preview} ↗</a>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          {order.next.secondary.includes("cancel") ? (
            <CancelForm lang={lang} busy={busy} onSubmit={(note) => act(`v1/admin/orders/${order.id}/cancel`, { note })} />
          ) : null}
        </aside>
      </div>
    </div>
  );
}

function NextSlab(props: {
  order: OrderDetail; lang: AdminLang; busy: boolean;
  act: (path: string, json: unknown) => Promise<boolean>;
  scan: (e: React.FormEvent<HTMLFormElement>) => void;
  scanRef: React.RefObject<HTMLInputElement | null>;
  scanResult: Flash; unpicked: number;
}) {
  const { order, lang, busy, act, scan, scanRef, scanResult, unpicked } = props;
  const d = adminDict(lang);
  const o = d.order;
  const [rates, setRates] = useState<{ package_id: string; rates: { id: string; carrier: string; service: string; rate: string; currency: string }[] } | null>(null);
  const [rateError, setRateError] = useState<string | null>(null);
  const kind = order.next.kind;

  if (order.state === "CANCELLED") {
    return (
      <section className="adm-next" aria-label={o.next}>
        <p className="adm-next__label">{o.next}</p>
        <h2 className="adm-next__title">{o.cancelled.title}</h2>
      </section>
    );
  }

  let body: React.ReactNode = null;
  if (kind === "mark_paid") {
    body = (
      <>
        <h2 className="adm-next__title">{o.markPaid.title}</h2>
        <p className="adm-next__lede">{o.markPaid.lede}</p>
        <form key="mark-paid" className="adm-next__form" onSubmit={(e) => { e.preventDefault(); const ref = (new FormData(e.currentTarget).get("reference") as string) || undefined; act(`v1/orders/${order.id}/mark-paid`, { reference: ref, method: "ETRANSFER" }); }}>
          <label className="field"><span className="field__label">{o.markPaid.ref}</span><input className="input" name="reference" maxLength={200} /></label>
          <button className="btn btn--red" disabled={busy} type="submit">{o.markPaid.button}</button>
        </form>
      </>
    );
  } else if (kind === "await_paypal") {
    body = (<><h2 className="adm-next__title">{o.awaitPayPal.title}</h2><p className="adm-next__lede">{o.awaitPayPal.lede}</p></>);
  } else if (kind === "await_card") {
    body = (<><h2 className="adm-next__title">{o.awaitCard.title}</h2><p className="adm-next__lede">{o.awaitCard.lede}</p></>);
  } else if (kind === "reserve") {
    body = (
      <>
        <h2 className="adm-next__title">{o.reserve.title}</h2>
        <p className="adm-next__lede">{o.reserve.lede}</p>
        <div><button className="btn btn--light" disabled={busy} type="button" onClick={() => act(`v1/orders/${order.id}/reserve`, {})}>{o.reserve.button}</button></div>
      </>
    );
  } else if (kind === "scan") {
    body = (
      <>
        <h2 className="adm-next__title">{o.scan.title}</h2>
        <p className="adm-next__lede">{o.scan.lede} {o.scan.left(unpicked)}</p>
        <form key="scan" className="adm-next__form" onSubmit={scan} style={{ gridTemplateColumns: "minmax(0, 1fr) auto" }}>
          <label className="field">
            <span className="sr-only">{o.scan.placeholder}</span>
            <input
              ref={scanRef}
              className="adm-scan"
              name="barcode"
              placeholder={o.scan.placeholder}
              autoComplete="off"
              autoCapitalize="off"
              spellCheck={false}
              inputMode="numeric"
              enterKeyHint="go"
              aria-invalid={scanResult?.tone === "bad" ? "true" : undefined}
              data-testid="scan-input"
            />
          </label>
          <button className="btn btn--light" disabled={busy} type="submit">{o.scan.button}</button>
        </form>
        <p className={`adm-next__result adm-next__result--${scanResult?.tone || "ok"}`} role="status" aria-live="assertive" data-testid="scan-result">{scanResult?.text}</p>
      </>
    );
  } else if (kind === "pack") {
    body = (
      <>
        <h2 className="adm-next__title">{o.pack.title}</h2>
        <p className="adm-next__lede">{o.pack.lede}{order.estimated_weight_g ? ` ${o.pack.estimate(order.estimated_weight_g)}` : ""}</p>
        <form key="pack" className="adm-next__form" onSubmit={(e) => { e.preventDefault(); const w = Number(new FormData(e.currentTarget).get("weight_g")); act(`v1/admin/orders/${order.id}/pack`, { weight_g: w }); }}>
          <label className="field"><span className="field__label">{o.pack.weight}</span>
            <input className="input" name="weight_g" type="number" min={1} max={70000} required inputMode="numeric" data-testid="weight-input" autoFocus /></label>
          <button className="btn btn--light" disabled={busy} type="submit">{o.pack.button}</button>
        </form>
      </>
    );
  } else if (kind === "ship") {
    const bound = order.shipment?.state === "PURCHASED" ? order.shipment.tracking_code : null;
    body = (
      <>
        <h2 className="adm-next__title">{o.ship.title}</h2>
        <p className="adm-next__lede">{o.ship.lede} {order.package?.weight_g ? `· ${order.package.weight_g} g` : ""}</p>
        <form key="ship" className="adm-next__form" onSubmit={(e) => { e.preventDefault(); const f = new FormData(e.currentTarget); act(`v1/orders/${order.id}/ship`, { carrier: f.get("carrier"), tracking_code: f.get("tracking_code") }); }}>
          <label className="field"><span className="field__label">{o.ship.carrier}</span>
            <input className="input" name="carrier" required maxLength={80} defaultValue={order.shipment?.carrier || ""} list="carriers" data-testid="carrier-input" /></label>
          <label className="field"><span className="field__label">{o.ship.tracking}</span>
            <input className="input mono" name="tracking_code" required minLength={3} maxLength={180} defaultValue={bound || ""} autoComplete="off" data-testid="tracking-input" /></label>
          <button className="btn btn--red" disabled={busy} type="submit">{o.ship.button}</button>
          <datalist id="carriers"><option value="Canada Post" /><option value="Purolator" /><option value="UPS" /><option value="FedEx" /></datalist>
        </form>
        {order.label.available ? (
          <div className="adm-actions">
            <button className="btn btn--light" type="button" disabled={busy} onClick={async () => {
              setRateError(null);
              const r = await adminCall<typeof rates>(`v1/admin/orders/${order.id}/label/rates`, { method: "POST", json: {}, lang });
              if (r.ok) setRates(r.data); else setRateError(r.message);
            }}>{o.ship.rates}</button>
            {rates?.rates.map((rate) => (
              <button key={rate.id} className="btn btn--light" type="button" disabled={busy}
                onClick={() => act(`v1/packages/${rates.package_id}/shipping/easypost/buy`, { rate_id: rate.id })}>
                {o.ship.buy}: {rate.carrier} {rate.service} {rate.currency} {rate.rate}
              </button>
            ))}
            {rateError ? <p className="adm-next__result adm-next__result--bad">{rateError}</p> : null}
          </div>
        ) : (
          <p className="adm-next__lede mono mono--sm">{o.ship.noLabel}</p>
        )}
      </>
    );
  } else if (kind === "locker") {
    body = (<><h2 className="adm-next__title">{o.locker.title}</h2><p className="adm-next__lede">{o.locker.lede}</p></>);
  } else {
    body = (
      <>
        <h2 className="adm-next__title">{o.done.title}</h2>
        {order.shipment?.tracking_code ? (
          <p className="mono" data-testid="shipped-tracking">{o.done.tracking}: {order.shipment.carrier} {order.shipment.tracking_code}</p>
        ) : null}
      </>
    );
  }
  return (
    <section className="adm-next" aria-label={o.next} data-testid="next-slab">
      <p className="adm-next__label">{o.next}</p>
      {body}
    </section>
  );
}

function ExceptionCard({ e, lang, onResolved }: { e: OrderDetail["exceptions"][number]; lang: AdminLang; onResolved: () => Promise<void> }) {
  const o = adminDict(lang).order;
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="adm-exc" data-state={e.state} data-kind={e.kind}>
      <p className="mono mono--sm">{e.kind} · {adminTime(e.created_at)}</p>
      <p className="ui">{e.summary}</p>
      {e.state === "OPEN" ? (
        <form className="adm-actions" onSubmit={async (ev) => {
          ev.preventDefault();
          const note = String(new FormData(ev.currentTarget).get("note") || "").trim();
          if (!note) return;
          setBusy(true);
          const r = await adminCall(`v1/exceptions/${e.id}/resolve`, { json: { note }, lang });
          setBusy(false);
          if (r.ok) await onResolved(); else setError(r.message);
        }}>
          <label className="field" style={{ flex: 1, minWidth: 200 }}><span className="sr-only">{o.resolveNote}</span>
            <input className="input" name="note" placeholder={o.resolveNote} required maxLength={2000} /></label>
          <button className="btn btn--ghost" type="submit" disabled={busy}>{o.resolve}</button>
          {error ? <p className="adm-msg adm-msg--bad">{error}</p> : null}
        </form>
      ) : (
        <p className="mono mono--sm">{o.resolved} {adminTime(e.resolved_at)}: {e.resolution_note}</p>
      )}
    </div>
  );
}

function NoteForm({ lang, busy, onSubmit }: { lang: AdminLang; busy: boolean; onSubmit: (body: string) => Promise<boolean> }) {
  const o = adminDict(lang).order;
  return (
    <form className="adm-actions" onSubmit={async (e) => {
      e.preventDefault();
      const form = e.currentTarget;
      const body = String(new FormData(form).get("body") || "").trim();
      if (body && (await onSubmit(body))) form.reset();
    }}>
      <label className="field" style={{ flex: 1, minWidth: 220 }}><span className="sr-only">{o.addNote}</span>
        <input className="input" name="body" placeholder={o.notePlaceholder} maxLength={4000} /></label>
      <button className="btn btn--ghost" type="submit" disabled={busy}>{o.addNote}</button>
    </form>
  );
}

function CancelForm({ lang, busy, onSubmit }: { lang: AdminLang; busy: boolean; onSubmit: (note: string) => Promise<boolean> }) {
  const o = adminDict(lang).order;
  const [open, setOpen] = useState(false);
  if (!open) {
    return <section className="adm-section"><button className="btn btn--ghost" type="button" onClick={() => setOpen(true)}>{o.cancel.title}</button></section>;
  }
  return (
    <section className="adm-section">
      <h2 className="adm-section__title">{o.cancel.title}</h2>
      <form className="adm-sheet" onSubmit={(e) => {
        e.preventDefault();
        const note = String(new FormData(e.currentTarget).get("note") || "").trim();
        if (note.length >= 3 && window.confirm(o.cancel.confirm)) onSubmit(note);
      }}>
        <label className="field"><span className="field__label">{o.cancel.note}</span>
          <textarea className="textarea" name="note" required minLength={3} maxLength={4000} /></label>
        <div className="adm-actions">
          <button className="btn btn--red" type="submit" disabled={busy}>{o.cancel.button}</button>
          <button className="btn btn--ghost" type="button" onClick={() => setOpen(false)}>{adminDict(lang).common.cancel}</button>
        </div>
      </form>
    </section>
  );
}
