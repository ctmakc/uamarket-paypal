"use client";

import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import type { Lang } from "@/lib/i18n";
import { href, t } from "@/lib/i18n";
import { tb } from "@/lib/i18n.buy";
import { tu } from "@/lib/i18n.ui";

/**
 * The search control in the phone header: a square with a magnifier drawn as a stitched ring.
 * It opens a search row pinned under the header with the field focused; Escape, the close
 * button or a page change closes it. Below 1024px only, where the header has no search field.
 */
export default function PhoneSearch({ lang }: { lang: Lang }) {
  const d = t(lang);
  const b = tb(lang);
  const u = tu(lang);
  const id = useId();
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const pathname = usePathname();

  useEffect(() => { setOpen(false); }, [pathname]);
  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      btnRef.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        className="psearch__btn"
        aria-expanded={open}
        aria-controls={id}
        aria-label={open ? b.searchClose : b.searchOpen}
        data-on={open ? "true" : undefined}
        onClick={() => setOpen((v) => !v)}
        data-phone-search
      >
        <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
          <circle cx="6.5" cy="6.5" r="4.5" fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="3 1.6" />
          <path d="M10 10 L14.5 14.5" stroke="currentColor" strokeWidth="2.4" strokeLinecap="square" />
        </svg>
      </button>
      <div id={id} className="psearch" hidden={!open}>
        <form action={href(lang, "/shop")} method="get" role="search" className="psearch__form canvas">
          <label className="sr-only" htmlFor={`${id}-q`}>{d.nav.search}</label>
          <input ref={inputRef} id={`${id}-q`} name="q" type="search" enterKeyHint="search" className="input" placeholder={d.nav.searchPlaceholder} />
          <button type="submit" className="btn">{u.searchGo}</button>
        </form>
      </div>
    </>
  );
}
