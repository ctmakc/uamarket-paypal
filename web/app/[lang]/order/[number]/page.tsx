import type { Metadata } from "next";
import Link from "next/link";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import CancelOrder from "@/components/CancelOrder";
import RetryPayment from "@/components/RetryPayment";
import OrderPayPal from "@/components/OrderPayPal";
import { tp as tpp } from "@/lib/i18n.paypal";
import StitchMark from "@/components/StitchMark";
import type { OrderPickup } from "@/lib/api";
import { api, ApiError, money } from "@/lib/api";
import { tb, variantLabel } from "@/lib/i18n.buy";
import { orderCookieName, plausibleKey, visitorFrom } from "@/lib/visitor";
import type { Lang } from "@/lib/i18n";
import { href, pick, t } from "@/lib/i18n";
import { MAIL_OFF, mailNotice, tm } from "@/lib/i18n.mail";
import { to } from "@/lib/i18n.order";
import { tp } from "@/lib/i18n.pages";
import { tpk } from "@/lib/i18n.pickup";
import { buildMetadata } from "@/lib/seo";

/**
 * One customer's order: noindex, nofollow. The order number stays out of the
 * description and out of the social-card URL that buildMetadata generates from
 * the title, so nothing reaches a third party through a preview fetch; the
 * browser tab still shows it, which is where the customer needs it.
 */
export async function generateMetadata({ params }: { params: Promise<{ lang: string; number: string }> }): Promise<Metadata> {
  const { lang: raw, number } = await params;
  const lang = raw as Lang;
  const d = t(lang);
  const meta = buildMetadata({
    lang,
    path: `/order/${number.toUpperCase()}`,
    title: d.order.title,
    description: tp(lang).orderStatusDescription,
    ogSeed: "order",
    robots: { index: false, follow: false },
  });
  // no-referrer: an order key that arrived in the address (?key= from the email) never
  // travels on to another site in a Referer header.
  return { ...meta, title: `${d.order.title} ${number.toUpperCase()}`, referrer: "no-referrer" };
}

/**
 * Where an order stands, as a step index. A shipped order has four steps (Placed · Paid ·
 * Packed · Shipped); a pickup order has five (… · In the locker · Collected). A finished
 * step is filled, the current one is red, and the last step of a finished order is filled
 * rather than current. `paid` means paid and waiting to be packed, so the Paid step is done
 * and Packed is current.
 */
function stepState(key: string, pickup: boolean): { now: number; done: number } {
  const last = pickup ? 4 : 3;
  switch (key) {
    case "awaiting_payment": return { now: 1, done: 1 };
    case "paid": return { now: 2, done: 2 };
    case "packing": return { now: 2, done: 2 };
    case "delayed": return { now: 2, done: 2 };
    case "ready": return pickup ? { now: 4, done: 4 } : { now: 3, done: 3 };
    case "shipped": case "collected": return { now: -1, done: last + 1 };
    default: return { now: 2, done: 2 };
  }
}

/**
 * The locker, in the hands of the person who bought the parcel.
 *
 * The API decides what may be said: `state` is one of six, `message` is the sentence for
 * that state in the buyer's language, and `code` is six digits in the one state where a
 * live credential exists. This block renders off `state` and never off the presence of a
 * code, because the code is absent in five states for five different reasons.
 *
 * The address, the hours and the door note appear beside a live code and nowhere else.
 * Before the parcel is in a bay the API's own sentence promises them "when your parcel is
 * in the locker", and printing them early would contradict it; after the bay is opened
 * they are a detail about a journey already finished.
 *
 * The digits are set in the shop's mono face at `.mono--price`, the largest mono size the
 * design has (40px, 32px on a phone), so the code can be read off a screen held at arm's
 * length at a garage door. `aria-label` spells them out one by one, since a screen reader
 * otherwise reads 142803 as "one hundred forty-two thousand eight hundred three".
 */
function PickupPlate({ lang, pickup }: { lang: Lang; pickup: OrderPickup }) {
  const pk = tpk(lang);
  const code = pickup.state === "ready" ? pickup.code : null;
  const name = pick(lang, pickup.label, pickup.label_uk);
  // The API knows one hours string and cannot translate it. SHOP_PICKUP_HOURS_UK is the
  // Ukrainian rendering the FAQ and the shipping page already read, and this page reads it
  // from the same place, so the three do not describe one locker in two ways.
  const openHours = (lang === "uk" && (process.env.SHOP_PICKUP_HOURS_UK || "").trim()) || pickup.hours;
  // A label and the thing it names go in one wrapper: paragraphs carry no margin here, so
  // the pair sits on two consecutive lines while `stack--tight` keeps a stitch between
  // pairs. Without it the label of one fact and the value of the one above it are spaced
  // identically and the block reads as a column of unrelated lines.
  const fact = (label: string, value: string) => (
    <div>
      <p className="mono mono--sm muted">{label}</p>
      <p>{value}</p>
    </div>
  );
  return (
    <div className="plate stack--tight" style={code ? { borderLeft: "3px solid var(--thread-red)" } : undefined}>
      <div>
        <p className="ui">{name}</p>
        {/* The bay stands on its own line: a bay id is a code, and appending it to the
            method name breaks it across two lines on a narrow screen. */}
        {pickup.bay ? <p className="mono mono--sm muted">{pk.bay(pickup.bay)}</p> : null}
      </div>
      {/* The API's sentence for this state, and it says "the code below" — so it is read
          before the digits, whatever the state. */}
      <p>{pick(lang, pickup.message, pickup.message_uk)}</p>
      {code ? (
        <div>
          <p className="mono mono--sm muted">{pk.code}</p>
          <p className="mono mono--price" aria-label={pk.codeSpoken(code)}>{code}</p>
        </div>
      ) : null}
      {code && pickup.valid_until_text ? <p className="status status--warn">{pk.until(pickup.valid_until_text)}</p> : null}
      {code && pickup.address ? fact(pk.address, pickup.address) : null}
      {code && openHours ? fact(pk.hours, openHours) : null}
      {code && pickup.note ? fact(pk.door, pickup.note) : null}
    </div>
  );
}

export default async function OrderPage({ params, searchParams }: { params: Promise<{ lang: string; number: string }>; searchParams: Promise<{ key?: string; placed?: string; paid?: string }> }) {
  const { lang: raw, number } = await params;
  const lang = raw as Lang;
  const d = t(lang);
  const b = tb(lang);
  const sp = await searchParams;
  // The order's key: from the link in the order email (?key=), or the HttpOnly cookie the
  // server set when this browser placed or looked up the order. Never an email address.
  const jar = await cookies();
  const key = plausibleKey(sp.key) || plausibleKey(jar.get(orderCookieName(number))?.value);
  if (!key) redirect(`${href(lang, "/order")}?number=${encodeURIComponent(number)}`);
  let o;
  try {
    o = await api.order(number, key, visitorFrom(await headers()));
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) redirect(`${href(lang, "/order")}?number=${encodeURIComponent(number)}&missing=1`);
    if (e instanceof ApiError && e.status === 429) redirect(`${href(lang, "/order")}?number=${encodeURIComponent(number)}&busy=1`);
    throw e;
  }
  // What this page may say about email. A config the page cannot read promises nothing.
  let mail = MAIL_OFF;
  let paypalConfig = null;
  try {
    const cfg = await api.config();
    mail = mailNotice(cfg);
    paypalConfig = cfg.paypal ?? null;
  } catch {
    mail = MAIL_OFF;
  }
  const mt = tm(lang);
  const isPickup = o.fulfillment_method === "PICKUP";
  const stepLabels = isPickup ? b.steps.pickup : b.steps.ship;
  const steps = stepState(o.status.key, isPickup);
  const cancelled = o.status.key === "cancelled";
  const statusLabel = pick(lang, o.status.label, o.status.label_uk);
  const placedAt = o.created_at ? new Date(o.created_at).toLocaleDateString(lang === "uk" ? "uk-UA" : "en-CA", { year: "numeric", month: "long", day: "numeric" }) : "";

  return (
    <section className="canvas band">
      <div className="split">
        <div className="split__a stack--loose">
          {/* The title was <h1 className="h2 mono">, and .mono is declared after
              .h2 at equal specificity, so the page a customer lands on after
              sending money had its only heading rendered at 14px. The page now
              carries a real title with the number in mono beneath it. */}
          <div className="stack--tight">
            <h1 className="h1">{d.order.title}</h1>
            <p className="mono" style={{ fontSize: "20px", lineHeight: "24px", fontWeight: 500 }}>{o.order_number}</p>
            <p className="key"><span>{d.order.placed}: {placedAt}</span><span>{o.customer.email}</span></p>
          </div>

          {sp.placed ? (
            <p className="notice notice--ok" role="status">
              {`${d.order.thanks} ${mail.email ? mt.placedWithEmail(o.customer.email || "") : mt.placedNoEmail}`}
            </p>
          ) : null}
          {sp.paid && o.paid_at ? (
            <p className="notice notice--ok" role="status">
              {mail.email ? d.order.paidThanks : `${d.order.paidThanks} ${mt.paidNoEmail}`}
            </p>
          ) : null}

          {/* progress as a row counter: finished rows filled */}
          {!cancelled ? (
            <div className="stack--tight">
              <p className="mono mono--sm muted" id="order-steps">{b.steps.label}</p>
              <ol className="counter" style={{ gridTemplateColumns: `repeat(${stepLabels.length}, minmax(0, 1fr))` }} aria-labelledby="order-steps" data-steps={isPickup ? "pickup" : "ship"}>
                {stepLabels.map((label, i) => (
                  <li key={label} className="counter__row" data-done={i < steps.done && i !== steps.now} data-now={i === steps.now} aria-current={i === steps.now ? "step" : undefined}>
                    <span className="counter__n" aria-hidden="true">{i + 1}</span>
                    <span>{label}</span>
                  </li>
                ))}
              </ol>
            </div>
          ) : (
            <p className="notice notice--warn">{d.order.cancelled}</p>
          )}

          <div className="stack--tight">
            <p className="mono mono--sm muted">{d.order.status}</p>
            <p className={`status ${o.status.key === "delayed" ? "status--warn" : o.status.key === "cancelled" ? "status--bad" : o.paid_at ? "status--ok" : "status--warn"}`} style={{ fontSize: "var(--fs-body)" }}>{statusLabel}</p>
          </div>

          {o.payment.due && !cancelled && o.payment.method === "PAYPAL" ? (
            <div className="plate stack--tight" style={{ borderLeft: `3px solid var(${o.demo ? "--thread-mustard" : "--thread-red"})` }} data-order-paypal-due>
              {o.demo ? <p className="mono mono--sm">{paypalConfig?.env === "sandbox" ? tpp(lang).demoSandbox : to(lang).orderDemo}</p> : null}
              {paypalConfig
                ? <OrderPayPal lang={lang} number={o.order_number} orderKey={key} config={paypalConfig} amount={money(o.payment.amount_cad ?? o.totals.total_cad, lang)} />
                : <p>{tpp(lang).failed}</p>}
            </div>
          ) : o.payment.due && !cancelled && (o.demo || o.payment.demo) ? (
            <div className="plate stack--tight" style={{ borderLeft: "3px solid var(--thread-mustard)" }} data-order-demo>
              <p className="h3">{d.order.payDue} · {money(o.payment.amount_cad ?? o.totals.total_cad, lang)}</p>
              <p>{to(lang).orderDemo}</p>
              {o.payment.method === "STRIPE" && o.payment.test_mode ? (
                o.payment.checkout_url
                  ? <p><a href={o.payment.checkout_url} className="btn btn--red" data-pay-test>{to(lang).payTestButton}</a></p>
                  : <RetryPayment lang={lang} number={o.order_number} orderKey={key} />
              ) : null}
            </div>
          ) : o.payment.due && !cancelled ? (
            <div className="plate stack--tight" style={{ borderLeft: "3px solid var(--thread-red)" }}>
              <p className="h3">{d.order.payDue} · {money(o.payment.amount_cad ?? o.totals.total_cad, lang)}</p>
              {/* The e-Transfer and by-arrangement lines in lib/i18n.ts promise a follow-up
                  email. With email switched off this page is the channel, and says so. */}
              {o.payment.method === "ETRANSFER" ? (
                <p>{!o.payment.recipient_email
                  ? mt.orderPayEtransferNoRecipient(o.order_number, money(o.payment.amount_cad ?? o.totals.total_cad, lang))
                  : mail.email
                    ? d.order.payEtransfer(o.payment.recipient_email, o.order_number, money(o.payment.amount_cad ?? o.totals.total_cad, lang))
                    : mt.orderPayEtransferNoEmail(o.payment.recipient_email, o.order_number, money(o.payment.amount_cad ?? o.totals.total_cad, lang))}</p>
              ) : o.payment.method === "STRIPE" ? (
                o.payment.checkout_url
                  ? <p><a href={o.payment.checkout_url} className="btn btn--red">{o.payment.test_mode ? to(lang).payTestButton : d.order.payStripe}</a></p>
                  : <RetryPayment lang={lang} number={o.order_number} orderKey={key} />
              ) : (
                <p>{mail.email && o.payment.contact_email
                  ? d.order.payInvoice(o.payment.contact_email)
                  : mt.orderPayInvoiceNoEmail(o.payment.contact_email || null)}</p>
              )}
            </div>
          ) : null}

          {o.paid_at ? (
            <div className="stack--tight">
              <p className="status status--ok">{d.order.paid} · {new Date(o.paid_at).toLocaleDateString(lang === "uk" ? "uk-UA" : "en-CA")}</p>
              {o.payment.paypal?.capture_id ? <p className="mono mono--sm muted" data-paypal-capture>{tpp(lang).orderPaidVia(o.payment.paypal.capture_id)}{o.payment.paypal.sandbox ? " · sandbox" : ""}</p> : null}
            </div>
          ) : null}

          {o.tracking ? (
            <div className="stack--tight" data-tracking>
              <p className="mono mono--sm muted">{d.order.tracking}</p>
              <p className="mono" style={{ fontSize: "20px", lineHeight: "24px" }}>{o.tracking.code}</p>
              {o.tracking.carrier ? <p className="mono mono--sm muted">{o.tracking.carrier}</p> : null}
            </div>
          ) : null}

          <div className="stack--tight">
            <p className="mono mono--sm muted">{o.fulfillment_method === "PICKUP" ? d.order.pickupAt : d.order.deliverTo}</p>
            {o.fulfillment_method === "PICKUP" ? (
              o.pickup ? <PickupPlate lang={lang} pickup={o.pickup} /> : <p>{d.checkout.pickup}</p>
            ) : (
              <p>{[o.ship_to.name, o.ship_to.street1, o.ship_to.street2, `${o.ship_to.city || ""}, ${o.ship_to.province || ""} ${o.ship_to.postal_code || ""}`].filter(Boolean).join(", ")}</p>
            )}
          </div>

          {o.status.key === "awaiting_payment" ? <CancelOrder lang={lang} number={o.order_number} orderKey={key} /> : null}
        </div>

        <div className="split__b">
          <div className="receipt">
            <div className="mono mono--sm muted" style={{ marginBottom: "var(--st)" }}>{d.order.lines}</div>
            {o.lines.map((l, i) => (
              <div key={i} className="receipt__row" style={{ gridTemplateColumns: "20px 1fr auto" }}>
                <span aria-hidden="true">{l.origin ? <StitchMark origin={l.origin} lang={lang} /> : null}</span>
                <span>{l.qty} × {l.product_slug ? <Link href={href(lang, `/product/${l.product_slug}`)} className="thread-link">{pick(lang, l.title, l.title_uk)}</Link> : pick(lang, l.title, l.title_uk)} <span className="muted" data-order-label>{variantLabel(lang, l.label, l.label_uk)}</span></span>
                <span>{money(l.line_total_cad, lang)}</span>
              </div>
            ))}
            <div className="receipt__row" style={{ marginTop: "var(--st)" }}><span>{d.bag.subtotal}</span><span>{money(o.totals.subtotal_cad, lang)}</span></div>
            <div className="receipt__row"><span>{d.bag.shipping}</span><span>{money(o.totals.shipping_cad, lang)}</span></div>
            {o.totals.tax_lines?.length
              ? o.totals.tax_lines.map((line) => (
                  <div key={line.code} className="receipt__row" data-tax-line={line.code}><span>{pick(lang, line.label, line.label_uk)}</span><span>{money(line.amount_cad, lang)}</span></div>
                ))
              : o.totals.tax_rate ? <div className="receipt__row"><span>{d.bag.tax} ({Math.round(o.totals.tax_rate * 100)}%)</span><span>{money(o.totals.tax_cad, lang)}</span></div> : null}
            <div className="receipt__row receipt__row--total"><span>{d.bag.total}</span><span>{money(o.totals.total_cad, lang)}</span></div>
            {o.gst_number ? <p className="mono mono--sm muted" style={{ marginTop: "var(--st)" }} data-gst-number>{b.gst(o.gst_number)}</p> : null}
          </div>
          <div className="receipt__tear" />
        </div>
      </div>
    </section>
  );
}
