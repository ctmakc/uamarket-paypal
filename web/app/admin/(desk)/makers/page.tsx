import type { Metadata } from "next";
import Link from "next/link";
import { adminGet } from "@/lib/admin/api";
import { catalogueStatus } from "@/lib/geo";
import { adminDict, pickLang } from "@/lib/admin/i18n";
import { adminLang } from "@/lib/admin/server";
import { requireSession } from "@/lib/admin/session";
import type { AdminMaker } from "@/lib/admin/types";

export const metadata: Metadata = { title: "Makers" };

export default async function MakersPage() {
  await requireSession();
  const lang = await adminLang();
  const d = adminDict(lang);
  const { items } = await adminGet<{ items: AdminMaker[] }>("/v1/admin/makers?status=all");
  const seeded = catalogueStatus() === "placeholder";
  return (
    <>
      <div className="adm-head">
        <h1 className="h1">{d.makers.title}</h1>
        <Link href="/admin/makers/new" className="btn btn--red">{d.makers.new}</Link>
      </div>
      {seeded ? <p className="example-line" style={{ marginBottom: "calc(var(--st) * 2)" }}>{d.makers.seeded}</p> : null}
      {items.length ? (
        <div className="adm-rows" data-testid="maker-rows">
          {items.map((m) => (
            <Link key={m.id} href={`/admin/makers/${m.id}`} className={`adm-row adm-row--${m.active ? "ok" : "wait"}`} style={{ gridTemplateColumns: "minmax(0,2fr) minmax(0,2fr) auto auto auto" }}>
              <span>{pickLang(lang, m.name, m.name_uk)}<span className="adm-row__sub" style={{ display: "block" }}>{m.slug}</span></span>
              <span className="adm-row__sub">{pickLang(lang, m.region, m.region_uk)}</span>
              <span className="adm-row__sub">{d.makers.products(m.product_count)}</span>
              <span className={`adm-status adm-status--${m.active ? "ok" : "quiet"}`}>{m.active ? d.common.active : d.common.retired}</span>
              <span className="adm-row__go">{d.common.edit} →</span>
            </Link>
          ))}
        </div>
      ) : <p className="adm-empty">{d.makers.empty}</p>}
    </>
  );
}
