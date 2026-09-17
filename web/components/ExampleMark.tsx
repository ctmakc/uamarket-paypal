import type { Lang } from "@/lib/i18n";
import { t } from "@/lib/i18n";

/**
 * The mark every maker name carries while the catalogue is the seeded one.
 *
 * The seven workshops in the demonstration catalogue are written, not found:
 * "Kosiv Thread Workshop, Kosiv, since 2009" has the shape of a business that
 * could be looked up, and a visitor who sees the name on a tile has no way to
 * know it was invented. The demo strip at the top of the page says the goods
 * are sample data; it scrolls away, and it says nothing about the workshop
 * whose name sits under the price. So the name carries the word itself.
 *
 * No new colour, no radius, no chip: a Fira Mono 12 line in `--muted` inside a
 * dashed `--count-major` rule, the same dashed rule the chart keys and the
 * provenance rows already use (DESIGN.md). On `--ink-plate` it switches to the
 * plate's muted pair.
 */
export default function ExampleMark({ lang, plate = false, className = "" }: { lang: Lang; plate?: boolean; className?: string }) {
  return (
    <span className={`example-mark${plate ? " example-mark--plate" : ""} ${className}`.trim()} data-example-mark>
      {t(lang).makers.example}
    </span>
  );
}

/** The same fact as one word, for a line that is a single mono cell (a tile selvedge, a bag line). */
export function exampleWord(lang: Lang): string {
  return t(lang).makers.exampleShort;
}
