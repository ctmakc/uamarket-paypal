"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { Lang } from "@/lib/i18n";
import { to } from "@/lib/i18n.order";

export default function TestPayButton({ lang, session, amount, orderHref }: { lang: Lang; session: string; amount: string; orderHref: string }) {
  const p = to(lang).testPage;
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  async function pay() {
    setBusy(true);
    setError(false);
    try {
      const res = await fetch(`/api/pay/test/${encodeURIComponent(session)}`, { method: "POST" });
      const body = res.ok ? await res.json() : null;
      if (body?.paid) {
        router.push(orderHref);
        return;
      }
    } catch {
      /* falls through to the error line */
    }
    setError(true);
    setBusy(false);
  }

  return (
    <div className="stack--tight">
      <p>
        <button type="button" className="btn btn--red btn--lg btn--wide" onClick={pay} disabled={busy} data-test-pay>
          {busy ? p.paying : p.pay(amount)}
        </button>
      </p>
      {error ? <p className="error" role="alert">{p.failed}</p> : null}
    </div>
  );
}
