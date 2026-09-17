/**
 * The size guide.
 *
 * Clothing in this shop is lettered XS–XXL and, for children, 4–12. The
 * catalogue carries no measurements for those letters, and inventing them would
 * be a fabrication, so this block renders in two states and says which one it
 * is in:
 *
 *   1. MEASURED — the product's attributes carry size-chart cells (the contract
 *      is written out in web/lib/i18n.product.ts). Rows are the sizes the piece
 *      is offered in, columns the measures found, values exactly as given.
 *   2. UNMEASURED — no cells. The block then shows only what is true: the sizes
 *      offered, which of them are sold out right now, the cut facts the workshop
 *      did send (sleeve, closure, fit…), a plain sentence saying the
 *      measurements are absent, and the route to an answer — the shop's contact
 *      address with the piece already in the subject line, plus the sizing entry
 *      on /faq.
 *
 * Both states are built from `product` alone, so a workshop that fills the
 * attributes in tomorrow gets the table with no code change.
 */
import Link from "next/link";
import type { Product } from "@/lib/api";
import type { Lang } from "@/lib/i18n";
import { href, pick } from "@/lib/i18n";
import { FIT_KEYS, MEASURE_ORDER, measureLabel, tpd, attributeLabel } from "@/lib/i18n.product";

export type SizeChart = {
  /** Size tokens, in the order the variants list them. */
  sizes: string[];
  /** Measure keys present for at least one size, known measures first. */
  measures: string[];
  /** cells[size][measure] — a size/measure pair with no cell is left blank. */
  cells: Record<string, Record<string, string>>;
  /** "cm" unless the workshop said otherwise. */
  unit: string;
  /** The workshop's own line on how it measured, when it sent one. */
  note: string | null;
};

const CHART_META = ["size_chart_unit", "size_chart_note", "size_chart_note_uk"];

/** The size tokens this piece is offered in, in catalogue order, deduplicated. */
export function sizesOffered(product: Product): string[] {
  const seen: string[] = [];
  for (const v of product.variants) {
    const s = v.options.size;
    if (s && !seen.includes(s)) seen.push(s);
  }
  return seen;
}

/** True when at least one variant in that size can be bought right now. */
export function sizeInStock(product: Product, size: string): boolean {
  return product.variants.some((v) => v.options.size === size && v.availability.in_stock);
}

/**
 * Read the size-chart cells out of `attributes`. Returns null when the piece
 * has no sizes or no cells at all — the caller then renders the honest state.
 */
export function parseSizeChart(product: Product, lang: Lang): SizeChart | null {
  const sizes = sizesOffered(product);
  if (!sizes.length) return null;
  const cells: Record<string, Record<string, string>> = {};
  const found = new Set<string>();
  for (const size of sizes) {
    const prefix = `size_${size}_`;
    for (const [key, value] of Object.entries(product.attributes)) {
      if (!key.startsWith(prefix)) continue;
      const measure = key.slice(prefix.length);
      if (!measure) continue;
      const text = String(value).trim();
      if (!text) continue;
      found.add(measure);
      (cells[size] ??= {})[measure] = text;
    }
  }
  if (!found.size) return null;
  const known = MEASURE_ORDER.filter((m) => found.has(m)) as string[];
  const extra = [...found].filter((m) => !known.includes(m)).sort();
  const unitKey = String(product.attributes.size_chart_unit ?? "cm").toLowerCase();
  const unit = unitKey === "in" ? tpd(lang).unit.in : tpd(lang).unit.cm;
  const note = pick(
    lang,
    product.attributes.size_chart_note === undefined ? null : String(product.attributes.size_chart_note),
    product.attributes.size_chart_note_uk === undefined ? null : String(product.attributes.size_chart_note_uk),
  );
  return { sizes, measures: [...known, ...extra], cells, unit, note: note || null };
}

/**
 * Cut facts the workshop sent, in reading order.
 *
 * The value is free text in whatever language the workshop wrote it, so a row
 * is printed in Ukrainian only when a `<key>_uk` sibling exists. Without that
 * rule the Ukrainian table read "Рукав → full": translated on the left, raw
 * English on the right. A missing translation drops the row rather than
 * printing the English one; docs/OWNER-ACTIONS.md asks the workshops for it.
 */
export function fitFacts(product: Product, lang: Lang): { key: string; label: string; value: string }[] {
  const out: { key: string; label: string; value: string }[] = [];
  for (const key of FIT_KEYS) {
    const base = product.attributes[key];
    if (base === undefined) continue;
    const localized = product.attributes[`${key}_uk`];
    if (lang === "uk" && localized === undefined) continue;
    const value = pick(lang, String(base), localized === undefined ? null : String(localized));
    if (value.trim()) out.push({ key, label: attributeLabel(lang, key), value: value.trim() });
  }
  return out;
}

/**
 * Every attribute key this block consumes, so the specification list can print
 * the rest without repeating a row.
 */
export function sizeGuideKeys(product: Product): Set<string> {
  const keys = new Set<string>(CHART_META);
  for (const key of FIT_KEYS) {
    keys.add(key);
    keys.add(`${key}_uk`);
  }
  for (const size of sizesOffered(product)) {
    const prefix = `size_${size}_`;
    for (const key of Object.keys(product.attributes)) if (key.startsWith(prefix)) keys.add(key);
  }
  return keys;
}

const CSS = `
.sg__scroll { overflow-x: auto; }
.sg__table { width: 100%; border-collapse: collapse; font-family: var(--face-mono); font-size: var(--fs-mono); line-height: 24px; font-variant-numeric: tabular-nums; }
.sg__table th, .sg__table td { text-align: left; padding: var(--st) var(--st) var(--st) 0; border-bottom: 1px dashed var(--count-major); white-space: nowrap; }
.sg__table thead th { font-size: var(--fs-mono-sm); font-weight: 400; color: var(--muted); border-bottom: 1px solid var(--thread-black); }
.sg__table tbody th { font-weight: 500; }
/* the slack goes to the last column, so the numbers stay in a tight block */
.sg__table th:last-child, .sg__table td:last-child { width: 100%; }
.sg__sizes { display: flex; flex-wrap: wrap; gap: 0 var(--st); font-family: var(--face-mono); font-size: var(--fs-mono); line-height: 24px; }
.sg__size[data-out="true"] { color: var(--muted); text-decoration: line-through; text-decoration-thickness: 1px; }
`;

export default function SizeGuide({
  lang,
  product,
  contactEmail,
  id = "size-guide",
}: {
  lang: Lang;
  product: Product;
  contactEmail: string | null;
  id?: string;
}) {
  const d = tpd(lang).sizeGuide;
  const sizes = sizesOffered(product);
  if (!sizes.length) return null;
  const chart = parseSizeChart(product, lang);
  const fit = fitFacts(product, lang);
  const title = pick(lang, product.title, product.title_uk);
  const mailto = contactEmail
    ? `mailto:${contactEmail}?subject=${encodeURIComponent(d.mailSubject(title))}`
    : null;

  return (
    <section id={id} className="stack" aria-labelledby={`${id}-h`}>
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      <h2 className="h3" id={`${id}-h`}>{d.heading}</h2>

      {chart ? (
        <div className="stack--tight">
          <p className="mono mono--sm muted">{d.measuredIn(chart.unit)}</p>
          <div className="sg__scroll">
            <table className="sg__table">
              <thead>
                <tr>
                  <th scope="col">{d.sizeColumn}</th>
                  {chart.measures.map((m) => (
                    <th key={m} scope="col">{measureLabel(lang, m)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {chart.sizes.map((s) => (
                  <tr key={s}>
                    <th scope="row">{s}</th>
                    {chart.measures.map((m) => (
                      <td key={m}>{chart.cells[s]?.[m] ?? "—"}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {chart.note ? <p className="mono mono--sm muted">{chart.note}</p> : null}
        </div>
      ) : (
        <div className="stack--tight">
          <p className="mono mono--sm muted">{d.offered}</p>
          <p className="sg__sizes">
            {sizes.map((s) => {
              const out = !sizeInStock(product, s);
              return (
                <span key={s} className="sg__size" data-out={out}>
                  {s}
                  {out ? <span className="sr-only"> — {d.soldOut}</span> : null}
                </span>
              );
            })}
          </p>
        </div>
      )}

      {fit.length ? (
        <div>
          <p className="mono mono--sm muted">{d.fitHeading}</p>
          <dl>
            {fit.map((f) => (
              <div key={f.key} className="row-line" style={{ gridTemplateColumns: "minmax(110px, 1fr) 2fr" }}>
                <dt className="mono mono--sm muted">{f.label}</dt>
                <dd style={{ margin: 0, fontSize: "var(--fs-ui)", lineHeight: "24px" }}>{f.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}

      {/* An absent field is information, not a warning: mustard is reserved
          for low stock and payment pending (DESIGN.md). */}
      {chart ? null : (
        <div className="notice notice--note stack--tight">
          <p>{d.missing}</p>
          <p>{mailto ? d.askLead : d.askNoEmail}</p>
          {mailto ? (
            <p className="ui">
              <a href={mailto} className="thread-link">{contactEmail} →</a>
            </p>
          ) : null}
          <p className="ui">
            <Link href={href(lang, "/faq#sizing")} className="thread-link tap">{d.faqLink} →</Link>
          </p>
        </div>
      )}
    </section>
  );
}
