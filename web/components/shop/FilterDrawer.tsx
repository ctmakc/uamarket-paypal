"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect, useId, useRef, useState } from "react";
import type { Lang } from "@/lib/i18n";
import { tb } from "@/lib/i18n.buy";
import { ts } from "@/lib/i18n.shop";
import type { ActiveChip } from "./ActiveFilters";
import UnpickMark from "./UnpickMark";

/**
 * The filter rails, folded into a drawer on a phone.
 *
 * From 720px up the rails are an ordinary block and this wrapper draws nothing of its own.
 * Below it the page shows one "Filter · Sort" button and the active filters as chips that
 * take themselves off; the rails open in a panel that slides over the page from the bottom.
 * Every control inside stays a link, so choosing a filter loads the filtered page and the
 * drawer closes with the navigation. Escape and the close button close it too, and the focus
 * goes back to the button.
 */
export default function FilterDrawer({
  lang,
  chips,
  clearHref,
  total,
  children,
}: {
  lang: Lang;
  /** Every active filter, each with the link that removes it. */
  chips: ActiveChip[];
  clearHref: string;
  total: number;
  children: ReactNode;
}) {
  const b = tb(lang).filters;
  const s = ts(lang);
  const id = useId();
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const pathname = usePathname();
  const params = useSearchParams();
  const query = params?.toString();

  useEffect(() => { setOpen(false); }, [pathname, query]);
  useEffect(() => {
    document.body.classList.toggle("fdrawer-open", open);
    if (!open) return;
    panelRef.current?.querySelector<HTMLElement>("[data-fdrawer-close]")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      btnRef.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); document.body.classList.remove("fdrawer-open"); };
  }, [open]);

  return (
    <>
      <div className="fbar">
        <button
          ref={btnRef}
          type="button"
          className="fbar__btn"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen(true)}
          data-filter-open
        >
          <svg viewBox="0 0 14 14" width="14" height="14" aria-hidden="true">
            <path d="M1 3 H13 M3 7 H11 M5 11 H9" stroke="currentColor" strokeWidth="2" />
          </svg>
          <span>{chips.length ? b.openCount(chips.length) : b.open}</span>
        </button>
        {chips.length ? (
          <div className="fbar__chips" role="group" aria-label={s.activeFilters}>
            {chips.map((c) => (
              <Link key={c.key} href={c.href} className="chip on-plate" data-on="true" aria-label={s.remove(c.label)}>
                <span>{c.label}</span>
                <UnpickMark />
              </Link>
            ))}
            <Link href={clearHref} className="thread-link ui">{s.clearAll}</Link>
          </div>
        ) : null}
      </div>
      <div ref={panelRef} id={id} className="fdrawer" data-open={open ? "true" : undefined} role="group" aria-label={s.filterRegion}>
        <div className="fdrawer__head">
          <p className="h3">{b.title}</p>
          <button type="button" className="fdrawer__close" onClick={() => { setOpen(false); btnRef.current?.focus(); }} aria-label={b.close} data-fdrawer-close>
            <svg viewBox="0 0 14 14" width="14" height="14" aria-hidden="true"><path d="M2 2 L12 12 M12 2 L2 12" stroke="currentColor" strokeWidth="2" /></svg>
          </button>
        </div>
        <div className="fdrawer__body">{children}</div>
        <div className="fdrawer__foot">
          <button type="button" className="btn btn--red btn--lg btn--wide" onClick={() => { setOpen(false); btnRef.current?.focus(); }}>{b.done(total)}</button>
        </div>
      </div>
      {open ? <div className="fdrawer__scrim" aria-hidden="true" onClick={() => setOpen(false)} /> : null}
    </>
  );
}
