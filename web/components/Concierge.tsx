"use client";

/**
 * The shopping concierge: a drawer on every storefront page.
 *
 * The agent (app/services/concierge.py) answers in words plus cards. The cards are the only
 * places money can be committed, and every one of them needs the buyer's own hand: "Add these
 * to my bag" writes the bag; the checkout card needs the terms box ticked and the PayPal
 * button pressed, and PayPal then asks for approval in its own window. The trace line under
 * each answer says which shop tools the agent called, so nothing it did is hidden.
 */
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import PayPalButton from "@/components/PayPalButton";
import type { AgentCard, AgentLine, AgentReply, PayPalConfig } from "@/lib/api";
import { money } from "@/lib/api";
import { bag, idempotencyKey } from "@/lib/bag";
import type { Lang } from "@/lib/i18n";
import { href, pick } from "@/lib/i18n";
import { paidAfterAll, tp } from "@/lib/i18n.paypal";

type Turn = {
  role: "user" | "assistant";
  content: string;
  cards?: AgentCard[];
  trace?: AgentReply["trace"];
  /** Set on a checkout card once PayPal confirmed: the order it became. */
  paid?: { order_number: string } | null;
  key?: string;
};

const STORE = "uamarket:concierge:v1";

function load(): { turns: Turn[]; budget: string; orders: string[] } {
  try {
    const raw = window.sessionStorage.getItem(STORE);
    if (raw) {
      const v = JSON.parse(raw);
      return { turns: Array.isArray(v.turns) ? v.turns.slice(-30) : [], budget: String(v.budget || ""), orders: Array.isArray(v.orders) ? v.orders : [] };
    }
  } catch { /* private window or blocked storage: start empty */ }
  return { turns: [], budget: "", orders: [] };
}

/** **bold** and "- " / "1. " list lines; everything else is plain text. */
export function Rich({ text }: { text: string }) {
  const blocks: React.ReactNode[] = [];
  let list: string[] = [];
  const inline = (s: string, k: string) => s.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={`${k}-${i}`}>{part.slice(2, -2)}</strong> : <span key={`${k}-${i}`}>{part.replace(/\*\*/g, "")}</span>);
  const flush = (k: string) => {
    if (list.length) blocks.push(<ul key={`l-${k}`} className="cg-list">{list.map((li, i) => <li key={i}>{inline(li, `${k}-${i}`)}</li>)}</ul>);
    list = [];
  };
  text.split("\n").forEach((line, i) => {
    const m = line.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/);
    if (m) { list.push(m[1]); return; }
    flush(String(i));
    if (line.trim()) blocks.push(<p key={`p-${i}`}>{inline(line, String(i))}</p>);
  });
  flush("end");
  return <>{blocks}</>;
}

function lineTitle(lang: Lang, l: AgentLine): string {
  const title = pick(lang, l.title || l.sku, l.title_uk);
  const label = pick(lang, l.label || "", l.label_uk);
  return label ? `${title} (${label})` : title;
}

export default function Concierge({ lang, paypal, enabled }: { lang: Lang; paypal: PayPalConfig | null; enabled: boolean }) {
  const pp = tp(lang);
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [budget, setBudget] = useState("");
  const [orders, setOrders] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const v = load();
    setTurns(v.turns); setBudget(v.budget); setOrders(v.orders); setReady(true);
    if (new URLSearchParams(window.location.search).get("concierge") === "1") setOpen(true);
  }, []);
  useEffect(() => {
    if (!ready) return;
    try { window.sessionStorage.setItem(STORE, JSON.stringify({ turns, budget, orders })); } catch { /* ignore */ }
  }, [turns, budget, orders, ready]);
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, busy, open]);
  useEffect(() => {
    if (open) inputRef.current?.focus();
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [open]);

  const currentBag = useCallback(() => {
    for (let i = turns.length - 1; i >= 0; i -= 1) {
      const card = turns[i].cards?.find((c) => c.type === "checkout" || c.type === "bag");
      if (card && (card.type === "checkout" || card.type === "bag")) return card.lines.map((l) => ({ sku: l.sku, qty: l.qty }));
    }
    return [];
  }, [turns]);

  async function send(text: string) {
    const content = text.trim();
    if (!content || busy) return;
    const next: Turn[] = [...turns, { role: "user", content }];
    setTurns(next); setDraft(""); setBusy(true); setError(null);
    try {
      const limit = Number(budget.replace(",", "."));
      const res = await fetch("/api/agent", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({
          messages: next.map((t) => ({ role: t.role, content: t.content })).slice(-16),
          locale: lang, budget_cad: limit >= 5 ? limit : null, orders, bag: currentBag(),
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) { setError(res.status === 429 ? String(body?.message || pp.offline) : pp.offline); return; }
      const reply = body as AgentReply;
      setTurns((prev) => [...prev, { role: "assistant", content: reply.reply, cards: reply.cards, trace: reply.trace, key: idempotencyKey() }]);
    } catch {
      setError(pp.offline);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  function markPaid(turnIndex: number, orderNumber: string) {
    setTurns((prev) => prev.map((t, i) => (i === turnIndex ? { ...t, paid: { order_number: orderNumber } } : t)));
    setOrders((prev) => (prev.includes(orderNumber) ? prev : [...prev, orderNumber]));
  }

  if (!enabled) return null;
  return (
    <>
      <button type="button" className="cg-tab" onClick={() => setOpen(true)} aria-expanded={open} aria-controls="concierge" data-concierge-open hidden={open}>
        <svg viewBox="0 0 14 14" width="14" height="14" aria-hidden="true" className="cg-tab__mark"><path d="M2 2 L12 12 M12 2 L2 12" stroke="currentColor" strokeWidth="2.2" /></svg>
        <span>{pp.open}</span>
      </button>
      <aside id="concierge" className="cg" data-open={open} aria-label={pp.title} aria-hidden={!open} inert={!open}>
        <header className="cg__head on-plate">
          <div className="cg__titlerow">
            <p className="cg__title">{pp.title}</p>
            <div className="cg__headtools">
              {turns.length ? <button type="button" className="cg__link" onClick={() => { setTurns([]); setError(null); }} data-concierge-restart>{pp.restart}</button> : null}
              <button type="button" className="cg__close" onClick={() => setOpen(false)} aria-label={pp.close} data-concierge-close>
                <svg viewBox="0 0 14 14" width="14" height="14" aria-hidden="true"><path d="M2 2 L12 12 M12 2 L2 12" stroke="currentColor" strokeWidth="2" /></svg>
              </button>
            </div>
          </div>
          <label className="cg__limit">
            <span className="mono mono--sm">{pp.limit}</span>
            <input className="cg__limitinput mono" inputMode="decimal" value={budget} placeholder={pp.noLimit}
              onChange={(e) => setBudget(e.target.value.replace(/[^\d.,]/g, "").slice(0, 7))} aria-describedby="cg-limit-hint" data-concierge-limit />
            <span id="cg-limit-hint" className="mono mono--sm muted">{pp.limitHint}</span>
          </label>
        </header>

        <div className="cg__log" ref={listRef} aria-live="polite">
          {!turns.length ? (
            <div className="cg__intro">
              <p>{pp.intro}</p>
              {paypal?.env === "sandbox" ? <p className="mono mono--sm muted">{pp.demoNote}</p> : null}
            </div>
          ) : null}
          {turns.map((turn, i) => (
            <div key={i} className={`cg-row cg-row--${turn.role}`} data-turn={turn.role}>
              <p className="cg-row__who mono mono--sm">{turn.role === "user" ? (lang === "uk" ? "ви" : "you") : (lang === "uk" ? "консультантка" : "concierge")}</p>
              <div className="cg-row__body">
                <Rich text={turn.content} />
                {turn.cards?.map((card, ci) => (
                  <CardView key={ci} card={card} lang={lang} paypal={paypal} turn={turn}
                    onPaid={(n) => markPaid(i, n)} />
                ))}
                {turn.trace && turn.trace.length ? (
                  <p className="cg-trace mono mono--sm" aria-label={pp.trace}>
                    {turn.trace.map((step, si) => (
                      <span key={si} data-ok={step.ok}>{pp.tools[step.tool] || step.tool}{step.ok ? "" : ` (${pp.refused})`}</span>
                    ))}
                  </p>
                ) : null}
              </div>
            </div>
          ))}
          {busy ? (
            <div className="cg-row cg-row--assistant" role="status">
              <p className="cg-row__who mono mono--sm">{lang === "uk" ? "консультантка" : "concierge"}</p>
              <div className="cg-row__body"><p className="cg-thinking mono mono--sm">{pp.thinking}</p></div>
            </div>
          ) : null}
          {error ? <p className="error cg__error" role="alert">{error}</p> : null}
        </div>

        <form className="cg__ask" onSubmit={(e) => { e.preventDefault(); send(draft); }}>
          <label htmlFor="cg-input" className="sr-only">{pp.placeholder}</label>
          <textarea id="cg-input" ref={inputRef} className="cg__input" rows={2} maxLength={1200} value={draft} placeholder={pp.placeholder}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(draft); } }} data-concierge-input />
          <button type="submit" className="btn cg__send" disabled={busy || !draft.trim()} data-concierge-send>{pp.send}</button>
        </form>
      </aside>
    </>
  );
}

function CardView({ card, lang, paypal, turn, onPaid }: { card: AgentCard; lang: Lang; paypal: PayPalConfig | null; turn: Turn; onPaid: (orderNumber: string) => void }) {
  const pp = tp(lang);
  if (card.type === "products") {
    return (
      <ul className="cg-products" data-card="products">
        {card.items.map((p) => (
          <li key={p.slug}>
            <Link href={href(lang, `/product/${p.slug}`)} className="cg-product">
              {p.image_url ? <img src={p.image_url} alt="" width={56} height={56} loading="lazy" /> : <span className="cg-product__blank" aria-hidden="true" />}
              <span className="cg-product__text">
                <span className="cg-product__name">{pick(lang, p.title, p.title_uk)}</span>
                <span className="mono mono--sm muted">{pick(lang, p.maker || "", p.maker_uk)}</span>
              </span>
              <span className="mono cg-product__price">{p.price_from_cad === p.price_to_cad ? money(p.price_from_cad, lang) : `${pp.from} ${money(p.price_from_cad, lang)}`}</span>
            </Link>
          </li>
        ))}
      </ul>
    );
  }
  if (card.type === "bag") return <BagCard card={card} lang={lang} />;
  if (card.type === "checkout") return <CheckoutCard card={card} lang={lang} paypal={paypal} turn={turn} onPaid={onPaid} />;
  if (card.type === "order") {
    return (
      <div className={`cg-card cg-card--order ${card.paid_at ? "is-paid" : ""}`} data-card="order">
        <p className="mono">{card.order_number} · {pick(lang, card.status.label, card.status.label_uk)} · {money(card.total_cad, lang)}</p>
        <p><Link href={href(lang, `/order/${card.order_number}`)} className="thread-link thread-link--on ui">{pp.openOrder} →</Link></p>
      </div>
    );
  }
  return null;
}

function Receipt({ lines, lang }: { lines: AgentLine[]; lang: Lang }) {
  return (
    <>
      {lines.map((l) => (
        <div key={l.sku} className="receipt__row" data-line={l.sku}>
          <span>{l.qty} × {lineTitle(lang, l)}</span>
          <span>{money((l.unit_price_cad || 0) * l.qty, lang)}</span>
        </div>
      ))}
    </>
  );
}

function BagCard({ card, lang }: { card: Extract<AgentCard, { type: "bag" }>; lang: Lang }) {
  const pp = tp(lang);
  const [added, setAdded] = useState(false);
  return (
    <div className="cg-card receipt" data-card="bag">
      <Receipt lines={card.lines} lang={lang} />
      <div className="receipt__row cg-card__sum"><span>{lang === "uk" ? "Товари" : "Goods"}</span><span>{money(card.subtotal_cad, lang)}</span></div>
      <div className="receipt__row"><span>{lang === "uk" ? "Доставка" : "Shipping"}</span><span>{money(card.shipping_cad, lang)}</span></div>
      <p className="mono mono--sm muted">{pp.taxAtCheckout}{card.budget_cad ? ` · ${pp.limit}: ${money(card.budget_cad, lang)}` : ""}</p>
      {added ? (
        <p className="ui status status--ok">{pp.added} · <Link href={href(lang, "/bag")} className="thread-link thread-link--on">{pp.viewBag} →</Link></p>
      ) : (
        <p><button type="button" className="btn btn--ghost btn--wide" data-concierge-addbag
          onClick={() => { card.lines.forEach((l) => bag.add({ sku: l.sku, slug: l.slug || "" }, l.qty)); setAdded(true); }}>{pp.addToBag}</button></p>
      )}
    </div>
  );
}

function CheckoutCard({ card, lang, paypal, turn, onPaid }: { card: Extract<AgentCard, { type: "checkout" }>; lang: Lang; paypal: PayPalConfig | null; turn: Turn; onPaid: (n: string) => void }) {
  const pp = tp(lang);
  const [accepted, setAccepted] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const placed = useRef<string | null>(null);
  const ship = card.ship_to;

  async function createOrder(): Promise<string> {
    setError(null); setNote(null);
    if (!placed.current) {
      const res = await fetch("/api/order", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({
          idempotency_key: `agent-${turn.key || "x"}`, email: card.contact.email, name: card.contact.name, phone: null, locale: lang,
          fulfillment_method: "SHIP", ship_to: ship, payment_method: "PAYPAL", note: lang === "uk" ? "Через консультантку" : "Placed through the concierge",
          lines: card.lines.map((l) => ({ sku: l.sku, qty: l.qty })), terms_accepted: true,
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || !body?.order_number) { setError(String(body?.message || pp.failed)); throw new Error("order"); }
      placed.current = body.order_number;
    }
    const res = await fetch(`/api/order/${encodeURIComponent(placed.current!)}/paypal`, { method: "POST" });
    const body = await res.json().catch(() => ({}));
    if (!res.ok || !body?.id) { setError(pp.failed); throw new Error("paypal"); }
    return String(body.id);
  }

  async function approved(id: string) {
    setNote(pp.capturing);
    const res = await fetch(`/api/order/${encodeURIComponent(placed.current!)}/paypal/capture`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ paypal_order_id: id }),
    });
    const body = await res.json().catch(() => ({}));
    setNote(null);
    if (!res.ok && !(body?.code !== "declined" && await paidAfterAll(placed.current!))) {
      setError(body?.code === "declined" ? pp.declined : pp.failed); return;
    }
    onPaid(placed.current!);
  }

  if (turn.paid) {
    return (
      <div className="cg-card cg-card--paid receipt" data-card="paid">
        <p className="h3 cg-card__paidtitle">{pp.paidTitle(turn.paid.order_number)}</p>
        <Receipt lines={card.lines} lang={lang} />
        <div className="receipt__row receipt__row--total"><span>{lang === "uk" ? "Сплачено" : "Paid"}</span><span>{money(card.totals.total_cad, lang)}</span></div>
        <p><Link href={href(lang, `/order/${turn.paid.order_number}`)} className="thread-link thread-link--on ui" data-concierge-order-link>{pp.openOrder} →</Link></p>
      </div>
    );
  }
  return (
    <div className="cg-card receipt" data-card="checkout">
      <p className="h3 cg-card__title">{pp.checkoutTitle}</p>
      <Receipt lines={card.lines} lang={lang} />
      <div className="receipt__row cg-card__sum"><span>{lang === "uk" ? "Товари" : "Goods"}</span><span>{money(card.totals.subtotal_cad, lang)}</span></div>
      <div className="receipt__row"><span>{lang === "uk" ? "Доставка" : "Shipping"}</span><span>{money(card.totals.shipping_cad, lang)}</span></div>
      {(card.totals.tax_lines || []).map((t) => (
        <div key={t.code} className="receipt__row"><span>{pick(lang, t.label, t.label_uk)}</span><span>{money(t.amount_cad, lang)}</span></div>
      ))}
      <div className="receipt__row receipt__row--total"><span>{lang === "uk" ? "Разом" : "Total"}</span><span>{money(card.totals.total_cad, lang)}</span></div>
      <p className="mono mono--sm cg-card__ship">{pp.shipTo}: {card.contact.name}, {ship.street1}{ship.street2 ? `, ${ship.street2}` : ""}, {ship.city} {ship.province} {ship.postal_code} · {card.contact.email}</p>
      {card.sandbox ? <p className="mono mono--sm muted">{pp.paySubSandbox}</p> : null}
      <label className="accept__row cg-card__terms">
        <input type="checkbox" checked={accepted} onChange={(e) => { setAccepted(e.target.checked); setError(null); }} data-concierge-terms />
        <span className="ui" style={{ fontWeight: 400 }}>
          <a href={href(lang, "/terms")} target="_blank" rel="noopener" className="thread-link thread-link--on">{pp.terms}</a>
        </span>
      </label>
      {paypal ? (
        <PayPalButton config={paypal} lang={lang} disabled={!accepted} onBlocked={() => setError(pp.termsNeeded)}
          createOrder={createOrder} onApproved={approved} onCancel={() => setNote(pp.cancelled)}
          onError={(m) => { if (m !== "order" && m !== "paypal") setError(pp.failed); }} />
      ) : <p className="error">{pp.failed}</p>}
      {note ? <p className="mono mono--sm" role="status">{note}</p> : null}
      {error ? <p className="error" role="alert">{error}</p> : null}
    </div>
  );
}
