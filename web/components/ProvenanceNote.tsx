/**
 * The provenance mark, expanded in place.
 *
 * The three stitch marks are the shop's central claim, and on a tile the mark
 * is all a buyer gets. On the product page the mark earns a paragraph: what the
 * mark means, then what it means for THIS piece — the workshop and its region,
 * the craft and the year the workshop names, the technique this piece is worked
 * in, and the workshop's own origin note. Every one of those lines comes from
 * the catalogue and is omitted when the catalogue has nothing to put there; the
 * component invents no timing, no village and no story.
 *
 * It borrows the page's existing language — the stitch mark, the mono caption,
 * the dashed `.row-line` list — so it adds no card style of its own.
 */
import type { ReactNode } from "react";
import Link from "next/link";
import ExampleMark from "@/components/ExampleMark";
import StitchMark from "@/components/StitchMark";
import type { Maker, Product } from "@/lib/api";
import { catalogueStatus } from "@/lib/geo";
import type { Lang } from "@/lib/i18n";
import { href, pick } from "@/lib/i18n";
import { tpd } from "@/lib/i18n.product";

type Row = { key: string; label: string; value: ReactNode };

export default function ProvenanceNote({
  lang,
  product,
  maker,
  id = "provenance",
}: {
  lang: Lang;
  product: Product;
  maker: Maker | null;
  id?: string;
}) {
  const d = tpd(lang).provenance;
  const originLabel = pick(lang, product.origin_label, product.origin_label_uk);
  const rows: Row[] = [];

  if (product.maker) {
    const name = pick(lang, product.maker.name, product.maker.name_uk);
    const region = pick(lang, product.maker.region, product.maker.region_uk);
    // The workshop, its region, its craft and its founding year are the seeded
    // ones while the catalogue is: the row that names them says so in place.
    const madeUp = catalogueStatus() === "placeholder";
    rows.push({
      key: "workshop",
      label: d.workshop,
      value: (
        <>
          <Link href={href(lang, `/makers/${product.maker.slug}`)} className="thread-link">{name}</Link>
          {region ? ` — ${region}` : null}
          {madeUp ? <> <ExampleMark lang={lang} /></> : null}
        </>
      ),
    });
  }
  if (maker?.craft) rows.push({ key: "craft", label: d.craft, value: pick(lang, maker.craft, maker.craft_uk) });
  if (maker?.founded_year) rows.push({ key: "since", label: d.since, value: String(maker.founded_year) });
  if (product.technique) {
    rows.push({ key: "technique", label: d.technique, value: pick(lang, product.technique, product.technique_uk) });
  }
  if (product.origin_note) {
    rows.push({ key: "note", label: d.note, value: pick(lang, product.origin_note, product.origin_note_uk) });
  }

  return (
    <section id={id} className="stack" aria-labelledby={`${id}-h`}>
      <h2 className="h3" id={`${id}-h`}>{d.heading}</h2>
      <p className="status" style={{ color: "var(--ink)" }}>
        <StitchMark origin={product.origin} lang={lang} />
        <span className="mono mono--sm">{originLabel}</span>
      </p>
      <p className="measure">{d.lead[product.origin]}</p>
      {rows.length ? (
        <dl>
          {rows.map((r) => (
            <div key={r.key} className="row-line" style={{ gridTemplateColumns: "minmax(110px, 1fr) 2fr" }}>
              <dt className="mono mono--sm muted">{r.label}</dt>
              <dd style={{ margin: 0, fontSize: "var(--fs-ui)", lineHeight: "24px" }}>{r.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      <p className="ui">
        <Link href={href(lang, "/faq#provenance-marks")} className="thread-link">{d.faqLink} →</Link>
      </p>
    </section>
  );
}
