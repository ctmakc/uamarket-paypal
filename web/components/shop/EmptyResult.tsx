/**
 * The end of a filter combination that matches nothing.
 *
 * Instead of a dead end it offers the nearest wider views — this same view
 * with one filter taken off — and says how many pieces each of them holds.
 * The counts are read from the catalogue at request time, so a suggestion is
 * only offered when it really has something in it.
 */
import Link from "next/link";
import type { Lang } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { tb } from "@/lib/i18n.buy";
import { ts } from "@/lib/i18n.shop";

/** A wider view worth offering: what it is called, where it is, how big it is. */
export type Suggestion = { key: string; label: string; href: string; count: number };

export default function EmptyResult({ lang, suggestions, shelf }: { lang: Lang; suggestions: Suggestion[]; /** The closest category to a search that found nothing. */ shelf?: { label: string; href: string } | null }) {
  const d = t(lang);
  const s = ts(lang);
  const b = tb(lang);
  return (
    <div className="plate stack" style={{ marginTop: "calc(var(--st) * 2)" }} data-empty-result>
      <p className="lede">{shelf ? b.suggestLead : d.shop.empty}</p>
      {shelf ? (
        <p className="ui" data-shelf-suggestion>
          <span className="muted">{b.suggestShelf}: </span>
          <Link href={shelf.href} className="thread-link thread-link--on">{shelf.label} →</Link>
        </p>
      ) : null}
      {suggestions.length > 0 ? (
        <div className="stack--tight">
          <p className="ui muted">{s.emptyWider}</p>
          <ul style={{ display: "grid", gap: "var(--st)" }}>
            {suggestions.map((x) => (
              <li key={x.key} style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "var(--st)" }}>
                <Link href={x.href} className="thread-link thread-link--on ui">
                  {x.label}
                </Link>
                <span className="mono mono--sm muted">{s.withCount(x.count)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
