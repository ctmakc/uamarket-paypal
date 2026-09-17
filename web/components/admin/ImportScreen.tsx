"use client";

import { useState } from "react";
import { adminCall } from "@/lib/admin/client";
import { adminDict, type AdminLang } from "@/lib/admin/i18n";

type Report = {
  apply: boolean; applied: boolean; rows: number; errors: number; columns_missing: string[];
  products: { create: number; update: number }; variants: { create: number; update: number }; makers: { create: number }; activated: number;
  lines: { line: number; product_slug?: string; sku?: string; status: string; actions?: string[]; messages: string[] }[];
};

export default function ImportScreen({ lang }: { lang: AdminLang }) {
  const d = adminDict(lang);
  const t = d.import;
  const [text, setText] = useState<string | null>(null);
  const [name, setName] = useState<string>("");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(apply: boolean) {
    if (text === null) return;
    setBusy(true);
    setError(null);
    const r = await adminCall<Report>(`v1/admin/import${apply ? "?apply=true" : ""}`, { method: "POST", body: text, contentType: "text/csv; charset=utf-8", lang });
    setBusy(false);
    if (!r.ok) return setError(r.message);
    setReport(r.data);
  }

  return (
    <>
      <div className="adm-head">
        <div>
          <h1 className="h1">{t.title}</h1>
          <p className="muted measure" style={{ fontSize: "var(--fs-ui)" }}>{t.lede}</p>
        </div>
        <p className="adm-actions">
          <a className="adm-link" href="/admin/import/template.csv" download>{t.template}</a>
        </p>
      </div>
      <div className="adm-drop" style={{ marginBottom: "calc(var(--st) * 2)" }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={async (e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) { setName(f.name); setText(await f.text()); setReport(null); } }}>
        <label className="btn btn--ghost">
          {t.choose}
          <input className="sr-only" type="file" accept=".csv,text/csv" data-testid="import-file"
            onChange={async (e) => { const f = e.target.files?.[0]; if (f) { setName(f.name); setText(await f.text()); setReport(null); } }} />
        </label>
        <p className="mono mono--sm">{name}</p>
      </div>
      <div className="adm-actions">
        <button className="btn btn--ghost btn--lg" type="button" disabled={busy || text === null} onClick={() => run(false)} data-testid="import-check">{t.check}</button>
        <button className="btn btn--red btn--lg" type="button" disabled={busy || !report || report.apply || report.errors > 0} onClick={() => run(true)} data-testid="import-apply">{t.apply}</button>
      </div>
      {error ? <p className="adm-msg adm-msg--bad" role="alert">{error}</p> : null}
      {report ? (
        <section className="adm-section" style={{ marginTop: "calc(var(--st) * 3)" }} data-testid="import-report" data-errors={report.errors} data-applied={report.applied ? "true" : "false"}>
          <h2 className="adm-section__title">{t.report}</h2>
          <p className={`adm-msg adm-msg--${report.errors ? "bad" : "ok"}`} data-testid="import-summary">
            {t.summary(report)}{report.applied ? ` · ${t.applied}` : report.errors ? ` · ${t.fixFirst}` : ""}
          </p>
          <div className="adm-scroll">
            <table className="adm-table adm-table--stack">
              <thead><tr><th scope="col">{t.line}</th><th scope="col">SKU</th><th scope="col">{d.products.cols.product}</th><th scope="col">{d.products.cols.status}</th></tr></thead>
              <tbody>
                {report.lines.map((l) => (
                  <tr key={l.line}>
                    <td className="mono" data-label={t.line}>{l.line}</td>
                    <td className="mono" data-label="SKU">{l.sku}</td>
                    <td data-label={d.products.cols.product}>{l.product_slug}</td>
                    <td className="wide">
                      <span className={`adm-status adm-status--${l.status === "error" ? "bad" : "ok"}`}>{l.status === "error" ? l.messages.join("; ") : (l.actions || []).join(" · ")}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </>
  );
}
