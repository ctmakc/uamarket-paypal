import type { Lang } from "@/lib/i18n";
import { to } from "@/lib/i18n.order";

/**
 * The first thing on every page while the catalogue is placeholder data.
 *
 * The footer-area line says the same at length; this strip makes sure nobody reaches a
 * price or a Place order button without having seen it. A dark plate band, one mono line,
 * a red running stitch as its only mark. It scrolls away with the page; the header stays.
 */
export default function DemoStrip({ lang }: { lang: Lang }) {
  return (
    <div className="demo-strip" role="note" data-demo-strip>
      <p className="canvas demo-strip__in">
        <svg className="demo-strip__mark" width="24" height="6" viewBox="0 0 24 6" aria-hidden="true">
          <path d="M0 3 H6 M9 3 H15 M18 3 H24" stroke="currentColor" strokeWidth="2" />
        </svg>
        <span className="demo-strip__long">{to(lang).demoStrip}</span>
        <span className="demo-strip__short">{to(lang).demoStripShort}</span>
      </p>
    </div>
  );
}
