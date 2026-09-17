import Link from "next/link";
import { Suspense } from "react";
import type { Lang } from "@/lib/i18n";
import { href, t } from "@/lib/i18n";
import { tu } from "@/lib/i18n.ui";
import BagButton from "./BagButton";
import BagToast from "./BagToast";
import LangSwitch from "./LangSwitch";
import MobileNav from "./MobileNav";
import PhoneSearch from "./PhoneSearch";

export default function SiteHeader({ lang }: { lang: Lang }) {
  const d = t(lang);
  const u = tu(lang);
  const nav = [
    { to: "/shop", label: d.nav.shop },
    { to: "/makers", label: d.nav.makers },
    { to: "/about", label: d.nav.about },
    { to: "/order", label: d.footer.orderStatus },
  ];
  return (
    <>
      <a href="#main" className="skip">{u.skip}</a>
      <header className="hdr">
        <div className="canvas">
          <div className="hdr__row">
            <Link href={href(lang, "/")} className="hdr__mark" aria-label={d.brand}>
              <svg width="18" height="18" viewBox="0 0 14 14" aria-hidden="true" style={{ color: "var(--thread-red)" }}>
                <path d="M2 2 L12 12 M12 2 L2 12" stroke="currentColor" strokeWidth="2.6" strokeLinecap="square" fill="none" />
              </svg>
              <span>{d.brand}</span>
            </Link>
            <nav className="hdr__nav" aria-label="Main">
              {nav.map((n) => (
                <Link key={n.to} href={href(lang, n.to)} className="thread-link">
                  {n.label}
                </Link>
              ))}
            </nav>
            <div className="hdr__tools">
              <Suspense fallback={null}>
                <PhoneSearch lang={lang} />
              </Suspense>
              <Suspense fallback={null}>
                <MobileNav lang={lang} />
              </Suspense>
              <form action={href(lang, "/shop")} method="get" role="search" className="hdr__search">
                <label className="sr-only" htmlFor="q">{d.nav.search}</label>
                <input id="q" name="q" type="search" className="input hdr__q" placeholder={d.nav.searchPlaceholder} />
              </form>
              <span className="hdr__lang">
                <Suspense fallback={null}>
                  <LangSwitch lang={lang} />
                </Suspense>
              </span>
              <BagButton lang={lang} />
            </div>
          </div>
        </div>
        <BagToast lang={lang} />
      </header>
    </>
  );
}
