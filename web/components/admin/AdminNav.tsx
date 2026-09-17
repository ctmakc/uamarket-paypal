"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { adminCall } from "@/lib/admin/client";
import { adminDict, type AdminLang } from "@/lib/admin/i18n";

export default function AdminNav({ lang }: { lang: AdminLang }) {
  const d = adminDict(lang);
  const path = usePathname() || "/admin";
  const items = [
    { href: "/admin", label: d.nav.orders, on: path === "/admin" || path.startsWith("/admin/orders") },
    { href: "/admin/products", label: d.nav.products, on: path.startsWith("/admin/products") },
    { href: "/admin/makers", label: d.nav.makers, on: path.startsWith("/admin/makers") },
    { href: "/admin/stock", label: d.nav.stock, on: path.startsWith("/admin/stock") },
    { href: "/admin/locker", label: d.nav.locker, on: path.startsWith("/admin/locker") },
    { href: "/admin/import", label: d.nav.import, on: path.startsWith("/admin/import") },
  ];
  async function signOut() {
    await adminCall("logout", { method: "POST", lang });
    window.location.assign("/admin/login");
  }
  const nav = useRef<HTMLElement>(null);
  useEffect(() => {
    // On a phone the tabs scroll sideways; keep the current one in view.
    const current = nav.current?.querySelector<HTMLElement>('[aria-current="page"]');
    if (current && nav.current && nav.current.scrollWidth > nav.current.clientWidth) {
      nav.current.scrollLeft += current.getBoundingClientRect().left - nav.current.getBoundingClientRect().left - (nav.current.clientWidth - current.offsetWidth) / 2;
    }
  }, [path]);
  const other = lang === "uk" ? "en" : "uk";
  return (
    <header className="adm-top">
      <div className="adm-wrap adm-top__row">
        <Link href="/admin" className="adm-top__mark">{d.brand} <small>{d.admin}</small></Link>
        <nav ref={nav} className="adm-nav" aria-label={d.admin}>
          {items.map((i) => (
            <Link key={i.href} href={i.href} aria-current={i.on ? "page" : undefined}>{i.label}</Link>
          ))}
        </nav>
        <div className="adm-top__tools">
          <a href={`/admin/api/lang?to=${other}&back=${encodeURIComponent(path)}`} lang={other} hrefLang={other}>
            {other.toUpperCase()}
          </a>
          <button type="button" onClick={signOut}>{d.signOut}</button>
        </div>
      </div>
    </header>
  );
}
