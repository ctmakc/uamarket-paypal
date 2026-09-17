import type { Lang } from "@/lib/i18n";
import { tu } from "@/lib/i18n.ui";

/**
 * One line, above the footer of every page, while the shop carries the seeded
 * assortment.
 *
 * /llms.txt, /llms-full.txt and /api/catalog have always opened by naming the
 * catalogue as demonstration data; no page a person reads said it, so a shopper
 * and an answer engine were told two different things about the same twenty-one
 * products. This says the same sentence to both.
 *
 * The row is a plain ruled band on the linen ground: no red, because the accent
 * is already spent on the page above it, and no icon.
 */
export default function PlaceholderNotice({ lang }: { lang: Lang }) {
  const u = tu(lang);
  return (
    <aside className="canvas" style={{ paddingBlock: "calc(var(--st) * 2)" }}>
      <p className="mono mono--sm muted measure" style={{ borderTop: "1px dashed var(--count-major)", paddingTop: "var(--st)" }}>
        {u.placeholder}
      </p>
    </aside>
  );
}
