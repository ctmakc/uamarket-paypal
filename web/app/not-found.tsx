import Link from "next/link";
import "./globals.css";
import { tu } from "@/lib/i18n.ui";
import { t } from "@/lib/i18n";

/**
 * The last-resort 404, for an address that never reaches a language segment.
 *
 * app/[lang]/[...rest] catches everything the proxy rewrites, so this page is
 * reached only by a request the proxy passes through and no route claims. It
 * carries its own <html lang> because there is no root layout above it, and it
 * offers the two doors a lost visitor wants.
 */
export default function RootNotFound() {
  const d = t("en");
  const u = tu("en");
  return (
    <html lang="en">
      <body>
        <main id="main">
          <section className="canvas band--tall">
            <div className="stack">
              <p className="eyebrow">{u.notFound.code}</p>
              <h1 className="h1">{u.notFound.title}</h1>
              <p className="lede">{u.notFound.body}</p>
              <div className="cta-row">
                <Link href="/shop" className="btn btn--red btn--lg">{u.notFound.shop}</Link>
                <Link href="/makers" className="thread-link ui">{u.notFound.makers} →</Link>
                <Link href="/" className="thread-link ui">{d.brand} →</Link>
              </div>
            </div>
          </section>
        </main>
      </body>
    </html>
  );
}
