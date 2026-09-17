"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { adminCall } from "@/lib/admin/client";
import { adminDict, adminTime, pickLang, type AdminLang } from "@/lib/admin/i18n";
import type { StockCell, Taxonomy } from "@/lib/admin/types";

type Item = StockCell & {
  variant_id: string; sku: string; barcode: string; label: string | null; label_uk: string | null; product_id: string | null;
  product_title: string; product_title_uk: string | null; product_active: boolean; variant_active: boolean;
};
type Event = { id: string; type: string; qty: number; location: string | null; reference: string; note: string | null; created_at: string | null };

export default function StockScreen({ lang, q, items, taxonomy }: { lang: AdminLang; q: string; items: Item[]; taxonomy: Taxonomy }) {
  const d = adminDict(lang);
  const s = d.stock;
  const router = useRouter();
  const [open, setOpen] = useState<{ sku: string; mode: "receive" | "adjust" | "history" } | null>(null);
  const [msg, setMsg] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [busy, setBusy] = useState(false);
  const sellable = taxonomy.locations.filter((l) => l.sellable);

  async function submit(ev: React.FormEvent<HTMLFormElement>, mode: "receive" | "adjust", sku: string) {
    ev.preventDefault();
    const f = new FormData(ev.currentTarget);
    const body = mode === "receive"
      ? { sku, qty: Number(f.get("qty")), location_id: f.get("location_id") || null, note: f.get("note") || null }
      : { sku, delta: Number(f.get("delta")), reason: f.get("reason"), location_id: f.get("location_id") || null, note: f.get("note") || null };
    setBusy(true);
    const r = await adminCall(`v1/admin/stock/${mode}`, { json: body, lang });
    setBusy(false);
    if (!r.ok) return setMsg({ tone: "bad", text: r.message });
    setMsg({ tone: "ok", text: `${sku}: ${d.common.saved}` });
    setOpen(null);
    router.refresh();
  }

  async function history(sku: string) {
    setOpen({ sku, mode: "history" });
    const r = await adminCall<{ events: Event[] }>(`v1/admin/stock/${encodeURIComponent(sku)}/ledger`, { lang });
    setEvents(r.ok ? r.data.events : []);
  }

  const shopper = (i: Item) => (!i.shopper?.in_stock ? s.shopper.out : i.shopper.low ? s.shopper.low : s.shopper.in);

  return (
    <>
      <div className="adm-head">
        <div>
          <h1 className="h1">{s.title}</h1>
          <p className="muted" style={{ fontSize: "var(--fs-ui)" }}>{s.lede}</p>
        </div>
      </div>
      <form action="/admin/stock" method="get" role="search" style={{ marginBottom: "calc(var(--st) * 2)", maxWidth: 520 }}>
        <label className="sr-only" htmlFor="stock-search">{d.common.search}</label>
        <input id="stock-search" className="input" type="search" name="q" defaultValue={q} placeholder={s.searchPlaceholder} />
      </form>
      <p className={`adm-msg adm-msg--${msg?.tone || "ok"}`} role="status" aria-live="polite">{msg?.text}</p>
      <div className="adm-scroll">
        <table className="adm-table adm-table--stack" data-testid="stock-table">
          <thead>
            <tr>
              <th scope="col">{s.cols.product}</th>
              <th scope="col">{s.cols.sku}</th>
              <th scope="col" className="num">{s.cols.onHand}</th>
              <th scope="col" className="num">{s.cols.reserved}</th>
              <th scope="col" className="num">{s.cols.available}</th>
              <th scope="col">{s.cols.shopper}</th>
              <th scope="col"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <StockRows key={i.variant_id} i={i}>
                <tr data-retired={i.variant_active ? undefined : "true"} data-sku={i.sku}>
                  <td className="wide">
                    {i.product_id ? <Link className="adm-link" href={`/admin/products/${i.product_id}`}>{pickLang(lang, i.product_title, i.product_title_uk)}</Link> : i.product_title}
                    <span className="muted" style={{ display: "block", fontSize: "var(--fs-ui)" }}>{pickLang(lang, i.label, i.label_uk)}</span>
                  </td>
                  <td className="mono" data-label={s.cols.sku}>{i.sku}</td>
                  <td className="num" data-label={s.cols.onHand}>{i.on_hand}</td>
                  <td className="num" data-label={s.cols.reserved}>{i.reserved}</td>
                  <td className="num" data-label={s.cols.available}><strong>{i.available}</strong></td>
                  <td data-label={s.cols.shopper}><span className={`adm-status adm-status--${!i.shopper?.in_stock ? "bad" : i.shopper.low ? "wait" : "ok"}`}>{shopper(i)}</span></td>
                  <td className="wide">
                    <span className="adm-actions" style={{ gap: "var(--st)" }}>
                      <button className="adm-link" type="button" onClick={() => setOpen({ sku: i.sku, mode: "receive" })}>{s.receive}</button>
                      <button className="adm-link" type="button" onClick={() => setOpen({ sku: i.sku, mode: "adjust" })}>{s.adjust}</button>
                      <button className="adm-link" type="button" onClick={() => history(i.sku)}>{s.history}</button>
                    </span>
                  </td>
                </tr>
                {open?.sku === i.sku ? (
                  <tr>
                    <td colSpan={7} className="wide" style={{ background: "var(--linen-shade)" }}>
                      {open.mode === "history" ? (
                        <ol className="adm-timeline">
                          {events.map((e) => (
                            <li key={e.id}><time>{adminTime(e.created_at)}</time><span className="mono">{e.type} {e.qty > 0 ? `+${e.qty}` : e.qty} · {e.location} · {e.reference}{e.note ? ` · ${e.note}` : ""}</span></li>
                          ))}
                        </ol>
                      ) : (
                        <form className="adm-grid4" style={{ padding: "var(--st) 0", alignItems: "end" }} onSubmit={(ev) => submit(ev, open.mode as "receive" | "adjust", i.sku)} data-testid={`stock-${open.mode}`}>
                          {open.mode === "receive" ? (
                            <label className="field"><span className="field__label">{s.qty}</span><input className="input mono" name="qty" type="number" min={1} max={100000} required autoFocus /></label>
                          ) : (
                            <>
                              <label className="field"><span className="field__label">{s.delta}</span><input className="input mono" name="delta" type="number" min={-100000} max={100000} required autoFocus /></label>
                              <label className="field"><span className="field__label">{s.reason}</span>
                                <select className="select" name="reason" required defaultValue="">
                                  <option value="" disabled>—</option>
                                  {taxonomy.adjust_reasons.map((r) => <option key={r.id} value={r.id}>{pickLang(lang, r.label, r.label_uk)}</option>)}
                                </select></label>
                            </>
                          )}
                          <label className="field"><span className="field__label">{s.location}</span>
                            <select className="select" name="location_id" defaultValue={i.locations[0]?.location_id || sellable[0]?.id || ""}>
                              {sellable.length ? sellable.map((l) => <option key={l.id} value={l.id}>{l.id}</option>) : <option value="">A-LANE-01</option>}
                            </select></label>
                          <label className="field"><span className="field__label">{s.note}</span><input className="input" name="note" maxLength={1000} /></label>
                          <button className="btn btn--red" type="submit" disabled={busy}>{open.mode === "receive" ? s.receiveButton : s.adjustButton}</button>
                        </form>
                      )}
                    </td>
                  </tr>
                ) : null}
              </StockRows>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function StockRows({ children }: { i: Item; children: React.ReactNode }) {
  return <>{children}</>;
}
