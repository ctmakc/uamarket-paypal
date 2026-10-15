import type { Metadata } from "next";
import PayPalDesk from "@/components/admin/PayPalDesk";
import { adminLang } from "@/lib/admin/server";
import { requireSession } from "@/lib/admin/session";

export const metadata: Metadata = { title: "PayPal desk" };

export default async function PayPalDeskPage() {
  await requireSession();
  const lang = await adminLang();
  return <PayPalDesk lang={lang} />;
}
