import { generateMotif, motifRows } from "@/lib/motif";

type Props = {
  seed: string;
  /** 'tile' = 60% stitched, planned rows faint (complete on hover); 'complete' = all stitched; 'hero' = stitches in row by row */
  mode?: "tile" | "complete" | "hero";
  size?: number;
  className?: string;
  /** colour of the ground lines behind stitches */
  plate?: boolean;
  title?: string;
  /** inside an element that already carries its own accessible name */
  decorative?: boolean;
  /**
   * Stitches left unworked in the top-left corner, the way an embroiderer keeps
   * a corner clear for a signature. A product tile draws its provenance mark
   * there, and on a five-block tile the motif's own stitches ran straight
   * through it: the red × was unreadable against a mass of red and black
   * stitches, and that mark is the shop's whole provenance system.
   */
  reserve?: number;
};

const CELL = 10;
/** Thread and state, in draw order: black behind, red on top, planned last. */
const GROUPS = [
  { red: false, planned: false },
  { red: true, planned: false },
  { red: false, planned: true },
  { red: true, planned: true },
];
const PAD = 1.6;

/**
 * A cross-stitch chart as inline SVG. Each stitch is an X drawn with two
 * strokes; black and red threads use the tokens via currentColor / CSS vars.
 */
export default function Motif({ seed, mode = "tile", size = 24, className = "", plate = false, title, decorative = false, reserve = 0 }: Props) {
  const m = generateMotif(seed, size);
  const rows = motifRows(m);
  const dim = size * CELL;
  const red = plate ? "var(--thread-red-lit)" : "var(--thread-red)";
  const black = plate ? "var(--thread-white)" : "var(--thread-black)";
  const gridColor = plate ? "var(--count-minor-on-plate)" : "var(--count-minor)";
  const majorColor = plate ? "var(--count-major-on-plate)" : "var(--count-major)";

  const stitches: { x: number; y: number; red: boolean; planned: boolean }[] = [];
  rows.forEach((row, y) => {
    for (let x = 0; x < row.length; x++) {
      const ch = row[x];
      if (ch === "0") continue;
      if (reserve > 0 && x < reserve && y < reserve) continue;
      stitches.push({ x, y, red: ch === "2" || ch === "q", planned: ch === "p" || ch === "q" });
    }
  });

  /** One cross, in user units. */
  const cross = (x: number, y: number) => {
    const x0 = x * CELL + PAD, y0 = y * CELL + PAD, x1 = (x + 1) * CELL - PAD, y1 = (y + 1) * CELL - PAD;
    return `M${x0} ${y0}L${x1} ${y1}M${x1} ${y0}L${x0} ${y1}`;
  };

  // hero: rows animate in with delays; red pass first, then black
  const delayFor = (s: { y: number; red: boolean }) => {
    if (mode !== "hero") return undefined;
    const rowDelay = (s.y / size) * 0.7;
    return `${(s.red ? 0 : 0.7) + rowDelay}s`;
  };

  return (
    <svg
      viewBox={`0 0 ${dim} ${dim}`}
      className={`motif ${mode === "complete" ? "motif--complete" : ""} ${mode === "hero" ? "motif--hero" : ""} ${className}`}
      role={decorative ? "presentation" : "img"}
      aria-hidden={decorative || undefined}
      aria-label={decorative ? undefined : title || "Cross-stitch chart"}
      shapeRendering="geometricPrecision"
    >
      {title ? <title>{title}</title> : null}
      <defs>
        <pattern id={`g-${seed}`} width={CELL} height={CELL} patternUnits="userSpaceOnUse">
          <path d={`M ${CELL} 0 L 0 0 0 ${CELL}`} fill="none" stroke={gridColor} strokeWidth="1" />
        </pattern>
        <pattern id={`G-${seed}`} width={CELL * 10} height={CELL * 10} patternUnits="userSpaceOnUse">
          <path d={`M ${CELL * 10} 0 L 0 0 0 ${CELL * 10}`} fill="none" stroke={majorColor} strokeWidth="1" />
        </pattern>
      </defs>
      <rect width={dim} height={dim} fill={`url(#g-${seed})`} />
      <rect width={dim} height={dim} fill={`url(#G-${seed})`} />
      <g strokeWidth="2.2" strokeLinecap="square" fill="none">
        {mode === "hero"
          ? // The hero embroiders itself row by row, so every stitch needs its own delay
            // and therefore its own element. It is one motif on one page.
            stitches.map((s) => (
              <path
                key={`${s.x}-${s.y}`}
                d={cross(s.x, s.y)}
                stroke={s.red ? red : black}
                className={`${s.planned ? "planned" : "stitched"} hero-stitch`}
                style={{ animationDelay: delayFor(s) }}
              />
            ))
          : // Everywhere else the four groups (thread × stitched/planned) are drawn as four
            // paths instead of one per stitch. A shop page carries a dozen of these charts:
            // per-stitch elements put 2,800 SVG nodes on the shop listing, and the picture
            // is identical either way.
            GROUPS.map(({ red: isRed, planned }) => {
              const d = stitches
                .filter((s) => s.red === isRed && s.planned === planned)
                .map((s) => cross(s.x, s.y))
                .join("");
              if (!d) return null;
              return (
                <path
                  key={`${isRed ? "r" : "b"}${planned ? "p" : "s"}`}
                  d={d}
                  stroke={isRed ? red : black}
                  className={planned ? "planned" : "stitched"}
                />
              );
            })}
      </g>
    </svg>
  );
}
