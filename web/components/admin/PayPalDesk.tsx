"use client";

/**
 * The PayPal desk: the owner asks, the agent reads the shop and PayPal (PayPal Agent Toolkit),
 * and anything that would change money or PayPal's records comes back as a card here. The
 * card's Confirm button calls the same endpoint the order page uses; the agent never does.
 */
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { adminCall } from "@/lib/admin/client";
import { Rich } from "@/components/Concierge";
import type { AdminLang } from "@/lib/admin/i18n";

type Action = { kind: "push_tracking" | "refund"; order_id: string; order_number: string; text: string; amount_cad?: number; carrier?: string; tracking_number?: string };
type Reply = { reply: string; actions: Action[]; trace: { tool: string; ok: boolean }[]; model: string; sandbox: boolean };
type Turn = { role: "user" | "assistant"; content: string; actions?: Action[]; trace?: Reply["trace"]; done?: Record<string, string> };

const T = {
  en: {
    title: "PayPal desk",
    lede: "Ask about payments, captures, tracking, refunds and disputes. The desk reads this shop and PayPal itself through the PayPal Agent Toolkit. Anything that changes money or PayPal's records waits for your Confirm.",
    quick: ["What needs my attention in PayPal?", "Which shipped orders does PayPal have no tracking for?", "Any open disputes?", "Show PayPal transactions from the last 7 days"],
    ask: "Ask the desk", send: "Ask", thinking: "Reading the shop and PayPal…", confirm: "Confirm", confirmed: "Done", you: "you", desk: "desk",
    tools: { shop_orders: "read the order queue", shop_order: "read an order", paypal_reconcile: "compared shop and PayPal", paypal_get_order: "PayPal get_order_details", paypal_list_disputes: "PayPal list_disputes", paypal_get_dispute: "PayPal get_dispute", paypal_get_tracking: "PayPal get_shipment_tracking", paypal_list_transactions: "PayPal list_transactions", propose_action: "proposed an action" } as Record<string, string>,
    failed: "failed", off: "The desk is not answering right now.", open: "Open order",
  },
  uk: {
    title: "PayPal",
    lede: "Питайте про оплати, трекінг, повернення та спори. Помічник читає крамницю і сам PayPal через PayPal Agent Toolkit. Усе, що змінює гроші чи записи PayPal, чекає на ваше «Підтвердити».",
    quick: ["Що в PayPal потребує моєї уваги?", "Для яких відправлених замовлень PayPal не має трекінгу?", "Є відкриті спори?", "Покажи транзакції PayPal за 7 днів"],
    ask: "Запитати", send: "Запитати", thinking: "Читаю крамницю і PayPal…", confirm: "Підтвердити", confirmed: "Готово", you: "ви", desk: "помічник",
    tools: { shop_orders: "черга замовлень", shop_order: "замовлення", paypal_reconcile: "звірка з PayPal", paypal_get_order: "PayPal get_order_details", paypal_list_disputes: "PayPal list_disputes", paypal_get_dispute: "PayPal get_dispute", paypal_get_tracking: "PayPal get_shipment_tracking", paypal_list_transactions: "PayPal list_transactions", propose_action: "запропонував дію" } as Record<string, string>,
    failed: "помилка", off: "Помічник зараз не відповідає.", open: "Відкрити замовлення",
  },
};

export default function PayPalDesk({ lang }: { lang: AdminLang }) {
  const t = T[lang === "uk" ? "uk" : "en"];
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const log = useRef<HTMLDivElement>(null);
  useEffect(() => { log.current?.lastElementChild?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [turns, busy]);

  async function ask(text: string) {
    const content = text.trim();
    if (!content || busy) return;
    const next: Turn[] = [...turns, { role: "user", content }];
    setTurns(next); setDraft(""); setBusy(true); setError(null);
    const r = await adminCall<Reply>("v1/admin/agent/desk", { json: { messages: next.map((x) => ({ role: x.role, content: x.content })).slice(-14) }, lang });
    setBusy(false);
    if (!r.ok) { setError(r.message || t.off); return; }
    setTurns((prev) => [...prev, { role: "assistant", content: r.data.reply, actions: r.data.actions, trace: r.data.trace }]);
  }

  async function confirm(turnIndex: number, a: Action) {
    setBusy(true); setError(null);
    const path = a.kind === "refund" ? `v1/admin/orders/${a.order_id}/paypal/refund` : `v1/admin/orders/${a.order_id}/paypal/tracking`;
    const r = await adminCall(path, { json: {}, lang });
    setBusy(false);
    if (!r.ok) { setError(r.message || t.failed); return; }
    setTurns((prev) => prev.map((x, i) => (i === turnIndex ? { ...x, done: { ...(x.done || {}), [a.kind + a.order_id]: t.confirmed } } : x)));
  }

  return (
    <div className="adm-desk" data-paypal-desk>
      <div className="adm-head"><h1 className="h1">{t.title}</h1></div>
      <p className="lede" style={{ maxWidth: "70ch" }}>{t.lede}</p>
      <div className="adm-actions adm-desk__quick">
        {t.quick.map((q) => <button key={q} type="button" className="btn btn--ghost" disabled={busy} onClick={() => ask(q)}>{q}</button>)}
      </div>
      <div className="adm-desk__log" ref={log}>
        {turns.map((x, i) => (
          <div key={i} className={`cg-row cg-row--${x.role}`} data-turn={x.role}>
            <p className="cg-row__who mono mono--sm">{x.role === "user" ? t.you : t.desk}</p>
            <div className="cg-row__body">
              <Rich text={x.content} />
              {x.actions?.map((a) => {
                const done = x.done?.[a.kind + a.order_id];
                return (
                  <section key={a.kind + a.order_id} className="adm-next adm-desk__action" data-action={a.kind}>
                    <p className="adm-next__label">{a.kind === "refund" ? "PayPal · refund" : "PayPal · tracking"}</p>
                    <p className="adm-next__title" style={{ fontSize: 20, lineHeight: "24px" }}>{a.text}</p>
                    <div className="adm-actions">
                      {done ? <p className="adm-next__result adm-next__result--ok">✓ {done}</p> : (
                        <button type="button" className={`btn ${a.kind === "refund" ? "btn--red" : "btn--light"}`} disabled={busy} onClick={() => confirm(i, a)} data-confirm>{t.confirm}</button>
                      )}
                      <Link className="adm-link" href={`/admin/orders/${a.order_id}`} style={{ color: "var(--thread-white)" }}>{t.open} →</Link>
                    </div>
                  </section>
                );
              })}
              {x.trace?.length ? <p className="cg-trace mono mono--sm">{x.trace.map((s, si) => <span key={si} data-ok={s.ok}>{t.tools[s.tool] || s.tool}{s.ok ? "" : ` (${t.failed})`}</span>)}</p> : null}
            </div>
          </div>
        ))}
        {busy ? <div className="cg-row"><p className="cg-row__who mono mono--sm">{t.desk}</p><div className="cg-row__body"><p className="cg-thinking mono mono--sm">{t.thinking}</p></div></div> : null}
      </div>
      {error ? <p className="error" role="alert">{error}</p> : null}
      <form className="adm-desk__ask" onSubmit={(e) => { e.preventDefault(); ask(draft); }}>
        <label htmlFor="desk-input" className="sr-only">{t.ask}</label>
        <input id="desk-input" className="input" value={draft} maxLength={1500} onChange={(e) => setDraft(e.target.value)} placeholder={t.quick[0]} data-desk-input />
        <button type="submit" className="btn btn--red" disabled={busy || !draft.trim()}>{t.send}</button>
      </form>
    </div>
  );
}
