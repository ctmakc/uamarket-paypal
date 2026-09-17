import Link from "next/link";
import type { ProductSummary } from "@/lib/api";
import { money } from "@/lib/api";
import { catalogueStatus } from "@/lib/geo";
import type { Lang } from "@/lib/i18n";
import { href, pick, t } from "@/lib/i18n";
import Motif from "./Motif";
import StitchMark from "./StitchMark";

/** The counted tile: media block rows + a selvedge row with name, maker and the price in the last cell. */
export default function ProductTile({ p, lang, span = 4, short = false, eager = false }: { p: ProductSummary; lang: Lang; /** Blocks wide: one of the widths spansFor() produces. */ span?: number; short?: boolean; /** The first tiles above the fold load at once. */ eager?: boolean }) {
  const d = t(lang);
  const title = pick(lang, p.title, p.title_uk);
  const town = p.maker ? pick(lang, p.maker.region, p.maker.region_uk).split(",")[0] : "";
  // The selvedge is one mono cell and clamps at two lines, so the workshop's name
  // carries the short word: "Kosiv Thread Workshop (example) · Kosiv". It sits right
  // after the name, where the clamp cannot cut it off. See components/ExampleMark.
  const madeUp = catalogueStatus() === "placeholder" && !!p.maker;
  const makerName = p.maker ? pick(lang, p.maker.name, p.maker.name_uk) : "";
  const makerLine = p.maker
    ? `${makerName}${madeUp ? ` (${d.makers.exampleShort})` : ""} · ${town}`
    : pick(lang, p.origin_label, p.origin_label_uk);
  const price = p.price_from_cad === p.price_to_cad ? money(p.price_from_cad, lang) : `${d.product.from} ${money(p.price_from_cad, lang)}`;
  const origin = pick(lang, p.origin_label, p.origin_label_uk) || d.origin[p.origin];
  // The link carries its own name, so everything inside it has to be named here.
  const label = [title, madeUp ? `${makerName} — ${d.makers.example}` : null, origin, price, p.in_stock ? null : d.product.soldOut].filter(Boolean).join(", ");
  return (
    <Link href={href(lang, `/product/${p.slug}`)} className={`tile span-${span} chart ${short ? "tile--short" : ""} ${p.in_stock ? "" : "tile--soldout"}`} aria-label={label}>
      <span className="tile__mark" aria-hidden="true">
        <StitchMark origin={p.origin} lang={lang} />
      </span>
      <div className="tile__media">
        {p.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            className="tile__photo"
            src={p.photos?.[0]?.src || p.image_url}
            srcSet={p.photos?.[0]?.srcset || undefined}
            sizes={p.photos?.[0] ? "(max-width: 719px) 50vw, (max-width: 1023px) 50vw, 34vw" : undefined}
            width={p.photos?.[0]?.width}
            height={p.photos?.[0]?.height}
            alt=""
            loading={eager ? "eager" : "lazy"}
            decoding="async"
          />
        ) : (
          <Motif seed={p.slug} mode="tile" className="tile__motif" title={d.product.photoPending} reserve={4} decorative />
        )}
      </div>
      <div className="tile__selvedge" aria-hidden="true">
        <span className="tile__name">{title}</span>
        <span className="tile__maker" title={makerLine}>{makerLine}</span>
        {p.in_stock ? <span className="tile__stock" /> : <span className="tile__stock tile__stock--out">{d.product.soldOut}</span>}
        <span className="tile__price">{price}</span>
      </div>
    </Link>
  );
}

/** 4/3/5 then 5/4/3: the chart band rhythm. */
const BAND: (3 | 4 | 5)[] = [4, 3, 5, 5, 4, 3];

/** How many blocks wide the tile at `index` is, before the tail rule. */
export function spanFor(index: number): 3 | 4 | 5 {
  return BAND[index % BAND.length];
}

/**
 * The widths of a whole grid, with one rule for the tail.
 *
 * Every card grid on the site — the home collections, the makers, the shop,
 * a maker's own pieces — is the same 4/3/5 then 5/4/3 band. A run that does not
 * divide by twelve used to be hand-tuned per page: the home page carried
 * `[4, 3, 5, 5, 7]`, which only balances at exactly five collections, and
 * /makers carried `[4, 3, 5, 5, 4, 3]`, which stranded a seventh maker in a
 * 392px card with 928px of empty linen beside it. One rule replaces both:
 * a last row that does not fill the twelve blocks is spread evenly across it,
 * so one card becomes the full width and two become halves. Complete bands are
 * left alone, so the rhythm survives wherever the run does divide.
 */
export function spansFor(count: number): number[] {
  const rows: number[][] = [];
  let row: number[] = [];
  let width = 0;
  for (let i = 0; i < count; i += 1) {
    const span = spanFor(i);
    if (width + span > 12) { rows.push(row); row = []; width = 0; }
    row.push(span);
    width += span;
  }
  if (row.length) rows.push(row);
  const last = rows[rows.length - 1];
  if (last && last.reduce((a, b) => a + b, 0) < 12) {
    const each = Math.floor(12 / last.length);
    const extra = 12 - each * last.length;
    for (let i = 0; i < last.length; i += 1) last[i] = each + (i < extra ? 1 : 0);
  }
  return rows.flat();
}
