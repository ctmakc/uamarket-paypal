import type { Metadata } from "next";
import { notFound } from "next/navigation";
import OrderWorkbench from "@/components/admin/OrderWorkbench";
import { AdminApiError, adminGet } from "@/lib/admin/api";
import { adminLang } from "@/lib/admin/server";
import { requireSession } from "@/lib/admin/session";
import type { OrderDetail } from "@/lib/admin/types";

export const metadata: Metadata = { title: "Order" };

export default async function OrderPage({ params }: { params: Promise<{ id: string }> }) {
  await requireSession();
  const lang = await adminLang();
  const { id } = await params;
  let order: OrderDetail;
  try {
    order = await adminGet<OrderDetail>(`/v1/admin/orders/${encodeURIComponent(id)}`);
  } catch (e) {
    if (e instanceof AdminApiError && e.status === 404) notFound();
    throw e;
  }
  return <OrderWorkbench initial={order} lang={lang} />;
}
