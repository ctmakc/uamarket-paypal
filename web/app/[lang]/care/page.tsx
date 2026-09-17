import type { Metadata } from "next";
import JsonLd, { breadcrumbList } from "@/components/JsonLd";
import PolicyPage from "@/components/PolicyPage";
import type { Product } from "@/lib/api";
import { api } from "@/lib/api";
import { careDoc, say } from "@/lib/content";
import Crumbs, { crumbNodes, trail } from "@/lib/crumbs";
import type { Lang } from "@/lib/i18n";
import { buildMetadata } from "@/lib/seo";

const PATH = "/care";

/**
 * The care rules are the catalogue's own: this page loads every product and
 * groups the workshops' care lines by material family. It invents no rule, and
 * a piece whose workshop sent none is listed as such.
 */
async function catalogue(): Promise<Product[]> {
  const list = await api.products({ limit: 120 }).catch(() => ({ items: [], total: 0 }));
  const full = await Promise.all(list.items.map((item) => api.product(item.slug).catch(() => null)));
  return full.filter((p): p is Product => p !== null);
}

export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }): Promise<Metadata> {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  // Title and description are fixed text on the doc; the catalogue only fills
  // the page's rows, so metadata does not pay for 21 product calls.
  const doc = careDoc(null, []);
  return buildMetadata({
    lang,
    path: PATH,
    title: say(lang, doc.title),
    description: say(lang, doc.description),
    ogSeed: "care",
  });
}

export default async function CarePolicy({ params }: { params: Promise<{ lang: string }> }) {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  const [cfg, products] = await Promise.all([api.config().catch(() => null), catalogue()]);
  const doc = careDoc(cfg, products);
  const crumbs = trail(lang, { name: say(lang, doc.title), path: PATH });
  return (
    <>
      <JsonLd id="ld-care" data={breadcrumbList(crumbNodes(lang, crumbs))} />
      {/* The trail sits one band above the reading sheet: PolicyPage opens its
          own 96px band, so the row is pulled back to one body line above the
          title instead of floating a whole band away from it. */}
      <section className="canvas crumb-band">
        <Crumbs lang={lang} items={crumbs} />
      </section>
      <PolicyPage lang={lang} doc={doc} contactEmail={cfg?.contact_email} configMissing={cfg === null} />
    </>
  );
}
