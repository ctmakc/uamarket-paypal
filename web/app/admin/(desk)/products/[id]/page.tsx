import type { Metadata } from "next";
import { notFound } from "next/navigation";
import ProductEditor from "@/components/admin/ProductEditor";
import { AdminApiError, adminGet } from "@/lib/admin/api";
import { adminLang } from "@/lib/admin/server";
import { requireSession } from "@/lib/admin/session";
import type { AdminMaker, AdminProduct, Taxonomy } from "@/lib/admin/types";

export const metadata: Metadata = { title: "Product" };

export default async function EditProductPage({ params }: { params: Promise<{ id: string }> }) {
  await requireSession();
  const lang = await adminLang();
  const { id } = await params;
  let product: AdminProduct;
  try {
    product = await adminGet<AdminProduct>(`/v1/admin/products/${encodeURIComponent(id)}`);
  } catch (e) {
    if (e instanceof AdminApiError && e.status === 404) notFound();
    throw e;
  }
  const [taxonomy, makers] = await Promise.all([
    adminGet<Taxonomy>("/v1/admin/taxonomy"),
    adminGet<{ items: AdminMaker[] }>("/v1/admin/makers?status=all"),
  ]);
  return <ProductEditor lang={lang} taxonomy={taxonomy} makers={makers.items} initial={product} />;
}
