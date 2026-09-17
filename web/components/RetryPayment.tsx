"use client";

import { useState } from "react";
import type { Lang } from "@/lib/i18n";
import { to } from "@/lib/i18n.order";

/** Opens a new card session for an unpaid order whose last one expired, then goes there. */
export default function RetryPayment({ lang, number, orderKey }: { lang: Lang; number: string; orderKey: string }) {
  const o = to(lang);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  async function start() {
    setBusy(true);
    setError(false);
    try {
      const res = await fetch(`/api/order/${encodeURIComponent(number)}/pay`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ key: orderKey }) });
      const body = res.ok ? await res.json() : null;
      const url = body?.payment?.checkout_url as string | undefined;
      if (url) {
        window.location.assign(url);
        return;
      }
      setError(true);
    } catch {
      setError(true);
    }
    setBusy(false);
  }

  return (
    <div className="stack--tight">
      <p>
        <button type="button" className="btn btn--red" onClick={start} disabled={busy} data-retry-payment>
          {o.retryPay}
        </button>
      </p>
      {error ? <p className="error" role="alert">{o.retryFailed}</p> : null}
    </div>
  );
}
