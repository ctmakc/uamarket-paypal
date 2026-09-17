import Link from "next/link";
import type { Collection } from "@/lib/api";
import type { Lang } from "@/lib/i18n";
import { href, pick, t } from "@/lib/i18n";
import { tu } from "@/lib/i18n.ui";
import { colophonFor } from "@/lib/content";
import StitchMark from "./StitchMark";
import WordmarkChart from "./WordmarkChart";

/**
 * The footer's shop column used to hard-code the words "Heritage" and
 * "Everyday", so the Ukrainian site printed two English collection names on
 * every page while /uk/shop showed the same two as «Спадщина» and «Щодня». The
 * names now come from the catalogue, which is the only place they can be right
 * in both languages at once.
 *
 * The four column headings are h2: the page's own h1 is the only heading above
 * them, and h4 skipped two levels on every page (axe: heading-order).
 */
export default function SiteFooter({
  lang,
  contactEmail,
  collections = [],
}: {
  lang: Lang;
  contactEmail?: string | null;
  collections?: Collection[];
}) {
  const d = t(lang);
  const u = tu(lang);
  return (
    <footer className="ftr on-plate">
      <div className="canvas">
        <div className="ftr__grid">
          <nav className="ftr__col ftr__col--shop" aria-label={d.footer.shop}>
            <h2>{d.footer.shop}</h2>
            <Link href={href(lang, "/shop")} className="thread-link">{d.shop.all}</Link>
            {collections.map((c) => (
              <Link key={c.slug} href={href(lang, `/shop?collection=${c.slug}`)} className="thread-link">
                {pick(lang, c.title, c.title_uk)}
              </Link>
            ))}
            <Link href={href(lang, "/makers")} className="thread-link">{d.nav.makers}</Link>
          </nav>
          <nav className="ftr__col ftr__col--help" aria-label={d.footer.help}>
            <h2>{d.footer.help}</h2>
            <Link href={href(lang, "/about")} className="thread-link">{d.nav.about}</Link>
            <Link href={href(lang, "/faq")} className="thread-link">{u.pages.faq}</Link>
            <Link href={href(lang, "/shipping")} className="thread-link">{u.pages.shipping}</Link>
            <Link href={href(lang, "/care")} className="thread-link">{u.pages.care}</Link>
            <Link href={href(lang, "/order")} className="thread-link">{d.footer.orderStatus}</Link>
            {contactEmail ? <a href={`mailto:${contactEmail}`} className="thread-link">{contactEmail}</a> : null}
          </nav>
          <nav className="ftr__col ftr__col--terms" aria-label={u.pages.heading}>
            <h2>{u.pages.heading}</h2>
            <Link href={href(lang, "/privacy")} className="thread-link">{u.pages.privacy}</Link>
            <Link href={href(lang, "/terms")} className="thread-link">{u.pages.terms}</Link>
          </nav>
          <div className="ftr__legend">
            <h2>{d.footer.legend}</h2>
            <ul className="stack--tight ftr__legend-list">
              <li><StitchMark origin="HANDMADE_UA" lang={lang} /> <span>{d.origin.HANDMADE_UA_desc}</span></li>
              <li><StitchMark origin="MADE_UA" lang={lang} /> <span>{d.origin.MADE_UA_desc}</span></li>
              <li><StitchMark origin="DESIGNED_UA" lang={lang} /> <span>{d.origin.DESIGNED_UA_desc}</span></li>
            </ul>
          </div>
        </div>
        <WordmarkChart />
        <div className="ftr__colophon">
          <span>{colophonFor(lang)}</span>
          <span>© {new Date().getFullYear()} {d.brand}</span>
        </div>
      </div>
    </footer>
  );
}
