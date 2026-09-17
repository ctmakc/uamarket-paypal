import type { Metadata } from "next";
import JsonLd, { breadcrumbList } from "@/components/JsonLd";
import PolicyPage from "@/components/PolicyPage";
import { api } from "@/lib/api";
import { privacyDoc, say } from "@/lib/content";
import Crumbs, { crumbNodes, trail } from "@/lib/crumbs";
import type { Lang } from "@/lib/i18n";
import { buildMetadata } from "@/lib/seo";

const PATH = "/privacy";

export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }): Promise<Metadata> {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  const doc = privacyDoc(await api.config().catch(() => null));
  return buildMetadata({
    lang,
    path: PATH,
    title: say(lang, doc.title),
    description: say(lang, doc.description),
    ogSeed: "privacy",
  });
}

export default async function PrivacyPolicy({ params }: { params: Promise<{ lang: string }> }) {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  const cfg = await api.config().catch(() => null);
  const doc = privacyDoc(cfg);
  const crumbs = trail(lang, { name: say(lang, doc.title), path: PATH });
  return (
    <>
      <JsonLd id="ld-privacy" data={breadcrumbList(crumbNodes(lang, crumbs))} />
      {/* The trail sits one band above the reading sheet: PolicyPage opens its
          own 96px band, so the row is pulled back to one body line above the
          title instead of floating a whole band away from it. */}
      <section className="canvas crumb-band">
        <Crumbs lang={lang} items={crumbs} />
      </section>
      <PolicyPage lang={lang} doc={doc} contactEmail={cfg?.contact_email} configMissing={cfg === null} business={cfg?.business} seller />
    </>
  );
}
