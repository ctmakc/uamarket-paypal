import type { Metadata } from "next";
import Link from "next/link";
import ExampleMark from "@/components/ExampleMark";
import JsonLd, { breadcrumbList, itemList } from "@/components/JsonLd";
import Motif from "@/components/Motif";
import { spansFor } from "@/components/ProductTile";
import { api } from "@/lib/api";
import Crumbs, { crumbNodes, trail } from "@/lib/crumbs";
import { catalogueStatus } from "@/lib/geo";
import type { Lang } from "@/lib/i18n";
import { href, pick, t } from "@/lib/i18n";
import { tf } from "@/lib/i18n.facts";
import { buildMetadata, canonicalFor, urlFor } from "@/lib/seo";

export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }): Promise<Metadata> {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  const d = t(lang);
  return buildMetadata({
    lang,
    path: "/makers",
    title: d.makers.title,
    description: tf(lang).makersSub,
    ogSeed: "makers",
  });
}

export default async function Makers({ params }: { params: Promise<{ lang: string }> }) {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  const d = t(lang);
  const makers = await api.makers().catch(() => ({ items: [] }));
  // Every workshop in the seeded catalogue is written, so every card says so.
  const madeUp = catalogueStatus() === "placeholder";
  const crumbs = trail(lang, { name: d.makers.title, path: "/makers" });
  const spans = spansFor(makers.items.length);
  return (
    <>
      <JsonLd
        id="ld-makers"
        data={[
          breadcrumbList(crumbNodes(lang, crumbs)),
          itemList({
            url: canonicalFor(lang, "/makers"),
            name: d.makers.title,
            items: makers.items.map((m) => ({
              url: urlFor(lang, `/makers/${m.slug}`),
              name: pick(lang, m.name, m.name_uk),
            })),
          }),
        ]}
      />
      <section className="canvas band">
        <Crumbs lang={lang} items={crumbs} style={{ marginBottom: "calc(var(--st) * 2)" }} />
        <div className="stack" style={{ marginBottom: "calc(var(--st) * 4)" }}>
          <h1 className="h1">{d.makers.title}</h1>
          <p className="lede muted">{tf(lang).makersSub}</p>
        </div>
        <div className="blocks">
          {makers.items.map((m, i) => (
            <Link
              key={m.slug}
              href={href(lang, `/makers/${m.slug}`)}
              className={`tile chart span-${spans[i]}`}
              style={{ minHeight: "calc(var(--blk) * 2)", gridTemplateRows: m.image_url ? "auto 1fr auto" : undefined }}
            >
              {/* The workshop picture runs the full width of the card, the way a product
                  photo bleeds to the tile edge. It used to sit in a 96 px square beside the
                  name, where a bench full of thread read as mush. */}
              {m.image_url ? (
                <span className="mk-band">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={m.image_url} alt="" loading="lazy" decoding="async" />
                </span>
              ) : null}
              <div style={{ display: "grid", gridTemplateColumns: m.image_url ? "1fr" : "96px 1fr", gap: "var(--st)", padding: "var(--st)", alignItems: "start" }}>
                {m.image_url ? null : (
                  <Motif seed={`maker-${m.slug}`} mode="complete" size={12} title={pick(lang, m.name, m.name_uk)} />
                )}
                <div className="stack--tight">
                  <div className="h3">{pick(lang, m.name, m.name_uk)}</div>
                  {madeUp ? <ExampleMark lang={lang} /> : null}
                  <div className="key">
                    <span>{pick(lang, m.region, m.region_uk)}</span>
                    {m.founded_year ? <span>{d.makers.since(m.founded_year)}</span> : null}
                  </div>
                  <p className="ui" style={{ fontWeight: 400 }}>{pick(lang, m.craft, m.craft_uk)}</p>
                </div>
              </div>
              <div className="tile__selvedge" style={{ minHeight: 0, gridTemplateRows: "24px" }}>
                <span className="tile__maker" style={{ gridRow: 1 }}>{d.makers.products(m.product_count || 0)}</span>
                <span className="tile__price" style={{ gridRow: 1 }}>→</span>
              </div>
            </Link>
          ))}
        </div>
      </section>
    </>
  );
}
