import AdminNav from "@/components/admin/AdminNav";
import { adminDict } from "@/lib/admin/i18n";
import { adminLang } from "@/lib/admin/server";
import { requireSession } from "@/lib/admin/session";
import { catalogueStatus } from "@/lib/geo";

export default async function DeskLayout({ children }: { children: React.ReactNode }) {
  const session = await requireSession();
  const lang = await adminLang();
  const d = adminDict(lang);
  return (
    <div className="adm">
      {/* Read by lib/admin/client.ts and sent back as x-csrf-token on every write. */}
      <meta name="admin-csrf" content={session.csrf} />
      <AdminNav lang={lang} />
      {catalogueStatus() === "placeholder" ? (
        <div className="adm-demo"><div className="adm-wrap">{d.queue.demoNote}</div></div>
      ) : <div />}
      <main id="main" className="adm-main adm-wrap">{children}</main>
    </div>
  );
}
