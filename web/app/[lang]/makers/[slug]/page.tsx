import type { Metadata } from "next";
import { notFound } from "next/navigation";
import ExampleMark from "@/components/ExampleMark";
import JsonLd, { breadcrumbList, itemList } from "@/components/JsonLd";
import Motif from "@/components/Motif";
import ProductTile, { spansFor } from "@/components/ProductTile";
import { api, ApiError } from "@/lib/api";
import type { Maker } from "@/lib/api";
import Crumbs, { crumbNodes, trail } from "@/lib/crumbs";
import { catalogueStatus } from "@/lib/geo";
import type { Lang } from "@/lib/i18n";
import { pick, t } from "@/lib/i18n";
import { makerDescription } from "@/lib/i18n.pages";
import { buildMetadata, canonicalFor, urlFor } from "@/lib/seo";

function crumbsFor(lang: Lang, m: Maker) {
  return trail(
    lang,
    { name: t(lang).makers.title, path: "/makers" },
    { name: pick(lang, m.name, m.name_uk), path: `/makers/${m.slug}` },
  );
}

export async function generateMetadata({ params }: { params: Promise<{ lang: string; slug: string }> }): Promise<Metadata> {
  const { lang: raw, slug } = await params;
  const lang = raw as Lang;
  let m: Maker;
  try {
    m = await api.maker(slug);
  } catch {
    return { title: t(lang).makers.title };
  }
  return buildMetadata({
    lang,
    path: `/makers/${m.slug}`,
    title: pick(lang, m.name, m.name_uk),
    description: makerDescription(lang, m),
    ogSeed: `maker-${m.slug}`,
  });
}

export default async function MakerPage({ params }: { params: Promise<{ lang: string; slug: string }> }) {
  const { lang: raw, slug } = await params;
  const lang = raw as Lang;
  const d = t(lang);
  let m;
  try {
    m = await api.maker(slug);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  const products = m.products || [];
  const madeUp = catalogueStatus() === "placeholder";
  const spans = spansFor(products.length);
  const crumbs = crumbsFor(lang, m);
  return (
    <>
      <JsonLd
        id="ld-maker"
        data={[
          breadcrumbList(crumbNodes(lang, crumbs)),
          itemList({
            url: canonicalFor(lang, `/makers/${m.slug}`),
            name: `${pick(lang, m.name, m.name_uk)} — ${d.makers.pieces}`,
            items: products.map((p) => ({
              url: urlFor(lang, `/product/${p.slug}`),
              name: pick(lang, p.title, p.title_uk),
            })),
          }),
        ]}
      />
      {/* Flat ink plate. The chart used to tile the whole 1440×648 band, with
          more than half of it ruled and empty; DESIGN.md keeps chart lines
          inside chart regions and names full-page wallpaper as forbidden. */}
      <section className="plate--ink on-plate">
        <div className="canvas band--tall">
          <div className="split split--5-7">
            <div className="split__a">
              {m.image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={m.image_url} alt={pick(lang, m.name, m.name_uk)} style={{ width: "100%", aspectRatio: "4 / 5", objectFit: "cover" }} />
              ) : (
                <div style={{ maxWidth: 360 }}>
                  <Motif seed={`maker-${m.slug}`} mode="complete" size={24} plate title={pick(lang, m.name, m.name_uk)} />
                </div>
              )}
            </div>
            <div className="split__b stack">
              <Crumbs lang={lang} items={crumbs} plate />
              <h1 className="h1">{pick(lang, m.name, m.name_uk)}</h1>
              {/* The story, the town and the year below are written for the demonstration,
                  so the name says it before a reader takes any of them for a fact. */}
              {madeUp ? (
                <div className="stack--tight">
                  <ExampleMark lang={lang} plate />
                  <p className="example-line example-line--plate">{d.makers.exampleLine}</p>
                </div>
              ) : null}
              <div className="key" style={{ color: "var(--muted-on-plate)", fontSize: "var(--fs-mono)" }}>
                <span>{pick(lang, m.region, m.region_uk)}</span>
                <span>{pick(lang, m.craft, m.craft_uk)}</span>
                {m.founded_year ? <span>{d.makers.since(m.founded_year)}</span> : null}
              </div>
              <p className="lede">{pick(lang, m.story, m.story_uk)}</p>
            </div>
          </div>
        </div>
      </section>
      <section className="canvas band">
        <div className="row-line" style={{ marginBottom: "calc(var(--st) * 3)" }}>
          <h2 className="h2">{d.makers.pieces}</h2>
          <span className="mono mono--sm muted">{d.makers.products(products.length)}</span>
        </div>
        <div className="blocks blocks--pairs">
          {products.map((p, i) => (
            <ProductTile key={p.slug} p={p} lang={lang} span={spans[i]} />
          ))}
        </div>
      </section>
    </>
  );
}
