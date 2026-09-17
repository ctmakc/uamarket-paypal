"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { Quote } from "@/lib/api";
import { ADDED_EVENT, lineFacts } from "@/lib/bag";
import type { Lang } from "@/lib/i18n";
import { href } from "@/lib/i18n";
import { tb } from "@/lib/i18n.buy";

/**
 * The confirmation that a tap on "Add to bag" landed, pinned under the header where the bag
 * count just changed. A bleached plate with a green rule, the piece's name and variant in the
 * page's language, and the two ways on: the bag and checkout.
 *
 * It closes itself after six seconds, but never while the pointer or the focus is inside it
 * (WCAG 2.2.1), and Escape closes it at once. It belongs to the page it was raised on: a tap
 * on one of its own links or any move to another page closes it, so it never sits over the
 * bag or the checkout form. It is a live region mounted from the first
 * render, so a screen reader hears the sentence.
 */
export default function BagToast({ lang }: { lang: Lang }) {
  const b = tb(lang);
  const [text, setText] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const timer = useRef<number | null>(null);
  const hovered = useRef(false);
  const pathname = usePathname();

  function close() {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = null;
    hovered.current = false;
    setOpen(false);
  }

  useEffect(() => {
    close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  function schedule() {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      if (hovered.current || boxRef.current?.contains(document.activeElement)) { schedule(); return; }
      setOpen(false);
    }, 6000);
  }

  useEffect(() => {
    const onAdded = (e: Event) => {
      const { sku, qty } = (e as CustomEvent<{ sku: string; qty: number }>).detail || {};
      if (!sku) return;
      fetch("/api/quote", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ lines: [{ sku, qty: 1 }] }) })
        .then((r) => (r.ok ? r.json() : null))
        .then((q: Quote | null) => {
          const f = lineFacts(lang, { sku, slug: "", qty: qty || 1 }, q?.lines?.[0]);
          const name = [f.title, f.label].filter(Boolean).join(" · ");
          setText(b.toastAdded(`${qty > 1 ? `${qty} × ` : ""}${name}`));
        })
        .catch(() => setText(b.toastAdded(sku)))
        .finally(() => { setOpen(true); schedule(); });
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener(ADDED_EVENT, onAdded);
    document.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener(ADDED_EVENT, onAdded);
      document.removeEventListener("keydown", onKey);
      if (timer.current) window.clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang]);

  return (
    <div className="toast-slot" role="status" aria-live="polite">
      {open && text ? (
        <div
          ref={boxRef}
          className="toast canvas"
          data-bag-toast
          onMouseEnter={() => { hovered.current = true; }}
          onMouseLeave={() => { hovered.current = false; }}
        >
          <div className="toast__plate">
            <p className="toast__text">{text}</p>
            <div className="toast__actions">
              <Link href={href(lang, "/bag")} className="btn btn--ghost" onClick={close}>{b.toastView}</Link>
              <Link href={href(lang, "/checkout")} className="btn btn--red" onClick={close}>{b.toastCheckout}</Link>
              <button type="button" className="toast__close" onClick={close} aria-label={b.toastClose}>
                <svg viewBox="0 0 14 14" width="14" height="14" aria-hidden="true"><path d="M2 2 L12 12 M12 2 L2 12" stroke="currentColor" strokeWidth="2" /></svg>
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
