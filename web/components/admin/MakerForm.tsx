"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { adminCall } from "@/lib/admin/client";
import { adminDict, pickLang, type AdminLang } from "@/lib/admin/i18n";
import type { AdminMaker } from "@/lib/admin/types";

const PAIRS = ["name", "region", "craft", "story"] as const;

export default function MakerForm({ lang, initial }: { lang: AdminLang; initial: AdminMaker | null }) {
  const d = adminDict(lang);
  const m = d.makers;
  const router = useRouter();
  const [maker, setMaker] = useState<AdminMaker | null>(initial);
  const [msg, setMsg] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(ev: React.FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    const f = new FormData(ev.currentTarget);
    const body: Record<string, string> = {};
    f.forEach((v, k) => { body[k] = String(v); });
    if (!body.slug) delete body.slug;
    setBusy(true);
    const r = maker
      ? await adminCall<AdminMaker>(`v1/admin/makers/${maker.id}`, { method: "PATCH", json: body, lang })
      : await adminCall<AdminMaker>("v1/admin/makers", { method: "POST", json: body, lang });
    setBusy(false);
    if (!r.ok) return setMsg({ tone: "bad", text: r.message });
    setMsg({ tone: "ok", text: d.common.saved });
    setMaker(r.data);
    if (!maker) router.replace(`/admin/makers/${r.data.id}`);
  }

  async function toggle() {
    if (!maker) return;
    const r = await adminCall<AdminMaker>(`v1/admin/makers/${maker.id}/${maker.active ? "retire" : "unretire"}`, { method: "POST", json: {}, lang });
    if (r.ok) setMaker(r.data); else setMsg({ tone: "bad", text: r.message });
  }

  return (
    <>
      <Link href="/admin/makers" className="adm-crumb">← {m.title}</Link>
      <div className="adm-head">
        <h1 className="h1">{maker ? pickLang(lang, maker.name, maker.name_uk) : m.new}</h1>
        {maker ? (
          <div className="adm-actions">
            <span className={`adm-status adm-status--${maker.active ? "ok" : "quiet"}`}>{maker.active ? d.common.active : d.common.retired}</span>
            <button className="btn btn--ghost" type="button" onClick={toggle}>{maker.active ? d.common.retire : d.common.unretire}</button>
          </div>
        ) : null}
      </div>
      <form onSubmit={submit} data-testid="maker-form" key={maker?.id || "new"}>
        <div className="adm-grid2 adm-sheet">
          {(["en", "uk"] as const).map((l) => (
            <div key={l} className="adm-lang-col" lang={l}>
              <p className="adm-lang-col__head">{l === "uk" ? d.common.uk : d.common.en}</p>
              {PAIRS.map((key) => {
                const name = l === "uk" ? `${key}_uk` : key;
                const value = maker ? ((maker as unknown as Record<string, string | null>)[name] ?? "") : "";
                return (
                  <label key={name} className="field">
                    <span className="field__label">{m.fields[key]}{key === "name" && l === "en" ? ` · ${d.common.required}` : ""}</span>
                    {key === "story" ? <textarea className="textarea" name={name} defaultValue={value} rows={5} /> : <input className="input" name={name} defaultValue={value} required={key === "name" && l === "en"} maxLength={200} />}
                  </label>
                );
              })}
            </div>
          ))}
        </div>
        <div className="adm-grid3 adm-sheet" style={{ marginTop: "var(--st)" }}>
          <label className="field"><span className="field__label">{m.fields.country}</span><input className="input mono" name="country" defaultValue={maker?.country || "UA"} maxLength={2} pattern="[A-Za-z]{2}" /></label>
          <label className="field"><span className="field__label">{m.fields.founded_year}</span><input className="input mono" name="founded_year" defaultValue={maker?.founded_year ?? ""} inputMode="numeric" /></label>
          <label className="field"><span className="field__label">{m.fields.slug}</span><input className="input mono" name="slug" defaultValue={maker?.slug || ""} pattern="[a-z0-9]+(-[a-z0-9]+)*" /></label>
        </div>
        <div className="adm-actions" style={{ marginTop: "calc(var(--st) * 2)" }}>
          <button className="btn btn--red btn--lg" type="submit" disabled={busy} data-testid="save-maker">{maker ? d.common.save : m.create}</button>
          <span className={`adm-msg adm-msg--${msg?.tone || "ok"}`} role="status" aria-live="polite">{msg?.text}</span>
        </div>
      </form>
    </>
  );
}
