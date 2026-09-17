import type { Metadata } from "next";
import Link from "next/link";
import TestPayButton from "@/components/TestPayButton";
import { api, money } from "@/lib/api";
import type { TestPaymentSession } from "@/lib/api";
import type { Lang } from "@/lib/i18n";
import { href } from "@/lib/i18n";
import { to } from "@/lib/i18n.order";

/**
 * The local stand-in for a card checkout (PAYMENT_PROVIDER=fake). The API decides whether
 * the session exists; on any deployment without the fake provider it never does, and this
 * page only says so.
 */
export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }): Promise<Metadata> {
  const { lang } = await params;
  return { title: to(lang as Lang).testPage.title, robots: { index: false, follow: false } };
}

export default async function TestPayPage({ params }: { params: Promise<{ lang: string; session: string }> }) {
  const { lang: raw, session } = await params;
  const lang = raw as Lang;
  const p = to(lang).testPage;
  let info: TestPaymentSession | null = null;
  try {
    info = await api.testPayment(session);
  } catch {
    info = null;
  }
  // The order's key is in the cookie checkout set, so the address carries the number only.
  const orderHref = info ? `${href(lang, `/order/${info.order_number}`)}?${info.paid ? "paid=1" : "from=pay"}` : null;
  return (
    <section className="canvas band">
      <div className="split">
        <div className="split__a stack--loose">
          <div className="stack--tight">
            <h1 className="h1">{p.title}</h1>
            <p className="lede measure">{p.lede}</p>
          </div>
          {!info ? <p className="notice notice--warn">{p.missing}</p> : null}
        </div>
        {info && orderHref ? (
          <div className="split__b">
            <div className="receipt stack--tight" data-test-pay-page>
              <div className="receipt__row"><span>{p.order}</span><span>{info.order_number}</span></div>
              <div className="receipt__row receipt__row--total"><span>{p.amount}</span><span>{money(info.amount_cad, lang)}</span></div>
              {info.paid ? (
                <div className="stack--tight" style={{ marginTop: "var(--st)" }}>
                  <p className="status status--ok">{p.paid}</p>
                  <p><Link href={orderHref} className="btn btn--red btn--wide">{p.toOrder} →</Link></p>
                </div>
              ) : (
                <div style={{ marginTop: "calc(var(--st) * 2)" }}>
                  <TestPayButton lang={lang} session={session} amount={money(info.amount_cad, lang)} orderHref={`${href(lang, `/order/${info.order_number}`)}?paid=1`} />
                </div>
              )}
            </div>
            <div className="receipt__tear" />
          </div>
        ) : null}
      </div>
    </section>
  );
}
