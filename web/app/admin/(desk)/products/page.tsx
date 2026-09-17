import type { Metadata } from "next";
import Link from "next/link";
import { adminGet } from "@/lib/admin/api";
import { adminDict, adminMoney, pickLang } from "@/lib/admin/i18n";
import { adminLang } from "@/lib/admin/server";
import { requireSession } from "@/lib/admin/session";
import type { AdminProductSummary } from "@/lib/admin/types";

export const metadata: Metadata = { title: "Products" };

const STATUSES = ["all", "active", "inactive"] as const;

export default async function ProductsPage({ searchParams }: { searchParams: Promise<{ q?: string; status?: string }> }) {
  await requireSession();
  const lang = await adminLang();
  const d = adminDict(lang);
  const sp = await searchParams;
  const q = (sp.q || "").slice(0, 80);
  const status = STATUSES.includes(sp.status as (typeof STATUSES)[number]) ? (sp.status as (typeof STATUSES)[number]) : "all";
  const data = await adminGet<{ items: AdminProductSummary[]; total: number }>(
    `/v1/admin/products?status=${status}${q ? `&q=${encodeURIComponent(q)}` : ""}`,
  );
  return (
    <>
      <div className="adm-head">
        <h1 className="h1">{d.products.title}</h1>
        <Link href="/admin/products/new" className="btn btn--red">{d.products.new}</Link>
      </div>
      <nav className="adm-tabs" aria-label={d.products.title}>
        {STATUSES.map((s) => (
          <Link key={s} className="adm-tab" href={`/admin/products?status=${s}${q ? `&q=${encodeURIComponent(q)}` : ""}`} aria-current={s === status ? "page" : undefined}>
            {d.products.filter[s]}
          </Link>
        ))}
      </nav>
      <form action="/admin/products" method="get" role="search" style={{ marginBottom: "calc(var(--st) * 2)", maxWidth: 520 }}>
        <input type="hidden" name="status" value={status} />
        <label className="sr-only" htmlFor="product-search">{d.common.search}</label>
        <input id="product-search" className="input" type="search" name="q" defaultValue={q} placeholder={d.products.searchPlaceholder} />
      </form>
      {data.items.length ? (
        <div className="adm-scroll">
          <table className="adm-table adm-table--stack" data-testid="product-table">
            <thead>
              <tr>
                <th scope="col"><span className="sr-only">Photo</span></th>
                <th scope="col">{d.products.cols.product}</th>
                <th scope="col">{d.products.cols.maker}</th>
                <th scope="col" className="num">{d.products.cols.price}</th>
                <th scope="col" className="num">{d.products.cols.variants}</th>
                <th scope="col" className="num">{d.products.cols.stock}</th>
                <th scope="col">{d.products.cols.status}</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((p) => (
                <tr key={p.id} data-slug={p.slug}>
                  <td>
                    {p.thumb ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img className="adm-thumb" src={p.thumb.src} alt="" />
                    ) : <span className="adm-thumb adm-thumb--none">{d.products.noPhoto}</span>}
                  </td>
                  <td className="wide">
                    <Link className="adm-link" href={`/admin/products/${p.id}`}>{pickLang(lang, p.title, p.title_uk)}</Link>
                    <span className="mono mono--sm muted" style={{ display: "block" }}>{p.slug}</span>
                  </td>
                  <td data-label={d.products.cols.maker}>{p.maker ? pickLang(lang, p.maker.name, p.maker.name_uk) : "—"}</td>
                  <td className="num" data-label={d.products.cols.price}>
                    {p.price_from_cad === null ? "—" : p.price_from_cad === p.price_to_cad ? adminMoney(p.price_from_cad) : `${adminMoney(p.price_from_cad)}–${Number(p.price_to_cad).toFixed(2)}`}
                  </td>
                  <td className="num" data-label={d.products.cols.variants}>{p.variant_count}</td>
                  <td className="num" data-label={d.products.cols.stock}>{p.available} / {p.on_hand}</td>
                  <td data-label={d.products.cols.status}>
                    <span className={`adm-status adm-status--${p.active ? "ok" : "wait"}`}>{p.active ? d.common.onSale : d.common.notOnSale}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="adm-empty">{d.products.empty}</p>
      )}
    </>
  );
}
