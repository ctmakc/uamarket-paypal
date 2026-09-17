import type { Metadata } from "next";
import ImportScreen from "@/components/admin/ImportScreen";
import { adminLang } from "@/lib/admin/server";
import { requireSession } from "@/lib/admin/session";

export const metadata: Metadata = { title: "Import" };

export default async function ImportPage() {
  await requireSession();
  return <ImportScreen lang={await adminLang()} />;
}
