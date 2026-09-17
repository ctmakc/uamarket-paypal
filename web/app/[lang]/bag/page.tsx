import type { Metadata } from "next";
import BagView from "@/components/BagView";
import { api } from "@/lib/api";
import { catalogueStatus } from "@/lib/geo";
import type { Lang } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { tp } from "@/lib/i18n.pages";
import { buildMetadata } from "@/lib/seo";

/** A bag holds one shopper's own choices, so it is closed to every index. */
export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }): Promise<Metadata> {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  return buildMetadata({
    lang,
    path: "/bag",
    title: t(lang).bag.title,
    description: tp(lang).bagDescription,
    robots: { index: false, follow: false },
  });
}

export default async function BagPage({ params }: { params: Promise<{ lang: string }> }) {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  const config = await api.config().catch(() => null);
  return (
    <section className="canvas band">
      <BagView lang={lang} config={config} demo={catalogueStatus() === "placeholder"} />
    </section>
  );
}
