/**
 * What is being filtered right now, as chips that take themselves off.
 *
 * Each chip is a link to the same view with that one filter dropped, so the
 * back button, a shared link and a browser with no JavaScript all behave the
 * same. The last link clears everything and lands on the plain shop.
 */
import Link from "next/link";
import type { Lang } from "@/lib/i18n";
import { ts } from "@/lib/i18n.shop";
import UnpickMark from "./UnpickMark";

/** One active filter: what it says, and where "remove me" points. */
export type ActiveChip = { key: string; label: string; href: string };

export default function ActiveFilters({
  lang,
  chips,
  clearHref,
  anyFilter = false,
}: {
  lang: Lang;
  chips: ActiveChip[];
  clearHref: string;
  /** True when any filter at all is on, including the ones with their own rail. */
  anyFilter?: boolean;
}) {
  const s = ts(lang);
  if (chips.length === 0 && !anyFilter) return null;
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: "var(--st)",
        paddingBlock: "var(--st)",
        borderBottom: "1px dashed var(--count-major)",
      }}
    >
      <span id="filter-active" className="mono mono--sm muted" style={{ minWidth: "calc(var(--blk) * 0.8)" }}>
        {chips.length > 0 ? s.activeFilters : ""}
      </span>
      <div className="swatches" role="group" aria-labelledby="filter-active">
        {chips.map((c) => (
          <Link
            key={c.key}
            href={c.href}
            className="chip on-plate"
            data-on="true"
            aria-label={s.remove(c.label)}
          >
            <span>{c.label}</span>
            <UnpickMark />
          </Link>
        ))}
        <Link href={clearHref} className="thread-link ui">
          {s.clearAll}
        </Link>
      </div>
    </div>
  );
}
