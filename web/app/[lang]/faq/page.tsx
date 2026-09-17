import type { Metadata } from "next";
import JsonLd, { breadcrumbList } from "@/components/JsonLd";
import type { JsonLdObject } from "@/components/JsonLd";
import PolicyPage from "@/components/PolicyPage";
import { api } from "@/lib/api";
import type { StorefrontConfig } from "@/lib/api";
import { faqDoc, faqEntries, say } from "@/lib/content";
import Crumbs, { crumbNodes, trail } from "@/lib/crumbs";
import type { Lang } from "@/lib/i18n";
import { buildMetadata, canonicalFor } from "@/lib/seo";

const PATH = "/faq";

/**
 * The questions on the page, marked up as the questions on the page.
 *
 * Both the visible answers and this node come from `faqEntries()`, so the
 * structured data cannot drift from what a customer reads, and a figure the
 * shop has not configured is missing from both.
 */
function faqPage(lang: Lang, cfg: StorefrontConfig | null): JsonLdObject | null {
  const entries = faqEntries(cfg);
  if (entries.length === 0) return null;
  return {
    "@type": "FAQPage",
    "@id": `${canonicalFor(lang, PATH)}#faq`,
    mainEntity: entries.map((entry) => ({
      "@type": "Question",
      "@id": `${canonicalFor(lang, PATH)}#${entry.id}`,
      name: say(lang, entry.question),
      acceptedAnswer: { "@type": "Answer", text: say(lang, entry.answer) },
    })),
  };
}

export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }): Promise<Metadata> {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  const doc = faqDoc(await api.config().catch(() => null));
  return buildMetadata({
    lang,
    path: PATH,
    title: say(lang, doc.title),
    description: say(lang, doc.description),
    ogSeed: "faq",
  });
}

export default async function Faq({ params }: { params: Promise<{ lang: string }> }) {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  const cfg = await api.config().catch(() => null);
  const doc = faqDoc(cfg);
  const crumbs = trail(lang, { name: say(lang, doc.title), path: PATH });
  return (
    <>
      <JsonLd id="ld-faq" data={[faqPage(lang, cfg), breadcrumbList(crumbNodes(lang, crumbs))]} />
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
