"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { adminCall } from "@/lib/admin/client";
import { adminDict, adminMoney, pickLang, type AdminLang } from "@/lib/admin/i18n";
import type { AdminMaker, AdminProduct, AdminVariant, Photo, SizeChart, Taxonomy } from "@/lib/admin/types";

type Msg = { tone: "ok" | "bad"; text: string } | null;

const MAX_BYTES = 15 * 1024 * 1024;
const PHOTO_TYPES = /\.(jpe?g|png|webp)$/i;
const TEXT_FIELDS = ["title", "subtitle", "description", "origin_note", "technique", "material", "care"] as const;
const LONG = new Set(["description"]);

export default function ProductEditor({ lang, taxonomy, makers, initial }: { lang: AdminLang; taxonomy: Taxonomy; makers: AdminMaker[]; initial: AdminProduct | null }) {
  const d = adminDict(lang);
  const e = d.editor;
  const router = useRouter();
  const [product, setProduct] = useState<AdminProduct | null>(initial);
  const [msg, setMsg] = useState<Msg>(null);
  const [busy, setBusy] = useState(false);

  async function reload() {
    if (!product) return;
    const r = await adminCall<AdminProduct>(`v1/admin/products/${product.id}`, { lang });
    if (r.ok) setProduct(r.data);
  }

  async function saveMain(ev: React.FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    const f = new FormData(ev.currentTarget);
    const body: Record<string, unknown> = {};
    for (const key of TEXT_FIELDS) {
      body[key] = String(f.get(key) || "");
      body[`${key}_uk`] = String(f.get(`${key}_uk`) || "");
    }
    for (const key of ["slug", "category", "collection", "origin", "maker_id"]) body[key] = String(f.get(key) || "");
    body.featured = f.get("featured") === "on";
    if (!body.slug) delete body.slug;
    setBusy(true);
    setMsg(null);
    const r = product
      ? await adminCall<AdminProduct>(`v1/admin/products/${product.id}`, { method: "PATCH", json: body, lang })
      : await adminCall<AdminProduct>("v1/admin/products", { method: "POST", json: body, lang });
    setBusy(false);
    if (!r.ok) {
      setMsg({ tone: "bad", text: r.message });
      return;
    }
    setMsg({ tone: "ok", text: d.common.saved });
    if (!product) {
      router.replace(`/admin/products/${r.data.id}`);
    }
    setProduct(r.data);
  }

  async function setOnSale(on: boolean) {
    if (!product) return;
    setBusy(true);
    setMsg(null);
    const r = await adminCall<AdminProduct>(`v1/admin/products/${product.id}/${on ? "activate" : "retire"}`, { method: "POST", json: {}, lang });
    setBusy(false);
    if (r.ok) {
      setProduct(r.data);
      setMsg({ tone: "ok", text: on ? d.common.onSale : d.common.notOnSale });
    } else {
      setMsg({ tone: "bad", text: r.message });
      await reload();
    }
  }

  const p = product;
  return (
    <div className="adm-editor" data-product-id={p?.id || ""}>
      <Link href="/admin/products" className="adm-crumb">← {d.products.title}</Link>
      <div className="adm-head">
        <div>
          <h1 className="h1">{p ? pickLang(lang, p.title, p.title_uk) : e.newTitle}</h1>
          {p ? <p className="mono mono--sm muted">{p.slug}</p> : null}
        </div>
        {p ? (
          <div className="adm-actions">
            <span className={`adm-status adm-status--${p.active ? "ok" : "wait"}`} data-testid="product-status">{p.active ? d.common.onSale : d.common.notOnSale}</span>
            {p.active ? (
              <button className="btn btn--ghost" type="button" disabled={busy} onClick={() => setOnSale(false)}>{e.takeOff}</button>
            ) : (
              <button className="btn btn--red" type="button" disabled={busy} onClick={() => setOnSale(true)} data-testid="put-on-sale">{e.putOnSale}</button>
            )}
            {p.active ? (
              <a className="adm-link" href={`${lang === "uk" ? "/uk" : ""}/product/${p.slug}`} target="_blank" rel="noopener">{e.preview} ↗</a>
            ) : <span className="mono mono--sm muted">{e.previewHidden}</span>}
          </div>
        ) : null}
      </div>
      <p className={`adm-msg adm-msg--${msg?.tone || "ok"}`} role="status" aria-live="polite" data-testid="editor-msg">{msg?.text}</p>

      {p && !p.active && p.problems.length ? (
        <div className="adm-problems" data-testid="problems">
          <p className="ui">{e.problemsTitle}</p>
          <ul>{p.problems.map((x, i) => <li key={`${x.code}-${i}`}>{lang === "uk" ? x.message_uk : x.message}</li>)}</ul>
          <p className="mono mono--sm muted">{p.catalogue_live ? e.liveNote : e.placeholderNote}</p>
        </div>
      ) : null}

      <form onSubmit={saveMain} className="adm-section" style={{ marginTop: "calc(var(--st) * 2)" }} data-testid="product-form" key={p?.id || "new"}>
        <h2 className="adm-section__title">{e.text}</h2>
        <div className="adm-grid2 adm-sheet">
          {(["en", "uk"] as const).map((l) => (
            <div key={l} className="adm-lang-col" lang={l === "uk" ? "uk" : "en"}>
              <p className="adm-lang-col__head">{l === "uk" ? d.common.uk : d.common.en}</p>
              {TEXT_FIELDS.map((key) => {
                const name = l === "uk" ? `${key}_uk` : key;
                const value = p ? ((p as unknown as Record<string, string | null>)[name] ?? "") : "";
                return (
                  <label key={name} className="field">
                    <span className="field__label">{e.fields[key]}{key === "title" && l === "en" ? ` · ${d.common.required}` : ""}</span>
                    {LONG.has(key) ? (
                      <textarea className="textarea" name={name} defaultValue={value} rows={5} maxLength={10000} />
                    ) : (
                      <input className="input" name={name} defaultValue={value} maxLength={key === "care" ? 400 : 240} required={key === "title" && l === "en"} />
                    )}
                  </label>
                );
              })}
            </div>
          ))}
        </div>
        <h2 className="adm-section__title" style={{ marginTop: "calc(var(--st) * 2)" }}>{e.facts}</h2>
        <div className="adm-sheet adm-grid3">
          <label className="field"><span className="field__label">{e.fields.category}</span>
            <select className="select" name="category" defaultValue={p?.category || ""} required>
              <option value="" disabled>—</option>
              {taxonomy.categories.map((c) => <option key={c.slug} value={c.slug}>{pickLang(lang, c.title, c.title_uk)}</option>)}
            </select></label>
          <label className="field"><span className="field__label">{e.fields.collection}</span>
            <select className="select" name="collection" defaultValue={p?.collection || ""} required>
              <option value="" disabled>—</option>
              {taxonomy.collections.map((c) => <option key={c.slug} value={c.slug}>{pickLang(lang, c.title, c.title_uk)}</option>)}
            </select></label>
          <label className="field"><span className="field__label">{e.fields.origin}</span>
            <select className="select" name="origin" defaultValue={p?.origin || "MADE_UA"}>
              {taxonomy.origins.map((o) => <option key={o.id} value={o.id}>{pickLang(lang, o.label, o.label_uk)}</option>)}
            </select></label>
          <label className="field"><span className="field__label">{e.fields.maker}</span>
            <select className="select" name="maker_id" defaultValue={p?.maker?.id || ""}>
              <option value="">—</option>
              {makers.map((m) => <option key={m.id} value={m.id}>{pickLang(lang, m.name, m.name_uk)}{m.active ? "" : ` (${d.common.retired})`}</option>)}
            </select></label>
          <label className="field"><span className="field__label">{e.fields.slug}</span>
            <input className="input mono" name="slug" defaultValue={p?.slug || ""} pattern="[a-z0-9]+(-[a-z0-9]+)*" maxLength={120} />
            <span className="field__hint">{e.slugHint}</span></label>
          <label className="adm-check"><input type="checkbox" name="featured" defaultChecked={p?.featured} /> {e.fields.featured}</label>
        </div>
        <div className="adm-actions" style={{ marginTop: "calc(var(--st) * 2)" }}>
          <button className="btn btn--red btn--lg" type="submit" disabled={busy} data-testid="save-product">{p ? d.common.save : e.create}</button>
        </div>
      </form>

      {p ? (
        <>
          <Variants product={p} lang={lang} onChange={setProduct} />
          <Photos product={p} lang={lang} reload={reload} />
          <SizeChartEditor product={p} lang={lang} onChange={setProduct} garment={Boolean(taxonomy.categories.find((c) => c.slug === p.category)?.garment)} />
        </>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------ variants

function Variants({ product, lang, onChange }: { product: AdminProduct; lang: AdminLang; onChange: (p: AdminProduct) => void }) {
  const d = adminDict(lang);
  const e = d.editor;
  const [msg, setMsg] = useState<Msg>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function send(path: string, method: string, json: unknown, form?: HTMLFormElement) {
    setBusy(true);
    setMsg(null);
    const r = await adminCall<AdminProduct & { ok?: boolean }>(path, { method, json, lang });
    setBusy(false);
    if (!r.ok) {
      setMsg({ tone: "bad", text: r.message });
      return false;
    }
    if (r.data && (r.data as AdminProduct).variants) onChange(r.data as AdminProduct);
    else {
      const again = await adminCall<AdminProduct>(`v1/admin/products/${product.id}`, { lang });
      if (again.ok) onChange(again.data);
    }
    form?.reset();
    setMsg({ tone: "ok", text: d.common.saved });
    return true;
  }

  function values(form: HTMLFormElement): Record<string, string> {
    const out: Record<string, string> = {};
    new FormData(form).forEach((v, k) => { out[k] = String(v); });
    return out;
  }

  return (
    <section className="adm-section" style={{ marginTop: "calc(var(--st) * 4)" }} data-testid="variants">
      <h2 className="adm-section__title">{e.variants}</h2>
      {product.variants.length ? (
        <div className="adm-scroll">
          <table className="adm-table adm-table--stack">
            <thead>
              <tr>
                <th scope="col">{e.variantCols.sku}</th>
                <th scope="col">{e.variantCols.label}</th>
                <th scope="col">{e.variantCols.labelUk}</th>
                <th scope="col" className="num">{e.variantCols.price}</th>
                <th scope="col" className="num">{e.variantCols.weight}</th>
                <th scope="col" className="num">{e.variantCols.stock}</th>
                <th scope="col"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {product.variants.map((v) => (
                <VariantRow key={v.id} v={v} lang={lang} open={open === v.id} busy={busy}
                  toggle={() => setOpen(open === v.id ? null : v.id)}
                  save={(form) => send(`v1/admin/variants/${v.id}`, "PATCH", values(form))}
                  retire={() => send(`v1/admin/variants/${v.id}/${v.active ? "retire" : "unretire"}`, "POST", {})}
                  receive={(qty, form) => send("v1/admin/stock/receive", "POST", { sku: v.sku, qty }, form)} />
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <form className="adm-sheet" data-testid="add-variant" onSubmit={async (ev) => {
        ev.preventDefault();
        const form = ev.currentTarget;
        await send(`v1/admin/products/${product.id}/variants`, "POST", values(form), form);
      }}>
        <p className="ui">{e.addVariant}</p>
        <div className="adm-grid4">
          <label className="field"><span className="field__label">{e.variantCols.label}</span><input className="input" name="option_label" maxLength={120} required /></label>
          <label className="field"><span className="field__label">{e.variantCols.labelUk}</span><input className="input" name="option_label_uk" maxLength={120} /></label>
          <label className="field"><span className="field__label">{e.variantCols.price}</span><input className="input mono" name="price_cad" inputMode="decimal" pattern="[0-9]+([.,][0-9]{1,2})?" required /></label>
          <label className="field"><span className="field__label">{e.variantCols.weight}</span><input className="input mono" name="weight_g" type="number" min={1} inputMode="numeric" /></label>
          <label className="field"><span className="field__label">{e.variantCols.sku}</span><input className="input mono" name="sku" maxLength={80} style={{ textTransform: "uppercase" }} /></label>
          <label className="field"><span className="field__label">{e.variantCols.barcode}</span><input className="input mono" name="barcode" maxLength={120} /></label>
        </div>
        <p className="field__hint">{e.autoFill}</p>
        <button className="btn btn--ghost" type="submit" disabled={busy}>{e.addVariant}</button>
      </form>
      <p className={`adm-msg adm-msg--${msg?.tone || "ok"}`} role="status" aria-live="polite">{msg?.text}</p>
    </section>
  );
}

function VariantRow({ v, lang, open, busy, toggle, save, retire, receive }: {
  v: AdminVariant; lang: AdminLang; open: boolean; busy: boolean; toggle: () => void;
  save: (form: HTMLFormElement) => Promise<boolean>; retire: () => void; receive: (qty: number, form: HTMLFormElement) => Promise<boolean>;
}) {
  const d = adminDict(lang);
  const e = d.editor;
  return (
    <>
      <tr data-retired={v.active ? undefined : "true"} data-sku={v.sku}>
        <td className="mono wide">{v.sku}<span className="mono mono--sm muted" style={{ display: "block" }}>{v.barcode}</span></td>
        <td data-label={e.variantCols.label}>{v.option_label || "—"}</td>
        <td data-label={e.variantCols.labelUk} lang="uk">{v.option_label_uk || "—"}</td>
        <td className="num" data-label={e.variantCols.price}>{adminMoney(v.price_cad)}</td>
        <td className="num" data-label={e.variantCols.weight}>{v.weight_g ?? "—"}</td>
        <td className="num" data-label={e.variantCols.stock} data-testid="variant-stock">{v.stock.available} / {v.stock.on_hand}</td>
        <td className="wide">
          <span className="adm-actions" style={{ gap: "var(--st)" }}>
            <button className="adm-link" type="button" onClick={toggle} aria-expanded={open}>{d.common.edit}</button>
            <button className="adm-link" type="button" onClick={retire} disabled={busy}>{v.active ? d.common.retire : d.common.unretire}</button>
          </span>
        </td>
      </tr>
      {open ? (
        <tr>
          <td colSpan={7} className="wide" style={{ background: "var(--linen-shade)" }}>
            <form onSubmit={async (ev) => { ev.preventDefault(); if (await save(ev.currentTarget)) toggle(); }} style={{ padding: "var(--st) 0", display: "grid", gap: "var(--st)" }}>
              <div className="adm-grid4">
                <label className="field"><span className="field__label">{e.variantCols.label}</span><input className="input" name="option_label" defaultValue={v.option_label || ""} /></label>
                <label className="field"><span className="field__label">{e.variantCols.labelUk}</span><input className="input" name="option_label_uk" defaultValue={v.option_label_uk || ""} /></label>
                <label className="field"><span className="field__label">{e.variantCols.price}</span><input className="input mono" name="price_cad" defaultValue={v.price_cad.toFixed(2)} inputMode="decimal" /></label>
                <label className="field"><span className="field__label">{e.variantCols.weight}</span><input className="input mono" name="weight_g" defaultValue={v.weight_g ?? ""} inputMode="numeric" /></label>
                <label className="field"><span className="field__label">{e.variantMore.cost}</span><input className="input mono" name="cost_cad" defaultValue={v.cost_cad?.toFixed(2) ?? ""} inputMode="decimal" /></label>
                <label className="field"><span className="field__label">{e.variantCols.barcode}</span><input className="input mono" name="barcode" defaultValue={v.barcode} /></label>
                <label className="field"><span className="field__label">{e.variantMore.fibre}</span><input className="input" name="fibre_content" defaultValue={v.fibre_content || ""} /></label>
                <label className="field"><span className="field__label">{e.variantMore.country}</span><input className="input mono" name="country_of_origin" defaultValue={v.country_of_origin || ""} maxLength={2} /></label>
                <label className="field"><span className="field__label">{e.variantMore.hs}</span><input className="input mono" name="hs_code" defaultValue={v.hs_code || ""} maxLength={13} /></label>
                <label className="field"><span className="field__label">{e.variantMore.dims} · L</span><input className="input mono" name="length_cm" defaultValue={v.length_cm ?? ""} inputMode="decimal" /></label>
                <label className="field"><span className="field__label">W</span><input className="input mono" name="width_cm" defaultValue={v.width_cm ?? ""} inputMode="decimal" /></label>
                <label className="field"><span className="field__label">H</span><input className="input mono" name="height_cm" defaultValue={v.height_cm ?? ""} inputMode="decimal" /></label>
              </div>
              <div className="adm-actions"><button className="btn btn--red" type="submit" disabled={busy}>{d.common.save}</button></div>
            </form>
            <form className="adm-actions" onSubmit={async (ev) => { ev.preventDefault(); const qty = Number(new FormData(ev.currentTarget).get("qty")); if (qty > 0) await receive(qty, ev.currentTarget); }}>
              <label className="field"><span className="field__label">{e.receive} · {d.stock.qty}</span><input className="input mono" name="qty" type="number" min={1} max={100000} inputMode="numeric" required data-testid="receive-qty" /></label>
              <button className="btn btn--ghost" type="submit" disabled={busy}>{d.stock.receiveButton}</button>
            </form>
          </td>
        </tr>
      ) : null}
    </>
  );
}

// ------------------------------------------------------------------ photos

function Photos({ product, lang, reload }: { product: AdminProduct; lang: AdminLang; reload: () => Promise<void> }) {
  const d = adminDict(lang);
  const e = d.editor;
  const [over, setOver] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  async function upload(files: FileList | File[]) {
    const list = Array.from(files);
    const out: Msg[] = [];
    for (const file of list) {
      if (!PHOTO_TYPES.test(file.name)) {
        out.push({ tone: "bad", text: e.badType(file.name) });
        continue;
      }
      if (file.size > MAX_BYTES) {
        out.push({ tone: "bad", text: e.tooBig(file.name, (file.size / 1048576).toFixed(1)) });
        continue;
      }
      setStatus(e.uploading(file.name));
      const form = new FormData();
      form.append("file", file, file.name);
      const r = await adminCall<Photo>(`v1/admin/products/${product.id}/images`, { form, lang });
      if (!r.ok) out.push({ tone: "bad", text: `${file.name}: ${r.message}` });
    }
    setStatus(null);
    setMsgs(out);
    if (input.current) input.current.value = "";
    await reload();
  }

  async function move(index: number, delta: number) {
    const ids = product.images.map((i) => i.id);
    const j = index + delta;
    if (j < 0 || j >= ids.length) return;
    [ids[index], ids[j]] = [ids[j], ids[index]];
    await adminCall(`v1/admin/products/${product.id}/images/order`, { json: { ids }, lang });
    await reload();
  }

  return (
    <section className="adm-section" style={{ marginTop: "calc(var(--st) * 4)" }} data-testid="photos">
      <h2 className="adm-section__title">{e.photos}</h2>
      <div
        className="adm-drop"
        data-over={over ? "true" : undefined}
        onDragOver={(ev) => { ev.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(ev) => { ev.preventDefault(); setOver(false); if (ev.dataTransfer.files.length) upload(ev.dataTransfer.files); }}
      >
        <p className="ui">{e.drop}</p>
        <p className="field__hint">{e.dropHint}</p>
        <label className="btn btn--ghost">
          {e.choose}
          <input ref={input} className="sr-only" type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" multiple
            onChange={(ev) => ev.target.files && ev.target.files.length && upload(ev.target.files)} data-testid="photo-input" />
        </label>
        <p className="mono mono--sm" role="status" aria-live="polite">{status}</p>
      </div>
      {msgs.map((m, i) => m ? <p key={i} className={`adm-msg adm-msg--${m.tone}`} role="alert" data-testid="photo-error">{m.text}</p> : null)}
      <div className="adm-photos">
        {product.images.map((img, i) => (
          <PhotoRow key={img.id} img={img} index={i} count={product.images.length} lang={lang} move={move} reload={reload} />
        ))}
      </div>
    </section>
  );
}

function PhotoRow({ img, index, count, lang, move, reload }: { img: Photo; index: number; count: number; lang: AdminLang; move: (i: number, d: number) => void; reload: () => Promise<void> }) {
  const d = adminDict(lang);
  const e = d.editor;
  const [msg, setMsg] = useState<Msg>(null);
  return (
    <form className="adm-photo" data-testid="photo-row" onSubmit={async (ev) => {
      ev.preventDefault();
      const f = new FormData(ev.currentTarget);
      const r = await adminCall(`v1/admin/images/${img.id}`, { method: "PATCH", json: { alt_en: f.get("alt_en"), alt_uk: f.get("alt_uk") }, lang });
      setMsg(r.ok ? { tone: "ok", text: d.common.saved } : { tone: "bad", text: r.message });
      if (r.ok) await reload();
    }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={img.src} srcSet={img.srcset} sizes="120px" alt={pickLang(lang, img.alt, img.alt_uk)} width={120} height={120} />
      <div style={{ display: "grid", gap: "var(--st)" }}>
        <p className="adm-photo__n">{index + 1} / {count} · {img.width}×{img.height}</p>
        <div className="adm-grid2">
          <label className="field"><span className="field__label">{e.altEn}</span><input className="input" name="alt_en" defaultValue={img.alt} maxLength={300} /></label>
          <label className="field"><span className="field__label">{e.altUk}</span><input className="input" name="alt_uk" defaultValue={img.alt_uk} maxLength={300} lang="uk" /></label>
        </div>
        <div className="adm-actions" style={{ gap: "var(--st)" }}>
          <button className="btn btn--ghost" type="submit">{d.common.save}</button>
          <button className="adm-link" type="button" onClick={() => move(index, -1)} disabled={index === 0}>↑ {e.moveUp}</button>
          <button className="adm-link" type="button" onClick={() => move(index, 1)} disabled={index === count - 1}>↓ {e.moveDown}</button>
          <button className="adm-link" type="button" onClick={async () => { await adminCall(`v1/admin/images/${img.id}`, { method: "DELETE", lang }); await reload(); }}>{d.common.delete}</button>
          <span className={`adm-msg adm-msg--${msg?.tone || "ok"}`}>{msg?.text}</span>
        </div>
      </div>
    </form>
  );
}

// ------------------------------------------------------------------ size chart

function SizeChartEditor({ product, lang, onChange, garment }: { product: AdminProduct; lang: AdminLang; onChange: (p: AdminProduct) => void; garment: boolean }) {
  const d = adminDict(lang);
  const e = d.editor;
  const start: SizeChart = product.size_chart || { unit: "cm", rows: {} };
  const [unit, setUnit] = useState<"cm" | "in">(start.unit === "in" ? "in" : "cm");
  const [sizes, setSizes] = useState<string[]>(Object.keys(start.rows));
  const [measures, setMeasures] = useState<string[]>(() => {
    const set = new Set<string>();
    Object.values(start.rows).forEach((r) => Object.keys(r).forEach((k) => set.add(k)));
    return set.size ? [...set] : ["chest", "length"];
  });
  const [cells, setCells] = useState<Record<string, Record<string, string>>>(start.rows);
  const [msg, setMsg] = useState<Msg>(null);
  const [open, setOpen] = useState(garment || Boolean(product.size_chart));

  if (!open) {
    return (
      <section className="adm-section" style={{ marginTop: "calc(var(--st) * 4)" }}>
        <button className="adm-link" type="button" onClick={() => setOpen(true)}>{e.sizeChart} +</button>
      </section>
    );
  }
  async function save() {
    const rows: Record<string, Record<string, string>> = {};
    for (const s of sizes) {
      const row: Record<string, string> = {};
      for (const m of measures) if (cells[s]?.[m]?.trim()) row[m] = cells[s][m].trim();
      if (s.trim() && Object.keys(row).length) rows[s.trim()] = row;
    }
    const r = await adminCall<AdminProduct>(`v1/admin/products/${product.id}`, { method: "PATCH", json: { size_chart: Object.keys(rows).length ? { unit, rows } : null }, lang });
    if (r.ok) { onChange(r.data); setMsg({ tone: "ok", text: d.common.saved }); } else setMsg({ tone: "bad", text: r.message });
  }
  return (
    <section className="adm-section" style={{ marginTop: "calc(var(--st) * 4)" }} data-testid="size-chart">
      <h2 className="adm-section__title">{e.sizeChart}</h2>
      <p className="muted" style={{ fontSize: "var(--fs-ui)" }}>{e.sizeChartLede}{!product.size_chart && product.size_chart_effective ? ` ${e.sizeChartUsingDefault}` : ""}</p>
      <div className="adm-sheet adm-scroll">
        <table className="adm-table">
          <thead>
            <tr>
              <th scope="col">{e.size}</th>
              {measures.map((m, i) => (
                <th key={i} scope="col">
                  <input className="input mono" aria-label={e.measure} value={m} onChange={(ev) => setMeasures(measures.map((x, j) => (j === i ? ev.target.value : x)))} style={{ minWidth: 96 }} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sizes.map((s, i) => (
              <tr key={i}>
                <td><input className="input mono" aria-label={e.size} value={s} style={{ minWidth: 64 }} onChange={(ev) => {
                  const next = ev.target.value;
                  setCells((c) => { const copy = { ...c }; copy[next] = copy[s] || {}; if (next !== s) delete copy[s]; return copy; });
                  setSizes(sizes.map((x, j) => (j === i ? next : x)));
                }} /></td>
                {measures.map((m) => (
                  <td key={m}><input className="input mono" aria-label={`${s} ${m}`} value={cells[s]?.[m] || ""} style={{ minWidth: 72 }}
                    onChange={(ev) => setCells((c) => ({ ...c, [s]: { ...(c[s] || {}), [m]: ev.target.value } }))} /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="adm-actions">
        <button className="adm-link" type="button" onClick={() => setSizes([...sizes, ""])}>+ {e.addSize}</button>
        <button className="adm-link" type="button" onClick={() => setMeasures([...measures, ""])}>+ {e.addMeasure}</button>
        <label className="adm-check">{e.unit}
          <select className="select" value={unit} onChange={(ev) => setUnit(ev.target.value === "in" ? "in" : "cm")} style={{ width: 96 }}>
            <option value="cm">cm</option><option value="in">in</option>
          </select></label>
        <button className="btn btn--ghost" type="button" onClick={save}>{d.common.save}</button>
        <span className={`adm-msg adm-msg--${msg?.tone || "ok"}`}>{msg?.text}</span>
      </div>
    </section>
  );
}
