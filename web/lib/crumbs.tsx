/**
 * The breadcrumb row, in the design's own language.
 *
 * A trail is a list of locale-free paths, which is all two consumers need: the
 * visible row (mono eyebrow, thread-link steps, slash separators — no new CSS
 * class, no new component style) and the BreadcrumbList node that
 * `breadcrumbList()` in components/JsonLd.tsx turns into structured data. Both
 * read the same array, so the marked-up trail is always the trail on screen.
 *
 * This lives in lib/ rather than components/ because components/ is owned by
 * another agent this phase.
 */
import { Fragment } from "react";
import Link from "next/link";
import type { Lang } from "@/lib/i18n";
import { href } from "@/lib/i18n";
import { tp } from "@/lib/i18n.pages";
import { urlFor } from "@/lib/seo";

/** One step: a name and the locale-free path it points at. */
export type Crumb = { name: string; path: string };

/** A trail that starts at the home page, as every trail on this site does. */
export function trail(lang: Lang, ...steps: Crumb[]): Crumb[] {
  return [{ name: tp(lang).home, path: "/" }, ...steps];
}

/** The same steps as absolute URLs, for breadcrumbList(). */
export function crumbNodes(lang: Lang, items: Crumb[]): { name: string; url: string }[] {
  return items.map((c) => ({ name: c.name, url: urlFor(lang, c.path) }));
}

export default function Crumbs({
  lang,
  items,
  plate = false,
  style,
}: {
  lang: Lang;
  items: Crumb[];
  /** Set on the dark maker band, where muted text needs its own token. */
  plate?: boolean;
  style?: React.CSSProperties;
}) {
  if (items.length === 0) return null;
  return (
    <nav
      className="eyebrow"
      aria-label={tp(lang).crumbLabel}
      style={{ ...(plate ? { color: "var(--muted-on-plate)" } : null), ...style }}
    >
      {items.map((c, i) => {
        const last = i === items.length - 1;
        return (
          <Fragment key={`${c.path}-${i}`}>
            {i > 0 ? <span aria-hidden="true"> / </span> : null}
            {last ? (
              <span aria-current="page">{c.name}</span>
            ) : (
              <Link href={href(lang, c.path)} className="thread-link tap">
                {c.name}
              </Link>
            )}
          </Fragment>
        );
      })}
    </nav>
  );
}
