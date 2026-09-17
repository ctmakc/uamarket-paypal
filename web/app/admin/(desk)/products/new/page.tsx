import type { Metadata } from "next";
import ProductEditor from "@/components/admin/ProductEditor";
import { adminGet } from "@/lib/admin/api";
import { adminLang } from "@/lib/admin/server";
import { requireSession } from "@/lib/admin/session";
import type { AdminMaker, Taxonomy } from "@/lib/admin/types";

export const metadata: Metadata = { title: "New product" };

export default async function NewProductPage() {
  await requireSession();
  const lang = await adminLang();
  const [taxonomy, makers] = await Promise.all([
    adminGet<Taxonomy>("/v1/admin/taxonomy"),
    adminGet<{ items: AdminMaker[] }>("/v1/admin/makers?status=all"),
  ]);
  return <ProductEditor lang={lang} taxonomy={taxonomy} makers={makers.items} initial={null} />;
}
