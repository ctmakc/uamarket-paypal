"use client";

import { usePathname } from "next/navigation";
import { langFromPath, tu } from "@/lib/i18n.ui";

/**
 * Placeholders in the counted-chart language: a piece that has not arrived yet
 * is drawn the way an embroiderer draws one — the planned X's of the chart,
 * with the row still unstitched. Nothing here pulses, shimmers or slides; the
 * faint chart already says "not filled in".
 */

/** A symmetric, deterministic field of planned stitches (same on server and client). */
function plannedCells(cols: number, rows: number, variant: number): { x: number; y: number }[] {
  const out: { x: number; y: number }[] = [];
  const a = 3 + (variant % 3);
  const b = 5 + ((variant * 2) % 4);
  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      const h = Math.min(x, cols - 1 - x);
      if ((h * a + y * b + variant) % 7 < 3) out.push({ x, y });
    }
  }
  return out;
}

const CELL = 10;
const PAD = 1.8;

function PlannedChart({ cols = 24, rows = 24, variant = 0, className = "" }: { cols?: number; rows?: number; variant?: number; className?: string }) {
  const cells = plannedCells(cols, rows, variant);
  return (
    <svg className={`sk__chart ${className}`} viewBox={`0 0 ${cols * CELL} ${rows * CELL}`} preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">
      <g strokeWidth="2" strokeLinecap="square" fill="none" stroke="var(--count-major)">
        {cells.map((c) => {
          const x0 = c.x * CELL + PAD, y0 = c.y * CELL + PAD, x1 = (c.x + 1) * CELL - PAD, y1 = (c.y + 1) * CELL - PAD;
          return <path key={`${c.x}-${c.y}`} d={`M${x0} ${y0}L${x1} ${y1}M${x1} ${y0}L${x0} ${y1}`} />;
        })}
      </g>
    </svg>
  );
}

/** A live region that says the page is loading, in the reader's language. */
export function LoadingStatus() {
  const lang = langFromPath(usePathname());
  return <span className="sr-only" role="status">{tu(lang).loading}</span>;
}

/** One tile-shaped placeholder: unstitched chart above, blank selvedge below. */
export function TileSkeleton({ span = 4, short = false, variant = 0 }: { span?: 3 | 4 | 5 | 6; short?: boolean; variant?: number }) {
  return (
    <div className={`tile sk-tile chart span-${span} ${short ? "tile--short" : ""}`} aria-hidden="true">
      <div className="tile__media"><PlannedChart variant={variant} /></div>
      <div className="tile__selvedge">
        <span className="tile__name"><span className="sk__bar sk__bar--name" /></span>
        <span className="tile__maker"><span className="sk__bar sk__bar--maker" /></span>
        <span className="tile__price"><span className="sk__bar sk__bar--price" /></span>
      </div>
    </div>
  );
}

const SPANS: (3 | 4 | 5)[] = [4, 3, 5, 5, 4, 3];

/** The tile grid before its tiles exist. */
export function TileGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="blocks blocks--pairs">
      {Array.from({ length: count }, (_, i) => (
        <TileSkeleton key={i} span={SPANS[i % SPANS.length]} variant={i} />
      ))}
    </div>
  );
}

/** Stand-in rows for a list that is still being read (the bag, an order). */
export function RowsSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="sk-row">
          <span className="sk__bar sk__bar--mark" />
          <span>
            <span className="sk__bar sk__bar--name" />
            <span className="sk__bar sk__bar--maker" />
          </span>
          <span className="sk__bar sk__bar--price" />
        </div>
      ))}
    </div>
  );
}

/** The whole page while the server is still answering. */
export default function PageSkeleton() {
  return (
    <section className="canvas band">
      <LoadingStatus />
      <div className="row-line" style={{ marginBottom: "calc(var(--st) * 3)" }} aria-hidden="true">
        <span className="sk__bar sk__bar--title" />
        <span className="sk__bar sk__bar--maker" />
      </div>
      <TileGridSkeleton count={6} />
    </section>
  );
}
