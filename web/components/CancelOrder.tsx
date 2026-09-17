"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import type { Lang } from "@/lib/i18n";
import { t } from "@/lib/i18n";

/**
 * Cancelling an order is a disclosure, so it behaves like one.
 *
 * The trigger stays mounted while the confirmation is open and carries
 * aria-expanded and aria-controls, the confirmation is a named group that takes
 * the focus when it opens, Escape closes it and hands the focus back, and the
 * trigger is hidden from the tab order only in the sense that it becomes the
 * "keep the order" way out — it is still the element the focus returns to.
 */
export default function CancelOrder({ lang, number, orderKey }: { lang: Lang; number: string; orderKey: string }) {
  const d = t(lang);
  const router = useRouter();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const panelId = useId();
  const btnRef = useRef<HTMLButtonElement>(null);
  const firstRef = useRef<HTMLButtonElement>(null);

  function close() {
    setConfirm(false);
    btnRef.current?.focus();
  }

  useEffect(() => {
    if (!confirm) return;
    firstRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setConfirm(false);
      btnRef.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [confirm]);

  async function cancel() {
    setBusy(true); setError(null);
    const res = await fetch(`/api/order/${encodeURIComponent(number)}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ key: orderKey }) });
    if (!res.ok) { setError(d.checkout.errors.generic); setBusy(false); return; }
    router.refresh();
    setBusy(false);
  }

  return (
    <div className="stack--tight">
      <p>
        <button
          ref={btnRef}
          type="button"
          className="thread-link ui muted"
          aria-expanded={confirm}
          aria-controls={panelId}
          onClick={() => (confirm ? close() : setConfirm(true))}
        >
          {d.order.cancel}
        </button>
      </p>
      <div id={panelId} hidden={!confirm} className="plate stack--tight" role="group" aria-labelledby={`${panelId}-q`}>
        <p className="ui" id={`${panelId}-q`}>{d.order.cancelConfirm}</p>
        <div style={{ display: "flex", gap: "var(--st)" }}>
          <button ref={firstRef} type="button" className="btn btn--ghost" onClick={cancel} disabled={busy}>{d.order.cancel}</button>
          <button type="button" className="thread-link ui" onClick={close}>{d.common.close}</button>
        </div>
        {error ? <p className="error" role="alert">{error}</p> : null}
      </div>
    </div>
  );
}
