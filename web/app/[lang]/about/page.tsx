import type { Metadata } from "next";
import JsonLd, { breadcrumbList, localBusiness } from "@/components/JsonLd";
import SellerBlock from "@/components/SellerBlock";
import { tb } from "@/lib/i18n.buy";
import StitchMark from "@/components/StitchMark";
import { api, money } from "@/lib/api";
import type { StorefrontConfig } from "@/lib/api";
import { paymentList, pickupCopy, say, taglineFor } from "@/lib/content";
import Crumbs, { crumbNodes, trail } from "@/lib/crumbs";
import type { Lang } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { tf } from "@/lib/i18n.facts";
import { mailNotice } from "@/lib/i18n.mail";
import { shipPhrase, shipPhraseInline, tp } from "@/lib/i18n.pages";
import { PICKUP_UNKNOWN } from "@/lib/i18n.pickup";
import { buildMetadata, canonicalFor, pickupPlace } from "@/lib/seo";

export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }): Promise<Metadata> {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  // A search snippet is read where the rest of the page cannot be, so the pickup
  // half of the description is printed only while the checkout takes a pickup
  // order. The config call is the cached one the page below makes anyway.
  const cfg = await api.config().catch(() => null);
  return buildMetadata({
    lang,
    path: "/about",
    title: t(lang).about.title,
    description: tp(lang).aboutDescription(shipPhraseInline(lang), cfg?.pickup.enabled === true),
    ogSeed: "about",
  });
}

/**
 * The locker section, in the three states the shop can be in.
 *
 * Pickup on: the shipping page's own sentences — what it costs, where the locker
 * is, when it can be reached, what is at the door, and how the one-time code
 * reaches the buyer, which follows whether this deployment can send email.
 * Pickup off: nothing at all, the way the checkout offers nothing at all.
 * Config unreadable: the one line that says which question this page could not
 * answer, matching the shipping line right above it.
 */
function pickupSection(
  lang: Lang,
  cfg: StorefrontConfig | null,
  copy: ReturnType<typeof pickupCopy>,
): [string, React.ReactNode][] {
  const heading = t(lang).about.pickup;
  if (!cfg) return [[heading, <p key="p">{say(lang, PICKUP_UNKNOWN)}</p>]];
  if (!copy) return [];
  return [
    [
      heading,
      <div key="p" className="stack--tight">
        <p>{say(lang, copy.intro)}</p>
        <ul className="stack--tight" style={{ paddingTop: "var(--st)" }}>
          {copy.facts.map((fact) => (
            <li key={fact.label.en}>
              <span className="mono mono--sm muted">{say(lang, fact.label)}</span> {say(lang, fact.value)}
            </li>
          ))}
        </ul>
        <p>{say(lang, copy.code)}</p>
      </div>,
    ],
  ];
}

export default async function About({ params }: { params: Promise<{ lang: string }> }) {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  const d = t(lang);
  const cfg = await api.config().catch(() => null);
  const crumbs = trail(lang, { name: d.about.title, path: "/about" });
  // Delivery, pickup and payment are read from the configuration here, the way
  // the FAQ, the policy pages and checkout already read them. Before this the
  // page promised card payment the checkout does not offer, a tracking email
  // the checkout says it will not send, and a locker reachable "any hour".
  const f = tf(lang);
  const mail = mailNotice(cfg);
  // The locker section is the shipping page's own copy, so /about cannot describe
  // the same locker differently: null means the checkout takes no pickup order and
  // the section is left out altogether. It used to promise a code "you receive"
  // and an address that "comes with the code" on every deployment, including this
  // one, where a PICKUP order is answered "Pickup is not available".
  const pickup = pickupCopy(cfg);
  const pay = paymentList(cfg);
  const sections: [string, React.ReactNode][] = [
    [d.about.sourcing, (
      <div className="stack--tight">
        <p>{d.about.sourcingText}</p>
        <ul className="stack--tight" style={{ paddingTop: "var(--st)" }}>
          <li><StitchMark origin="HANDMADE_UA" lang={lang} /> <span style={{ marginLeft: 6 }}>{d.origin.HANDMADE_UA_desc}</span></li>
          <li><StitchMark origin="MADE_UA" lang={lang} /> <span style={{ marginLeft: 6 }}>{d.origin.MADE_UA_desc}</span></li>
          <li><StitchMark origin="DESIGNED_UA" lang={lang} /> <span style={{ marginLeft: 6 }}>{d.origin.DESIGNED_UA_desc}</span></li>
        </ul>
      </div>
    )],
    [d.about.shipping, <p key="s">{cfg
      ? f.aboutShipping(shipPhrase(lang), money(cfg.shipping.flat_cad, lang), money(cfg.shipping.free_over_cad, lang), mail.email)
      : f.aboutShippingUnknown}</p>],
    ...pickupSection(lang, cfg, pickup),
    [d.about.payment, <p key="pay">{pay ? f.aboutPayment(say(lang, pay)) : f.payNoneSub}</p>],
    [d.about.taxes, <p key="t">{d.about.taxesText(cfg?.tax.configured_provinces || [])}</p>],
  ];
  if (cfg?.contact_email) sections.push([d.about.contact, <p key="c"><a href={`mailto:${cfg.contact_email}`} className="thread-link">{cfg.contact_email}</a></p>]);
  // Who sells: the same block the terms and the privacy notice print.
  sections.push([tb(lang).seller.heading, <SellerBlock key="seller" lang={lang} business={cfg?.business} id="about-seller" />]);
  return (
    <>
      {/* The pickup point is described here, so its Store node belongs here. It
          is published only while the checkout will take a pickup order, and it
          carries the address this page prints: SHOP_PICKUP_ADDRESS_JSON field by
          field when the owner filled that in, and otherwise the line the API
          publishes from PICKUP_ADDRESS. Either setting alone describes the shop;
          neither one, and there is no node and nothing is claimed. */}
      <JsonLd
        id="ld-about"
        data={[
          breadcrumbList(crumbNodes(lang, crumbs)),
          localBusiness({
            lang,
            url: canonicalFor(lang, "/about"),
            place: cfg?.pickup.enabled ? pickupPlace(cfg.pickup) : null,
          }),
        ]}
      />
      <section className="canvas band">
        <Crumbs lang={lang} items={crumbs} style={{ marginBottom: "calc(var(--st) * 2)" }} />
        <h1 className="h1" style={{ marginBottom: "calc(var(--st) * 4)" }}>{d.about.title}</h1>
        <div className="split split--5-7">
          <div className="split__a">
            <p className="lede muted sticky">{taglineFor(lang)}</p>
          </div>
          <div className="split__b">
            {sections.map(([h, body]) => (
              <div key={h} className="row-line" style={{ gridTemplateColumns: "minmax(140px, 1fr) 3fr", paddingBlock: "calc(var(--st) * 2)" }}>
                <h2 className="h3">{h}</h2>
                <div className="prose">{body}</div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
