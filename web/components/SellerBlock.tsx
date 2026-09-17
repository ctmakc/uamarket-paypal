import type { BusinessIdentity } from "@/lib/api";
import { shopPolicy } from "@/lib/content";
import type { Lang } from "@/lib/i18n";
import { pick } from "@/lib/i18n";
import { tb } from "@/lib/i18n.buy";

/**
 * Who sells, printed on the terms, the privacy notice and "How it works": the registered
 * name, the business address, the contact and privacy addresses and the GST/HST number,
 * each read from settings (/v1/storefront/config `business`). A value the owner has not
 * given says "not published yet" in its place; nothing is filled in for them.
 */
export default function SellerBlock({ lang, business, id = "seller" }: { lang: Lang; business: BusinessIdentity | null | undefined; id?: string }) {
  const s = tb(lang).seller;
  const policy = shopPolicy();
  const legal = business?.legal_name ? pick(lang, business.legal_name, business.legal_name_uk) : null;
  const rows: [string, string | null, "mail" | "text"][] = [
    [s.legalName, legal ?? s.tradingName(pick(lang, policy.seller.en, policy.seller.uk)), "text"],
    [s.address, business?.address ?? null, "text"],
    [s.contact, business?.contact_email ?? null, "mail"],
    [s.privacy, business?.privacy_email ?? business?.contact_email ?? null, "mail"],
  ];
  if (business?.gst_number) rows.push([s.gst, business.gst_number, "text"]);
  return (
    <section className="seller plate" aria-labelledby={`${id}-h`} data-seller-block>
      <h2 className="eyebrow" id={`${id}-h`}>{s.heading}</h2>
      <dl className="seller__rows">
        {rows.map(([label, value, kind]) => (
          <div key={label} className="seller__row">
            <dt className="mono mono--sm muted">{label}</dt>
            <dd>
              {value === null ? (
                <span className="mono mono--sm unpublished">{s.unpublished}</span>
              ) : kind === "mail" ? (
                <a href={`mailto:${value}`} className="thread-link">{value}</a>
              ) : (
                value
              )}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
