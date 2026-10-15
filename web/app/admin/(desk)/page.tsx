import type { Metadata } from "next";
import Link from "next/link";
import { adminGet } from "@/lib/admin/api";
import { adminDict, adminMoney, adminTime } from "@/lib/admin/i18n";
import { adminLang } from "@/lib/admin/server";
import { requireSession } from "@/lib/admin/session";
import type { ExceptionRow, OrderSummary, QueueName } from "@/lib/admin/types";

export const metadata: Metadata = { title: "Orders" };

const QUEUES: QueueName[] = ["awaiting_payment", "to_pack", "ready_to_ship", "shipped", "exceptions", "cancelled"];

type QueueResponse = { queue: QueueName; counts: Record<string, number>; items: (OrderSummary & { next?: string })[]; other_exceptions: ExceptionRow[] };

function nextFor(state: string, method: string | null): keyof ReturnType<typeof adminDict>["queue"]["next"] {
  if (state === "AWAITING_PAYMENT") return method === "PAYPAL" ? "await_paypal" : method === "STRIPE" ? "await_card" : "mark_paid";
  if (state === "PAID" || state === "OUT_OF_STOCK") return "reserve";
  if (state === "PICK_PLANNED" || state === "PICKING") return "scan";
  if (state === "PICK_VERIFIED") return "pack";
  if (state === "PACKING" || state === "LABEL_VERIFIED" || state === "READY_FOR_PICKUP") return "ship";
  return "none";
}

export default async function QueuePage({ searchParams }: { searchParams: Promise<{ queue?: string; q?: string }> }) {
  await requireSession();
  const lang = await adminLang();
  const d = adminDict(lang);
  const sp = await searchParams;
  const q = (sp.q || "").slice(0, 120);
  const queue: QueueName = QUEUES.includes(sp.queue as QueueName) ? (sp.queue as QueueName) : "to_pack";
  const [data, summary] = await Promise.all([
    adminGet<QueueResponse>(`/v1/admin/orders?queue=${queue}${q ? `&q=${encodeURIComponent(q)}` : ""}`),
    adminGet<{ paid_today_cad: string }>("/v1/admin/summary").catch(() => null),
  ]);
  return (
    <>
      <div className="adm-head">
        <h1 className="h1">{d.queue.title}</h1>
        {summary ? (
          <p className="mono">{d.queue.paidToday} <strong>CA$ {summary.paid_today_cad}</strong></p>
        ) : null}
      </div>
      <nav className="adm-tabs" aria-label={d.queue.title}>
        {QUEUES.map((name) => (
          <Link
            key={name}
            href={`/admin?queue=${name}`}
            className={`adm-tab${name === "exceptions" && data.counts[name] ? " adm-tab--alert" : ""}`}
            aria-current={!q && name === queue ? "page" : undefined}
          >
            {d.queue.tabs[name]} <b>{data.counts[name] ?? 0}</b>
          </Link>
        ))}
      </nav>
      <form action="/admin" method="get" role="search" style={{ marginBottom: "calc(var(--st) * 2)", maxWidth: 520 }}>
        <input type="hidden" name="queue" value={queue} />
        <label className="sr-only" htmlFor="order-search">{d.common.search}</label>
        <input id="order-search" className="input" type="search" name="q" defaultValue={q} placeholder={d.queue.searchPlaceholder} />
      </form>
      {data.items.length ? (
        <div className="adm-rows" data-testid="queue-rows">
          {data.items.map((o) => {
            const next = nextFor(o.state, o.payment_method);
            const tone = o.has_exception || o.state === "OUT_OF_STOCK" ? "alert" : o.state === "HANDOFF_COMPLETE" ? "ok" : o.state === "AWAITING_PAYMENT" ? "wait" : "";
            return (
              <Link key={o.id} href={`/admin/orders/${o.id}`} className={`adm-row${tone ? ` adm-row--${tone}` : ""}`} data-order={o.order_number}>
                <span>
                  <span className="adm-row__num">{o.order_number}</span>
                  <span className="adm-row__sub" style={{ display: "block" }}>{adminTime(o.created_at)}</span>
                </span>
                <span>
                  {o.customer_name || o.customer_email || o.channel}
                  <span className="adm-row__sub" style={{ display: "block" }}>
                    {[o.city, o.province].filter(Boolean).join(" ")}
                    {o.demo ? <> · <span className="adm-tag">{d.common.demo}</span></> : null}
                  </span>
                </span>
                <span className="adm-row__sub">{d.queue.items(o.items)}</span>
                <span className="adm-row__money">{adminMoney(o.total_cad)}</span>
                <span className="adm-row__go">{d.queue.next[next]} →</span>
              </Link>
            );
          })}
        </div>
      ) : (
        <p className="adm-empty">{d.queue.empty}</p>
      )}
      {data.other_exceptions.length ? (
        <section className="adm-section" style={{ marginTop: "calc(var(--st) * 4)" }}>
          <h2 className="adm-section__title">{d.queue.other}</h2>
          {data.other_exceptions.map((e) => (
            <div key={e.id} className="adm-exc">
              <p className="mono mono--sm">{e.kind} · {e.reference_type} {e.reference_id} · {adminTime(e.created_at)}</p>
              <p className="ui">{e.summary}</p>
            </div>
          ))}
        </section>
      ) : null}
    </>
  );
}
