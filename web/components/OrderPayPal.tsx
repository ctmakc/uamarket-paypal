"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import PayPalButton from "@/components/PayPalButton";
import type { PayPalConfig } from "@/lib/api";
import type { Lang } from "@/lib/i18n";
import { tp } from "@/lib/i18n.paypal";

/** Pay an unpaid PayPal order from its order page (the email link, or a closed PayPal window). */
export default function OrderPayPal({ lang, number, orderKey, config, amount }: { lang: Lang; number: string; orderKey: string; config: PayPalConfig; amount: string }) {
  const pp = tp(lang);
  const router = useRouter();
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function open(): Promise<string> {
    setError(null);
    setNote(null);
    const res = await fetch(`/api/order/${encodeURIComponent(number)}/paypal`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ key: orderKey }) });
    const body = await res.json().catch(() => ({}));
    if (!res.ok || !body?.id) { setError(pp.failed); throw new Error("paypal"); }
    return String(body.id);
  }

  async function approved(id: string) {
    setNote(pp.capturing);
    const res = await fetch(`/api/order/${encodeURIComponent(number)}/paypal/capture`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ paypal_order_id: id, key: orderKey }) });
    const body = await res.json().catch(() => ({}));
    setNote(null);
    if (!res.ok) { setError(body?.code === "declined" ? pp.declined : pp.failed); return; }
    router.refresh();
  }

  return (
    <div className="stack--tight" data-order-paypal>
      <p className="h3">{pp.orderPayTitle}</p>
      <p className="measure">{pp.orderPayBody(amount)}</p>
      {config.env === "sandbox" ? <p className="mono mono--sm muted">{pp.paySubSandbox}</p> : null}
      <div style={{ maxWidth: "calc(var(--blk) * 3.6)" }}>
        <PayPalButton config={config} lang={lang} createOrder={open} onApproved={approved}
          onCancel={() => setNote(pp.cancelled)} onError={(m) => { if (m !== "paypal") setError(pp.failed); }} />
      </div>
      {note ? <p className="mono mono--sm" role="status">{note}</p> : null}
      {error ? <p className="error" role="alert">{error}</p> : null}
    </div>
  );
}
