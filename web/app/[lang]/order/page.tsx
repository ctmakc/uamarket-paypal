import type { Metadata } from "next";
import { api } from "@/lib/api";
import type { Lang } from "@/lib/i18n";
import { href, t } from "@/lib/i18n";
import { MAIL_OFF, mailNotice } from "@/lib/i18n.mail";
import { tb } from "@/lib/i18n.buy";
import { tp } from "@/lib/i18n.pages";
import { tu } from "@/lib/i18n.ui";
import { buildMetadata } from "@/lib/seo";

/**
 * The lookup form takes an order number and an email, and the page it opens is
 * one customer's own order, so neither is offered to an index.
 */
export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }): Promise<Metadata> {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  return buildMetadata({
    lang,
    path: "/order",
    title: t(lang).order.lookup,
    description: tp(lang).orderLookupDescription,
    robots: { index: false, follow: false },
  });
}

export default async function OrderLookup({ params, searchParams }: { params: Promise<{ lang: string }>; searchParams: Promise<{ number?: string; missing?: string; busy?: string; down?: string }> }) {
  const { lang: raw } = await params;
  const lang = raw as Lang;
  const d = t(lang);
  const u = tu(lang);
  const b = tb(lang);
  const sp = await searchParams;
  // The shared lookup line tells the customer to take the number "from your
  // email". While the shop sends none, the sibling order page and the checkout
  // both say so and this page has to agree.
  let mail = MAIL_OFF;
  try {
    mail = mailNotice(await api.config());
  } catch {
    mail = MAIL_OFF;
  }
  const failed = Boolean(sp.missing || sp.busy || sp.down);
  const failure = sp.busy ? b.lookupBusy : sp.down ? b.lookupDown : d.order.notFound;
  return (
    <section className="canvas band">
      <div className="split">
        <div className="split__a stack">
          <h1 className="h1">{d.order.lookup}</h1>
          <p className="lede muted">{mail.email ? d.order.lookupSub : u.orderLookupNoEmail}</p>
          {/* The message is described to both fields it is about, and the
              number field takes the focus, because a live region that is
              already in the page when it loads announces nothing. */}
          {failed ? <p className="error" id="lookup-error">{failure}</p> : null}
          {/* POST: the number and the email travel in the body, and the order page that
              opens carries neither in its address. */}
          <form method="post" action="/api/order/lookup" className="stack" style={{ maxWidth: 480 }}>
            <input type="hidden" name="lang" value={lang} />
            <div className="field">
              <label className="field__label" htmlFor="number">{d.order.number}</label>
              <input
                id="number"
                name="number"
                className="input mono"
                placeholder="UA-260902-XXXX"
                defaultValue={sp.number || ""}
                aria-invalid={failed || undefined}
                aria-describedby={failed ? "lookup-error" : undefined}
                autoFocus={failed}
                required
              />
            </div>
            <div className="field">
              <label className="field__label" htmlFor="email">{d.checkout.email}</label>
              <input
                id="email"
                name="email"
                type="email"
                className="input"
                autoComplete="email"
                aria-invalid={failed || undefined}
                aria-describedby={failed ? "lookup-error" : undefined}
                required
              />
            </div>
            <p><button type="submit" className="btn btn--red">{d.order.find}</button></p>
          </form>
        </div>
      </div>
    </section>
  );
}
