"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Motif from "@/components/Motif";
import { href, t } from "@/lib/i18n";
import { langFromPath, tu } from "@/lib/i18n.ui";

/**
 * The 404 inside a localised route. It reads the language off the path because
 * Next gives a not-found boundary no route params, and it offers the two doors
 * a lost visitor actually wants: the shop and the makers.
 */
export default function NotFound() {
  const lang = langFromPath(usePathname());
  const d = t(lang);
  const u = tu(lang);
  return (
    <section className="canvas band--tall">
      <div className="split">
        <div className="split__a stack">
          <p className="eyebrow">{u.notFound.code}</p>
          <h1 className="h1">{u.notFound.title}</h1>
          <p className="lede">{u.notFound.body}</p>
          <div className="cta-row">
            <Link href={href(lang, "/shop")} className="btn btn--red btn--lg">{u.notFound.shop}</Link>
            <Link href={href(lang, "/makers")} className="thread-link ui">{u.notFound.makers} →</Link>
            <Link href={href(lang, "/")} className="thread-link ui">{u.notFound.home} →</Link>
          </div>
          <form action={href(lang, "/shop")} method="get" role="search" className="find-row">
            <label className="field__label" htmlFor="nf-q">{u.notFound.searchLead}</label>
            <span className="find-row__controls">
              <input id="nf-q" name="q" type="search" className="input" placeholder={d.nav.searchPlaceholder} />
              <button type="submit" className="btn">{u.searchGo}</button>
            </span>
          </form>
        </div>
        <div className="split__b nf__motif">
          <div className="chart chart--pad">
            <Motif seed="not-on-the-chart" mode="tile" size={24} decorative />
          </div>
        </div>
      </div>
    </section>
  );
}
