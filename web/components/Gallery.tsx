"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Lang } from "@/lib/i18n";
import { tb } from "@/lib/i18n.buy";

export type GalleryPhoto = { src: string; srcset?: string; width?: number; height?: number; alt: string };

/**
 * The product photos: one main frame, a row of thumbnails that are real buttons, swipe on a
 * phone, and a full-screen view.
 *
 * - A thumbnail is a button with aria-pressed; click, Enter or Space shows that photo.
 * - On the main frame a horizontal swipe of 40px or more moves to the next or previous photo.
 * - The corner button opens a native <dialog>: Escape closes it (the browser does that), the
 *   arrow keys and two buttons move through the photos, and focus returns to the opener.
 * - The first photo carries width, height, srcset and fetchpriority=high; it is the page's
 *   largest paint on a phone, so it is never lazy.
 */
export default function Gallery({ lang, photos, title }: { lang: Lang; photos: GalleryPhoto[]; title: string }) {
  const g = tb(lang).gallery;
  const [index, setIndex] = useState(0);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const openerRef = useRef<HTMLButtonElement>(null);
  const start = useRef<{ x: number; y: number } | null>(null);
  const count = photos.length;
  const current = photos[index] ?? photos[0];

  const go = useCallback((to: number) => setIndex(((to % count) + count) % count), [count]);

  function onPointerDown(e: React.PointerEvent) {
    start.current = { x: e.clientX, y: e.clientY };
  }
  function onPointerUp(e: React.PointerEvent) {
    const s = start.current;
    start.current = null;
    if (!s || count < 2) return;
    const dx = e.clientX - s.x;
    const dy = e.clientY - s.y;
    if (Math.abs(dx) >= 40 && Math.abs(dx) > Math.abs(dy)) go(index + (dx < 0 ? 1 : -1));
  }
  // Touch events as well: a vertical page scroll cancels pointer events on some phones
  // before pointerup, and Playwright's touch emulation dispatches touch events.
  function onTouchStart(e: React.TouchEvent) {
    const t = e.touches[0];
    start.current = { x: t.clientX, y: t.clientY };
  }
  function onTouchEnd(e: React.TouchEvent) {
    const s = start.current;
    start.current = null;
    const t = e.changedTouches[0];
    if (!s || !t || count < 2) return;
    const dx = t.clientX - s.x;
    const dy = t.clientY - s.y;
    if (Math.abs(dx) >= 40 && Math.abs(dx) > Math.abs(dy)) go(index + (dx < 0 ? 1 : -1));
  }

  function openFull() {
    const dlg = dialogRef.current;
    if (!dlg) return;
    if (typeof dlg.showModal === "function") dlg.showModal();
    else dlg.setAttribute("open", "");
  }

  useEffect(() => {
    const dlg = dialogRef.current;
    if (!dlg) return;
    const onClose = () => openerRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") { e.preventDefault(); go(index + 1); }
      if (e.key === "ArrowLeft") { e.preventDefault(); go(index - 1); }
    };
    dlg.addEventListener("close", onClose);
    dlg.addEventListener("keydown", onKey);
    return () => {
      dlg.removeEventListener("close", onClose);
      dlg.removeEventListener("keydown", onKey);
    };
  }, [go, index]);

  if (!current) return null;
  const sizes = "(max-width: 1023px) 100vw, 50vw";

  return (
    <div className="gallery" role="group" aria-roledescription="gallery" aria-label={g.region}>
      <div
        className="gallery__main"
        onPointerDown={onPointerDown}
        onPointerUp={onPointerUp}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
        data-gallery-main
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          key={current.src}
          src={current.src}
          srcSet={current.srcset || undefined}
          sizes={current.srcset ? sizes : undefined}
          width={current.width}
          height={current.height}
          alt={current.alt || title}
          fetchPriority={index === 0 ? "high" : "auto"}
          decoding={index === 0 ? "sync" : "async"}
          draggable={false}
        />
        <button ref={openerRef} type="button" className="gallery__full" onClick={openFull} aria-label={g.open} data-gallery-open>
          <svg viewBox="0 0 14 14" width="14" height="14" aria-hidden="true">
            <path d="M1 5 V1 H5 M9 1 H13 V5 M13 9 V13 H9 M5 13 H1 V9" stroke="currentColor" strokeWidth="2" fill="none" />
          </svg>
        </button>
        {count > 1 ? <span className="gallery__count mono mono--sm" aria-hidden="true">{g.counter(index + 1, count)}</span> : null}
      </div>

      {count > 1 ? (
        <div className="gallery__thumbs">
          {photos.map((p, i) => (
            <button
              key={p.src}
              type="button"
              className="gallery__thumb"
              aria-pressed={i === index}
              aria-label={g.show(i + 1, count)}
              onClick={() => setIndex(i)}
              data-gallery-thumb={i}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={p.src} srcSet={p.srcset || undefined} sizes="120px" alt="" loading="lazy" decoding="async" width={p.width} height={p.height} />
            </button>
          ))}
        </div>
      ) : null}

      <dialog ref={dialogRef} className="lightbox" aria-label={title} data-lightbox>
        <div className="lightbox__bar">
          <span className="mono mono--sm">{count > 1 ? g.counter(index + 1, count) : ""}</span>
          <form method="dialog">
            <button type="submit" className="lightbox__btn" aria-label={g.close} data-lightbox-close>
              <svg viewBox="0 0 14 14" width="16" height="16" aria-hidden="true"><path d="M2 2 L12 12 M12 2 L2 12" stroke="currentColor" strokeWidth="2" /></svg>
            </button>
          </form>
        </div>
        <div className="lightbox__stage" onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={current.src} srcSet={current.srcset || undefined} sizes="100vw" alt={current.alt || title} />
        </div>
        {count > 1 ? (
          <div className="lightbox__nav">
            <button type="button" className="lightbox__btn" onClick={() => go(index - 1)} aria-label={g.prev}>←</button>
            <button type="button" className="lightbox__btn" onClick={() => go(index + 1)} aria-label={g.next}>→</button>
          </div>
        ) : null}
      </dialog>
    </div>
  );
}
