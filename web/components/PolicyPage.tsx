import Link from "next/link";
import type { BusinessIdentity } from "@/lib/api";
import type { PolicyBlock, PolicyDoc, PolicyRow } from "@/lib/content";
import { say, writtenDate } from "@/lib/content";
import SellerBlock from "./SellerBlock";
import type { Lang } from "@/lib/i18n";
import { href } from "@/lib/i18n";
import { tc } from "@/lib/i18n.content";

/**
 * One reading layout for the FAQ and the four policy pages.
 *
 * The page is a chart of ruled rows: an index of the sections in the narrow
 * column, the sections themselves as counted rows in the wide one. Every
 * section carries the same shape — a numbered heading at H2 across the reading
 * column, the prose under it — so the FAQ and the four policy documents read
 * as one set. The layout classes live in web/app/globals.css.
 */

function RowList({ lang, rows, layout }: { lang: Lang; rows: PolicyRow[]; layout: "figures" | "notes" }) {
  return (
    <dl style={{ margin: 0 }}>
      {rows.map((row, i) => {
        const label = say(lang, row.label);
        const value = say(lang, row.value);
        const note = row.note ? say(lang, row.note) : null;
        return (
          <div
            key={`${label}-${i}`}
            style={
              layout === "figures"
                ? {
                    display: "grid",
                    gridTemplateColumns: "minmax(0, 1fr) auto",
                    gap: "0 var(--st)",
                    alignItems: "baseline",
                    paddingBlock: "4px",
                    borderBottom: "1px dashed var(--count-major)",
                  }
                : { paddingBlock: "var(--st)", borderBottom: "1px dashed var(--count-major)" }
            }
          >
            <dt className={layout === "figures" ? "ui" : "mono mono--sm muted"} style={{ margin: 0 }}>
              {row.href ? (
                <Link href={href(lang, row.href)} className="thread-link">
                  {label}
                </Link>
              ) : (
                label
              )}
            </dt>
            <dd
              className={layout === "figures" ? "mono" : undefined}
              // A short figure (money, a day range) keeps its line; a long one
              // wraps rather than pushing the row past a narrow viewport.
              style={layout === "figures" ? { margin: 0, whiteSpace: value.length > 24 ? "normal" : "nowrap" } : { margin: 0, maxWidth: "62ch" }}
            >
              {value}
            </dd>
            {/* Where a figure comes from, when it is a software default rather
                than a setting the owner made. The page's own opening sentence
                claims configuration for all of them, so the ones that are not
                say so beside the number. */}
            {/* A second <dd> rather than a <p>: inside a <dl>, a wrapping <div>
                may hold only dt/dd groups, and a paragraph there is a WCAG
                definition-list violation (axe: serious). */}
            {note ? (
              <dd className="mono mono--sm muted" style={{ gridColumn: "1 / -1", margin: 0 }}>
                {note}
              </dd>
            ) : null}
          </div>
        );
      })}
    </dl>
  );
}

function Block({ lang, block }: { lang: Lang; block: PolicyBlock }) {
  if (block.kind === "text") return <p className="measure">{say(lang, block.body)}</p>;
  if (block.kind === "list") {
    return (
      <ul className="stack--tight measure" style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {block.items.map((item, i) => (
          <li key={i} style={{ display: "grid", gridTemplateColumns: "calc(var(--st) * 2) minmax(0, 1fr)", gap: "var(--st)" }}>
            <span className="mono mono--sm muted" aria-hidden="true">
              ×
            </span>
            <span>{say(lang, item)}</span>
          </li>
        ))}
      </ul>
    );
  }
  if (block.kind === "rows") return <RowList lang={lang} rows={block.rows} layout={block.layout} />;
  return (
    <div>
      {block.entries.map((entry) => (
        <article key={entry.id} id={entry.id} className="policy-qa">
          <h3
            style={{
              fontFamily: "var(--face-display)",
              fontWeight: 600,
              fontSize: "20px",
              lineHeight: "24px",
              letterSpacing: "-0.01em",
              maxWidth: "48ch",
            }}
          >
            {say(lang, entry.question)}
          </h3>
          <p className="measure" style={{ marginTop: "var(--st)" }}>
            {say(lang, entry.answer)}
          </p>
          {entry.link ? (
            <p className="ui" style={{ marginTop: "var(--st)" }}>
              <Link href={href(lang, entry.link.path)} className="thread-link tap">
                {say(lang, entry.link.label)} <span aria-hidden="true">→</span>
              </Link>
            </p>
          ) : null}
        </article>
      ))}
    </div>
  );
}

/** True when a page prints a figure marked unconfirmed or a value not published yet. */
function hasOpenValues(doc: PolicyDoc): boolean {
  const marks = /not confirmed yet|not published yet|ще не підтверджено|ще не опубліковано|не опубліковано/i;
  return doc.sections.some((section) =>
    section.blocks.some((block) => {
      if (block.kind === "rows") return block.rows.some((r) => Boolean(r.note) || marks.test(r.value.en) || marks.test(r.value.uk));
      if (block.kind === "text") return marks.test(block.body.en) || marks.test(block.body.uk);
      if (block.kind === "list") return block.items.some((i) => marks.test(i.en));
      return block.entries.some((e) => marks.test(e.answer.en));
    }),
  );
}

export default function PolicyPage({
  lang,
  doc,
  contactEmail,
  configMissing = false,
  business,
  seller = false,
}: {
  lang: Lang;
  doc: PolicyDoc;
  contactEmail?: string | null;
  configMissing?: boolean;
  business?: BusinessIdentity | null;
  /** Print the seller block (terms and privacy). */
  seller?: boolean;
}) {
  const c = tc(lang);
  // One line per page, instead of a sentence about software beside every figure: the page
  // says the open values will be confirmed before opening and where to ask meanwhile.
  const openValues = seller || hasOpenValues(doc);
  return (
    <section className="canvas band">
      <header style={{ maxWidth: "62ch" }}>
        <h1 className="h1">{say(lang, doc.title)}</h1>
        <p className="lede muted" style={{ marginTop: "calc(var(--st) * 2)" }}>
          {say(lang, doc.lede)}
        </p>
        {openValues ? <p className="confirm-line" data-confirm-line>{c.confirmLine(contactEmail ?? null)}</p> : null}
      </header>
      {seller ? <div style={{ marginTop: "calc(var(--st) * 3)" }}><SellerBlock lang={lang} business={business} /></div> : null}

      <div className="split split--5-7" style={{ marginTop: "calc(var(--st) * 4)" }}>
        <div className="split__a">
          <nav className="sticky" aria-labelledby={`${doc.id}-index`}>
            <p className="eyebrow" id={`${doc.id}-index`}>
              {c.index}
            </p>
            <ol className="stack--tight policy-index" style={{ listStyle: "none", padding: 0, margin: "var(--st) 0 0", fontSize: "var(--fs-ui)", lineHeight: "24px" }}>
              {doc.sections.map((section, i) => (
                <li key={section.id} style={{ display: "grid", gridTemplateColumns: "calc(var(--st) * 3) minmax(0, 1fr)", gap: "var(--st)" }}>
                  <span className="mono mono--sm muted" aria-hidden="true">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <a href={`#${section.id}`} className="thread-link">
                    {say(lang, section.heading)}
                  </a>
                </li>
              ))}
            </ol>
            <p className="mono mono--sm muted" style={{ marginTop: "calc(var(--st) * 3)" }}>
              {c.written(writtenDate(lang))}
            </p>
            <p className="mono mono--sm muted" style={{ marginTop: "var(--st)", maxWidth: "44ch" }}>
              {c.draftNote(contactEmail ?? null)}
            </p>
          </nav>
        </div>

        <div className="split__b">
          {configMissing ? (
            <p className="notice notice--warn" style={{ marginBottom: "calc(var(--st) * 2)" }}>
              {c.configMissing}
            </p>
          ) : null}

          {/* One section shape for all five documents: the numbered heading
              across the reading column, the prose under it. The FAQ used to be
              the only page built this way while the four policy pages squeezed
              the same heading into a 171px rail. */}
          {doc.sections.map((section, n) => (
            <section key={section.id} id={section.id} className="policy-row">
              <h2 className="h2 policy-row__head">
                <span className="mono mono--sm muted" aria-hidden="true">
                  {String(n + 1).padStart(2, "0")}
                </span>
                <span>{say(lang, section.heading)}</span>
              </h2>
              <div className="prose stack">
                {section.blocks.map((block, i) => (
                  <Block key={i} lang={lang} block={block} />
                ))}
              </div>
            </section>
          ))}

          <section className="policy-row" id="ask">
            <h2 className="h2 policy-row__head">
              <span className="mono mono--sm muted" aria-hidden="true">
                {String(doc.sections.length + 1).padStart(2, "0")}
              </span>
              <span>{c.stillHeading}</span>
            </h2>
            <div className="prose">
              {contactEmail ? (
                <>
                  <p className="measure">{c.stillLead}</p>
                  <p className="mono" style={{ marginTop: "var(--st)" }}>
                    <a href={`mailto:${contactEmail}`} className="thread-link">
                      {contactEmail}
                    </a>
                  </p>
                </>
              ) : (
                <p className="measure">{c.stillNoEmail}</p>
              )}
            </div>
          </section>
        </div>
      </div>
    </section>
  );
}
