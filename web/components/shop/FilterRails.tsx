/**
 * The two filter rails the catalogue API does not carry: provenance and price.
 *
 * Both are links. Clicking one adds its parameter to the URL, clicking the
 * active one takes it off again, and every one of them is a real href — the
 * page works with JavaScript switched off.
 *
 * Provenance wears its own stitch mark, the same three marks the product tiles
 * and the footer legend use, so the filter and the goods speak one language.
 */
import Link from "next/link";
import StitchMark from "@/components/StitchMark";
import type { Lang } from "@/lib/i18n";
import { amount, plainAmount, ts } from "@/lib/i18n.shop";
import FilterRow from "./FilterRow";
import type { PriceBand, ShopQuery } from "./query";
import { ORIGINS, priceBands, qs } from "./query";

/** "Under CA$ 50", "CA$ 50–120", "CA$ 250 and up". */
export function bandLabel(band: PriceBand, lang: Lang): string {
  const s = ts(lang);
  if (band.min === null && band.max !== null) return s.priceUnder(amount(band.max, lang));
  if (band.max === null && band.min !== null) return s.priceFrom(amount(band.min, lang));
  if (band.min !== null && band.max !== null) return s.priceBetween(amount(band.min, lang), plainAmount(band.max, lang));
  return "";
}

export default function FilterRails({ lang, base, current }: { lang: Lang; base: string; current: ShopQuery }) {
  const s = ts(lang);
  const bands = priceBands();
  return (
    <>
      <FilterRow id="filter-origin" label={s.origin}>
        {ORIGINS.map((o) => {
          const on = current.origin === o.id;
          return (
            <Link
              key={o.id}
              href={`${base}${qs(current, { origin: on ? undefined : o.id })}`}
              className={`chip${on ? " on-plate" : ""}`}
              aria-current={on ? "true" : undefined}
            >
              <StitchMark origin={o.value} lang={lang} withLabel />
            </Link>
          );
        })}
      </FilterRow>

      {bands.length > 0 ? (
        <FilterRow id="filter-price" label={s.price}>
          {bands.map((b) => {
            const on = current.price === b.id;
            return (
              <Link
                key={b.id}
                href={`${base}${qs(current, { price: on ? undefined : b.id })}`}
                className="chip"
                aria-current={on ? "true" : undefined}
                style={{ fontFamily: "var(--face-mono)" }}
              >
                {bandLabel(b, lang)}
              </Link>
            );
          })}
        </FilterRow>
      ) : null}
    </>
  );
}
