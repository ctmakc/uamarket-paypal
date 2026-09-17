import type { Metadata } from "next";
import MakerForm from "@/components/admin/MakerForm";
import { adminLang } from "@/lib/admin/server";
import { requireSession } from "@/lib/admin/session";

export const metadata: Metadata = { title: "New maker" };

export default async function NewMakerPage() {
  await requireSession();
  return <MakerForm lang={await adminLang()} initial={null} />;
}
