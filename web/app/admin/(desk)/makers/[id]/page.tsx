import type { Metadata } from "next";
import { notFound } from "next/navigation";
import MakerForm from "@/components/admin/MakerForm";
import { AdminApiError, adminGet } from "@/lib/admin/api";
import { adminLang } from "@/lib/admin/server";
import { requireSession } from "@/lib/admin/session";
import type { AdminMaker } from "@/lib/admin/types";

export const metadata: Metadata = { title: "Maker" };

export default async function MakerPage({ params }: { params: Promise<{ id: string }> }) {
  await requireSession();
  const { id } = await params;
  let maker: AdminMaker;
  try {
    maker = await adminGet<AdminMaker>(`/v1/admin/makers/${encodeURIComponent(id)}`);
  } catch (e) {
    if (e instanceof AdminApiError && e.status === 404) notFound();
    throw e;
  }
  return <MakerForm lang={await adminLang()} initial={maker} />;
}
