import type { Metadata } from "next";
import StockScreen from "@/components/admin/StockScreen";
import { adminGet } from "@/lib/admin/api";
import { adminLang } from "@/lib/admin/server";
import { requireSession } from "@/lib/admin/session";
import type { StockCell, Taxonomy } from "@/lib/admin/types";

export const metadata: Metadata = { title: "Stock" };

export type StockItem = StockCell & {
  variant_id: string; sku: string; barcode: string; label: string | null; label_uk: string | null; product_id: string | null;
  product_title: string; product_title_uk: string | null; product_active: boolean; variant_active: boolean;
};

export default async function StockPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  await requireSession();
  const lang = await adminLang();
  const q = ((await searchParams).q || "").slice(0, 80);
  const [data, taxonomy] = await Promise.all([
    adminGet<{ items: StockItem[] }>(`/v1/admin/stock${q ? `?q=${encodeURIComponent(q)}` : ""}`),
    adminGet<Taxonomy>("/v1/admin/taxonomy"),
  ]);
  return <StockScreen lang={lang} q={q} items={data.items} taxonomy={taxonomy} />;
}
