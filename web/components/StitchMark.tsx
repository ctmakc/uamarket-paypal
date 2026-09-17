import type { Lang } from "@/lib/i18n";
import { t } from "@/lib/i18n";

type Origin = "HANDMADE_UA" | "MADE_UA" | "DESIGNED_UA";

/**
 * The three provenance marks: red X, black running stitch, dotted square.
 * On a product tile the mark is the only statement of provenance, so it is
 * announced as an image with its label rather than left to a title tooltip.
 */
export default function StitchMark({ origin, lang, withLabel = false, className = "" }: { origin: Origin; lang: Lang; withLabel?: boolean; className?: string }) {
  const label = t(lang).origin[origin];
  let glyph;
  if (origin === "HANDMADE_UA") {
    glyph = (
      <svg className={`mark mark--x ${className}`} viewBox="0 0 14 14" aria-hidden="true">
        <path d="M2 2 L12 12 M12 2 L2 12" stroke="currentColor" strokeWidth="2.2" strokeLinecap="square" fill="none" />
      </svg>
    );
  } else if (origin === "MADE_UA") {
    glyph = (
      <svg className={`mark mark--run ${className}`} viewBox="0 0 14 14" aria-hidden="true">
        <path d="M0 7 H4 M6 7 H10 M12 7 H14" stroke="currentColor" strokeWidth="2.2" fill="none" />
      </svg>
    );
  } else {
    glyph = (
      <svg className={`mark mark--dot ${className}`} viewBox="0 0 14 14" aria-hidden="true">
        <rect x="1.5" y="1.5" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="1.6" strokeDasharray="2 2" />
      </svg>
    );
  }
  if (!withLabel) return <span role="img" aria-label={label} title={label}>{glyph}</span>;
  // A labelled mark takes the type of whatever it sits in — a filter chip is
  // set in the shop's UI face like every other chip, so the mark must not drag
  // a mono 12px run in with it.
  return (
    <>
      {glyph}
      <span>{label}</span>
    </>
  );
}
