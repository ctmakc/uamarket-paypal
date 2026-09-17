"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { href } from "@/lib/i18n";
import { tb } from "@/lib/i18n.buy";
import { langFromPath, tu } from "@/lib/i18n.ui";

const DOWN_DIGEST = "UAM_API_DOWN";

/**
 * The error boundary for every page under /[lang]. It states what happened,
 * offers to run the render again, and shows the digest Next assigns so a
 * reader can quote it to the shop. Nothing here guesses at the cause.
 */
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const lang = langFromPath(usePathname());
  const u = tu(lang);
  // The catalogue could not be read (lib/api ApiDown): say so in the shop's words.
  const down = error.digest === DOWN_DIGEST || error.name === "ApiDown";
  const dn = tb(lang).down;

  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <section className="canvas band--tall">
      <div className="stack measure">
        {down ? null : <p className="eyebrow">{u.error.ref}{error.digest ? `: ${error.digest}` : ""}</p>}
        <h1 className="h1">{down ? dn.title : u.error.title}</h1>
        <p className="lede">{down ? dn.body : u.error.body}</p>
        <div className="cta-row">
          <button type="button" className="btn btn--red btn--lg" onClick={() => reset()}>{u.error.retry}</button>
          <Link href={href(lang, "/shop")} className="thread-link ui">{u.error.shop} →</Link>
        </div>
      </div>
    </section>
  );
}
