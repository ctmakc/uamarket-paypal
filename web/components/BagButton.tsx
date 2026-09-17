"use client";

import Link from "next/link";
import { useBag } from "@/lib/bag";
import type { Lang } from "@/lib/i18n";
import { href, t } from "@/lib/i18n";
import { tu } from "@/lib/i18n.ui";

/**
 * The bag reads from localStorage, so the count is 0 until hydration. An empty
 * bag shows the word alone; a filled one adds the count in an inverted cell, so
 * the state is legible without reading the number.
 */
export default function BagButton({ lang }: { lang: Lang }) {
  const items = useBag();
  const count = items.reduce((n, i) => n + i.qty, 0);
  const d = t(lang);
  const u = tu(lang);
  return (
    <Link href={href(lang, "/bag")} className="hdr__bag" data-count={count} aria-label={u.bagCount(count)}>
      <span>{d.nav.bag}</span>
      {count > 0 ? <span className="hdr__count" aria-hidden="true">{count}</span> : null}
    </Link>
  );
}
