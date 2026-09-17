"use client";

import { usePathname, useSearchParams } from "next/navigation";
import type { Lang } from "@/lib/i18n";
import { t } from "@/lib/i18n";

/**
 * Same page, other language. English is unprefixed; Ukrainian is /uk/... .
 * The query string travels with the switch, so a filtered or searched shop page
 * stays filtered when the reader changes language.
 *
 * A plain anchor, on purpose: the two languages are two root layouts (<html lang>), so the
 * switch is a full page load either way. A <Link> prefetched the other language's RSC
 * payload from inside this one, the router could not apply it to the current root, and it
 * asked again, about fifty times a second, for as long as the page stayed open.
 */
export default function LangSwitch({ lang, className = "thread-link", onNavigate }: { lang: Lang; className?: string; onNavigate?: () => void }) {
  const pathname = usePathname() || "/";
  const params = useSearchParams();
  const query = params?.toString() ?? "";
  const bare = pathname.replace(/^\/(uk|en)(?=\/|$)/, "") || "/";
  const path = lang === "en" ? (bare === "/" ? "/uk" : `/uk${bare}`) : bare;
  const target = query ? `${path}?${query}` : path;
  const other: Lang = lang === "en" ? "uk" : "en";
  return (
    <a href={target} className={className} lang={other} hrefLang={other} onClick={onNavigate}>
      {t(lang).nav.lang}
    </a>
  );
}
