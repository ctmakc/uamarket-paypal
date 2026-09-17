import type { Metadata } from "next";
import { notFound } from "next/navigation";
import "../globals.css";
import JsonLd, { onlineStore, website } from "@/components/JsonLd";
import DemoStrip from "@/components/DemoStrip";
import PlaceholderNotice from "@/components/PlaceholderNotice";
import SiteHeader from "@/components/SiteHeader";
import SiteFooter from "@/components/SiteFooter";
import { api } from "@/lib/api";
import type { Collection } from "@/lib/api";
import { catalogueStatus } from "@/lib/geo";
import { taglineFor } from "@/lib/content";
import { LANGS, isLang, t } from "@/lib/i18n";
import { buildMetadata, siteUrl } from "@/lib/seo";

// A shop renders per request: stock, prices and payment options must never be baked at build time.
export const dynamic = "force-dynamic";

export function generateStaticParams() {
  return LANGS.map((lang) => ({ lang }));
}

export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }): Promise<Metadata> {
  const { lang } = await params;
  const l = isLang(lang) ? lang : "en";
  const d = t(l);
  const base = buildMetadata({ lang: l, path: "/", title: d.brand, description: taglineFor(l), ogSeed: "ua-market-hero" });
  return {
    ...base,
    // Pages set their own title; the layout supplies the fallback and the suffix.
    title: { default: d.brand, template: `%s · ${d.brand}` },
    // The canonical URL and the hreflang set belong to the page. A layout-level
    // pair would attach the home page's address to every route that sets none —
    // the 404 page, for one — so it is left off here on purpose.
    alternates: undefined,
  };
}

export default async function LangLayout({ children, params }: { children: React.ReactNode; params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const d = t(lang);
  let contactEmail: string | null = null;
  try {
    contactEmail = (await api.config()).contact_email;
  } catch {
    contactEmail = null;
  }
  // The footer's shop column names collections; reading them from the
  // catalogue is the only way they cannot drift from it, and it is what stopped
  // "Heritage" and "Everyday" printing in English on every Ukrainian page.
  let collections: Collection[] = [];
  try {
    collections = (await api.collections()).items.slice(0, 3);
  } catch {
    collections = [];
  }
  return (
    <html lang={lang === "uk" ? "uk" : "en-CA"}>
      <body>
        {/* The shop and the site itself, described once for every page below. The logo is
            the cross-stitch "UA" from tools/brand_assets.py. */}
        <JsonLd
          id="ld-site"
          data={[
            onlineStore({ lang, description: taglineFor(lang), email: contactEmail, logoUrl: `${siteUrl()}/logo-512.png` }),
            website({ lang, description: taglineFor(lang) }),
          ]}
        />
        {catalogueStatus() === "placeholder" ? <DemoStrip lang={lang} /> : null}
        <SiteHeader lang={lang} />
        {/* tabIndex makes the skip link actually move the focus: without it the
            hash changes and document.activeElement stays on <body>. */}
        <main id="main" tabIndex={-1}>{children}</main>
        {/* While the assortment is the seeded demonstration one, every human
            page says so, in the same words /llms.txt and /api/catalog use. */}
        {catalogueStatus() === "placeholder" ? <PlaceholderNotice lang={lang} /> : null}
        <SiteFooter lang={lang} contactEmail={contactEmail} collections={collections} />
      </body>
    </html>
  );
}
