import type { Metadata } from "next";
import "../globals.css";
import "./admin.css";
import { adminLang } from "@/lib/admin/server";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: { default: "Admin · UA Market", template: "%s · Admin · UA Market" },
  robots: { index: false, follow: false, nocache: true, googleBot: { index: false, follow: false } },
  referrer: "same-origin",
};

export default async function AdminRootLayout({ children }: { children: React.ReactNode }) {
  const lang = await adminLang();
  return (
    <html lang={lang === "uk" ? "uk" : "en-CA"}>
      <body>{children}</body>
    </html>
  );
}
