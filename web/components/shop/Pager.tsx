/**
 * Paging with real links.
 *
 * No infinite scroll: it hides the footer, it cannot be shared, and it leaves
 * a crawler with one page. Every page here has its own address, its own
 * canonical URL and a link a browser can follow with JavaScript off. The ends
 * of the run are printed as plain text rather than dead links.
 */
import Link from "next/link";
import type { Lang } from "@/lib/i18n";
import { ts } from "@/lib/i18n.shop";

/** First page, last page, and the current page with a neighbour each side. */
export function pageWindow(page: number, pageCount: number): (number | null)[] {
  const wanted = new Set<number>([1, pageCount, page - 1, page, page + 1]);
  const numbers = [...wanted].filter((n) => n >= 1 && n <= pageCount).sort((a, b) => a - b);
  const out: (number | null)[] = [];
  numbers.forEach((n, i) => {
    if (i > 0 && n - numbers[i - 1] > 1) out.push(null);
    out.push(n);
  });
  return out;
}

const STEP: React.CSSProperties = { whiteSpace: "nowrap" };

export default function Pager({
  lang,
  page,
  pageCount,
  hrefFor,
}: {
  lang: Lang;
  page: number;
  pageCount: number;
  /** Full localized href of one page of this same view. */
  hrefFor: (page: number) => string;
}) {
  const s = ts(lang);
  if (pageCount <= 1) return null;
  return (
    <nav
      aria-label={s.pages}
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: "var(--st)",
        marginTop: "calc(var(--st) * 4)",
        paddingTop: "calc(var(--st) * 2)",
        borderTop: "1px dashed var(--count-major)",
      }}
    >
      {page > 1 ? (
        <Link href={hrefFor(page - 1)} rel="prev" className="thread-link thread-link--on ui tap" aria-label={s.prevLabel} style={STEP}>
          ← {s.prev}
        </Link>
      ) : (
        <span className="ui muted" style={STEP}>
          ← {s.prev}
        </span>
      )}

      <div className="swatches">
        {pageWindow(page, pageCount).map((n, i) =>
          n === null ? (
            <span key={`gap-${i}`} className="mono mono--sm muted" style={{ lineHeight: "36px" }}>
              …
            </span>
          ) : (
            <Link
              key={n}
              href={hrefFor(n)}
              className="chip"
              aria-current={n === page ? "true" : undefined}
              aria-label={s.goToPage(n)}
              style={{ fontFamily: "var(--face-mono)" }}
            >
              {n}
            </Link>
          ),
        )}
      </div>

      {page < pageCount ? (
        <Link href={hrefFor(page + 1)} rel="next" className="thread-link thread-link--on ui tap" aria-label={s.nextLabel} style={STEP}>
          {s.next} →
        </Link>
      ) : (
        <span className="ui muted" style={STEP}>
          {s.next} →
        </span>
      )}

      <span className="mono mono--sm muted" style={{ marginLeft: "auto" }}>
        {s.pageOf(page, pageCount)}
      </span>
    </nav>
  );
}
