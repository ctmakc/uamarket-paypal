import type { Metadata } from "next";
import Link from "next/link";
import ExampleMark from "@/components/ExampleMark";
import Motif from "@/components/Motif";
import ProductTile, { spansFor } from "@/components/ProductTile";
import { api, money } from "@/lib/api";
import { heroSubFor, paymentList, pickupHours, say } from "@/lib/content";
import { catalogueStatus } from "@/lib/geo";
import type { Lang } from "@/lib/i18n";
import { href, pick, t } from "@/lib/i18n";
import { tf } from "@/lib/i18n.facts";
import { mailNotice } from "@/lib/i18n.mail";
import { shipPhrase } from "@/lib/i18n.pages";
import { PROPOSED_SEO, proposedSeoOn } from "@/lib/i18n.seo";
import { buildMetadata } from "@/lib/seo";

/**
 * The home page's title is the shop's own hero line, so the tab, the search
 * result and the page all say the same sentence. It is absolute because the
 * layout's "%s · UA Market" suffix would otherwise print the brand twice.
 */
function heroLine(lang: Lang): string {
  const d = t(lang);
  return `${d.home.heroLine1} ${d.home.heroLine2}`.replace(/[.\s]+$/u, "");
}

/** The hero sells pickup only where the checkout would accept it. */
function heroSub(lang: Lang, pickup: boolean): string {
  return heroSubFor(lang, pickup);
}

export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }): Promise<Metadata> {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  const d = t(lang);
  const cfg = await api.config().catch(() => null);
  const proposed = proposedSeoOn() ? PROPOSED_SEO[lang] : null;
  const title = proposed ? proposed.homeTitle : `${d.brand} — ${heroLine(lang)}`;
  const meta = buildMetadata({
    lang,
    path: "/",
    title,
    description: proposed ? proposed.homeDescription : heroSub(lang, cfg?.pickup.enabled === true),
    // The card charts the same motif the hero embroiders on the page.
    ogSeed: "ua-market-hero",
  });
  return { ...meta, title: { absolute: title } };
}

export default async function Home({ params }: { params: Promise<{ lang: string }> }) {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  const d = t(lang);
  const [featured, collections, makers, cfg] = await Promise.all([
    api.products({ featured: true, limit: 6 }).catch(() => ({ items: [], total: 0 })),
    api.collections().catch(() => ({ items: [] })),
    api.makers().catch(() => ({ items: [] })),
    api.config().catch(() => null),
  ]);
  // The three "how it works" cards state what the shop has switched on, read
  // from the same configuration checkout reads.
  const f = tf(lang);
  // The workshops in the band below are written for the demonstration.
  const madeUp = catalogueStatus() === "placeholder";
  const mail = mailNotice(cfg);
  const hours = pickupHours(cfg);
  const pay = paymentList(cfg);
  const how: [string, string][] = [
    [f.shipTitle(shipPhrase(lang)), cfg ? f.shipSub(money(cfg.shipping.flat_cad, lang), money(cfg.shipping.free_over_cad, lang), mail.email) : f.aboutShippingUnknown],
    ...(cfg?.pickup.enabled === false ? [] : ([[d.home.howPickup, f.pickupSub(hours ? say(lang, hours) : null)]] as [string, string][])),
    pay ? [f.payTitle(say(lang, pay)), d.home.howPaySub] : [f.payNone, f.payNoneSub],
  ];
  // One rule for every card grid on the site; see spansFor in ProductTile.
  const collectionSpans = spansFor(collections.items.length);
  const featuredSpans = spansFor(featured.items.length);

  return (
    <>
      {/* ------------------------------------------------ hero */}
      <section className="canvas band--tall">
        <div className="hero">
          <div className="hero__copy stack--loose">
            <h1 className="display">
              <span className="stitch-in" style={{ display: "block" }}>{d.home.heroLine1}</span>
              <span className="display--light stitch-in" style={{ display: "block", animationDelay: "240ms" }}>{d.home.heroLine2}</span>
            </h1>
            <p className="lede">{heroSub(lang, cfg?.pickup.enabled === true)}</p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "calc(var(--st) * 2)", alignItems: "center" }}>
              <Link href={href(lang, "/shop")} className="btn btn--red btn--lg">{d.home.heroCta}</Link>
              <Link href={href(lang, "/makers")} className="thread-link ui">{d.home.heroCta2} →</Link>
            </div>
          </div>
          <div className="hero__motif chart" style={{ aspectRatio: "1 / 1" }}>
            <Motif seed="ua-market-hero" mode="hero" size={24} title="UA Market hero motif" />
          </div>
        </div>
      </section>

      {/* On a phone the shop's pick comes first and the collections follow as a compact
          two-column index (.home-pair in globals.css); on a wide screen the order is
          collections, then the pick. */}
      <div className="home-pair">
      {/* ------------------------------------------------ collections */}
      <section className="canvas band home-pair__cols" id="collections">
        <div className="row-line" style={{ marginBottom: "calc(var(--st) * 3)" }}>
          <h2 className="h2">{d.home.collections}</h2>
          <Link href={href(lang, "/shop")} className="thread-link ui">{d.home.seeAll} →</Link>
        </div>
        <div className="blocks">
          {collections.items.map((c, i) => (
            <Link key={c.slug} href={href(lang, `/shop?collection=${c.slug}`)} className={`tile tile--short chart col-tile span-${collectionSpans[i]}`}>
              <div className="col-tile__body">
                <Motif seed={`collection-${c.slug}`} mode="complete" size={12} title={pick(lang, c.title, c.title_uk)} className="col-tile__motif" />
                <div>
                  <div className="h3 col-tile__name">{pick(lang, c.title, c.title_uk)}</div>
                  <p className="ui muted col-tile__lede" style={{ fontWeight: 400 }}>{pick(lang, c.lede, c.lede_uk)}</p>
                </div>
              </div>
              <div className="tile__selvedge" style={{ minHeight: 0, gridTemplateRows: "24px" }}>
                <span className="tile__maker" style={{ gridRow: 1 }}>{d.shop.results(c.count)}</span>
                <span className="tile__price" style={{ gridRow: 1 }}>→</span>
              </div>
            </Link>
          ))}
        </div>
      </section>

      {/* ------------------------------------------------ featured */}
      <section className="canvas band home-pair__pick" id="pick">
        <div className="row-line" style={{ marginBottom: "calc(var(--st) * 3)" }}>
          <div>
            {/* `featured` is a static flag the seeder sets and the catalogue
                records no made-on or listed-on date, so the band names itself
                as a selection rather than as this week's finished work. */}
            <h2 className="h2">{f.featured}</h2>
            <p className="muted">{f.featuredSub}</p>
          </div>
          <Link href={href(lang, "/shop")} className="thread-link ui">{d.home.seeAll} →</Link>
        </div>
        <div className="blocks blocks--pairs">
          {featured.items.map((p, i) => (
            <ProductTile key={p.slug} p={p} lang={lang} span={featuredSpans[i]} eager={i < 2} />
          ))}
        </div>
      </section>
      </div>

      {/* ------------------------------------------------ makers */}
      {/* A dark plate, flat: the counted chart lives inside tiles and the hero
          motif, never as a full-bleed band of wallpaper (see DESIGN.md). */}
      <section className="plate--ink on-plate">
        <div className="canvas band--tall">
          <div className="split split--5-7">
            <div className="split__a stack">
              <h2 className="h2">{d.home.makers}</h2>
              <p className="lede">{d.home.makersSub}</p>
              <Link href={href(lang, "/makers")} className="thread-link ui">{d.nav.makers} →</Link>
            </div>
            <div className="split__b">
              {makers.items.map((m) => (
                <Link key={m.slug} href={href(lang, `/makers/${m.slug}`)} className="row-line" style={{ borderColor: "var(--count-major-on-plate)" }}>
                  <span>
                    <span className="h3" style={{ display: "block" }}>{pick(lang, m.name, m.name_uk)}</span>
                    {madeUp ? <ExampleMark lang={lang} plate className="row-line__example" /> : null}
                    <span className="key" style={{ color: "var(--muted-on-plate)" }}>
                      <span>{pick(lang, m.region, m.region_uk)}</span>
                      <span>{pick(lang, m.craft, m.craft_uk)}</span>
                    </span>
                  </span>
                  <span className="mono mono--sm" style={{ color: "var(--muted-on-plate)" }}>{d.makers.products(m.product_count || 0)}</span>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------ how it works */}
      <section className="canvas band--tall">
        <h2 className="h2" style={{ marginBottom: "calc(var(--st) * 3)" }}>{d.home.how}</h2>
        <div className="blocks">
          {how.map(([h, sub], i) => (
            <div key={i} className="span-4 stack--tight" style={{ paddingTop: "var(--st)", borderTop: "2px dashed var(--thread-black)" }}>
              <h3 className="h3">{h}</h3>
              <p className="muted">{sub}</p>
            </div>
          ))}
        </div>
        <p style={{ marginTop: "calc(var(--st) * 3)" }}>
          <Link href={href(lang, "/about")} className="thread-link ui">{d.nav.about} →</Link>
        </p>
      </section>
    </>
  );
}
