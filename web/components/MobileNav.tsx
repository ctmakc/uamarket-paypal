"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import type { Lang } from "@/lib/i18n";
import { href, t } from "@/lib/i18n";
import { tu } from "@/lib/i18n.ui";
import LangSwitch from "./LangSwitch";

/**
 * The phone menu. The header has no room for the nav, the search field and the
 * language switch at 390px, so they live in a disclosure panel under it.
 *
 * The control is drawn, not borrowed: a small counted square with three running
 * stitches, on the same pressed-chip ground the shop filters use. Escape closes
 * the panel and returns focus to the button; opening it moves focus to the
 * search field; following a link closes it; and focus leaving the panel closes
 * it too, so the tab order never continues into the page behind the panel.
 */
export default function MobileNav({ lang }: { lang: Lang }) {
  const d = t(lang);
  const u = tu(lang);
  const panelId = useId();
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const pathname = usePathname();

  // A client navigation leaves the panel mounted; close it when the page changes.
  useEffect(() => { setOpen(false); }, [pathname]);

  useEffect(() => {
    if (!open) return;
    searchRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      btnRef.current?.focus();
    };
    const onDown = (e: PointerEvent) => {
      const target = e.target as Node;
      if (panelRef.current?.contains(target) || btnRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
    };
  }, [open]);

  const nav = [
    { to: "/shop", label: d.nav.shop },
    { to: "/makers", label: d.nav.makers },
    { to: "/about", label: d.nav.about },
    { to: "/order", label: d.footer.orderStatus },
  ];

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        className="mnav__btn"
        data-on={open ? "true" : undefined}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => {
          const next = !open;
          setOpen(next);
          if (!next) btnRef.current?.focus();
        }}
      >
        <svg className="mnav__glyph" viewBox="0 0 14 14" aria-hidden="true">
          <path d="M1 3 H5 M7 3 H13 M1 7 H9 M11 7 H13 M1 11 H5 M7 11 H13" stroke="currentColor" strokeWidth="2" fill="none" />
        </svg>
        <span>{open ? u.menuClose : u.menu}</span>
      </button>

      {/* The panel paints an opaque ground over the page, so focus must not walk
          out of it into content nobody can see. Tabbing past the last item
          closes the panel, using the same boundary the pointer handler above
          already computes. */}
      <div
        ref={panelRef}
        id={panelId}
        className="mnav chart"
        hidden={!open}
        onBlur={(e) => {
          if (!open) return;
          const next = e.relatedTarget as Node | null;
          if (next && (panelRef.current?.contains(next) || btnRef.current?.contains(next))) return;
          setOpen(false);
        }}
      >
        <form action={href(lang, "/shop")} method="get" role="search" className="mnav__search">
          <label className="sr-only" htmlFor={`${panelId}-q`}>{d.nav.search}</label>
          <input ref={searchRef} id={`${panelId}-q`} name="q" type="search" className="input" placeholder={d.nav.searchPlaceholder} />
          <button type="submit" className="btn">{u.searchGo}</button>
        </form>
        <nav aria-label={u.menuPanel}>
          <ul>
            {nav.map((n) => (
              <li key={n.to}>
                <Link href={href(lang, n.to)} className="mnav__link" onClick={() => setOpen(false)}>
                  <span>{n.label}</span>
                  <span aria-hidden="true">→</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>
        <div className="mnav__foot">
          <LangSwitch lang={lang} onNavigate={() => setOpen(false)} />
        </div>
      </div>
    </>
  );
}
