import type { Metadata } from "next";
import CheckoutForm from "@/components/CheckoutForm";
import { api } from "@/lib/api";
import { carrierIsSet, shopPolicy } from "@/lib/content";
import type { Lang } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { tf } from "@/lib/i18n.facts";
import { tp } from "@/lib/i18n.pages";
import { catalogueStatus } from "@/lib/geo";
import { buildMetadata } from "@/lib/seo";

/** Checkout carries a shopper's contact and address: noindex, nofollow. */
export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }): Promise<Metadata> {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  return buildMetadata({
    lang,
    path: "/checkout",
    title: t(lang).checkout.title,
    description: tp(lang).checkoutDescription,
    robots: { index: false, follow: false },
  });
}

export default async function CheckoutPage({ params }: { params: Promise<{ lang: string }> }) {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  const d = t(lang);
  let config;
  try {
    config = await api.config();
  } catch {
    return (
      <section className="canvas band stack">
        <h1 className="h1">{d.checkout.title}</h1>
        <p className="error">{d.checkout.errors.generic}</p>
      </section>
    );
  }
  return (
    <section className="canvas band">
      {/* The carrier name is read on the server: SHOP_CARRIER is a server
          setting, and the form is a client component. */}
      <CheckoutForm lang={lang} config={config} demo={catalogueStatus() === "placeholder"} shipLabel={tf(lang).shipOption(carrierIsSet() ? shopPolicy().carrier : null)} />
    </section>
  );
}
