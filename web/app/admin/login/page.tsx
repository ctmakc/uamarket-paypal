import type { Metadata } from "next";
import { redirect } from "next/navigation";
import LoginForm from "@/components/admin/LoginForm";
import { adminDict } from "@/lib/admin/i18n";
import { adminLang } from "@/lib/admin/server";
import { adminConfig, currentSession } from "@/lib/admin/session";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage() {
  if (await currentSession()) redirect("/admin");
  const lang = await adminLang();
  const d = adminDict(lang);
  const cfg = adminConfig();
  return (
    <main className="adm adm-login">
      <div className="adm-login__card">
        <div className="adm-login__plate">
          <p className="mono mono--sm" style={{ color: "var(--muted-on-plate)" }}>{d.brand} · {d.admin}</p>
          <h1 className="display">{d.login.title}</h1>
          <p style={{ color: "var(--muted-on-plate)", marginTop: "var(--st)" }}>{d.login.lede}</p>
        </div>
        {cfg.ok ? (
          <LoginForm lang={lang} />
        ) : (
          <div className="adm-login__form">
            <p className="error">{d.login.notConfigured}</p>
            <p className="ui">{d.login.missing} <span className="mono">{cfg.missing.join(", ")}</span></p>
            <p className="mono mono--sm muted">{d.login.howTo}</p>
          </div>
        )}
        <a className="adm-link" href={`/admin/api/lang?to=${lang === "uk" ? "en" : "uk"}&back=/admin/login`} lang={lang === "uk" ? "en" : "uk"}>
          {d.langSwitch}
        </a>
      </div>
    </main>
  );
}
