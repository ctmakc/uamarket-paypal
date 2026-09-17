/**
 * "UA MARKET" charted in cross-stitches for the footer. A 5×7 pixel alphabet,
 * each on-pixel an X in thread-white on the ink plate; the two letters of UA
 * are stitched in red.
 */
const GLYPHS: Record<string, string[]> = {
  U: ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
  A: ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
  M: ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
  R: ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
  K: ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
  E: ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
  T: ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
  " ": ["000", "000", "000", "000", "000", "000", "000"],
};

export default function WordmarkChart({ text = "UA MARKET" }: { text?: string }) {
  const CELL = 10;
  const PAD = 1.8;
  const letters = text.split("").map((ch) => GLYPHS[ch] || GLYPHS[" "]);
  const widths = letters.map((g) => g[0].length + 1);
  const totalW = widths.reduce((a, b) => a + b, 0) - 1;
  const H = 7;
  const paths: { x: number; y: number; red: boolean }[] = [];
  let cursor = 0;
  letters.forEach((g, li) => {
    // "UA" is stitched in red; the rest of the word in thread-white.
    const red = li < 2;
    g.forEach((row, y) => {
      row.split("").forEach((c, x) => {
        if (c === "1") paths.push({ x: cursor + x, y, red });
      });
    });
    cursor += widths[li];
  });
  return (
    <svg className="wordmark-chart" viewBox={`0 0 ${totalW * CELL} ${H * CELL}`} role="img" aria-label={text} preserveAspectRatio="xMidYMid meet">
      <g strokeWidth="2.2" strokeLinecap="square" fill="none">
        {paths.map((p, i) => {
          const x0 = p.x * CELL + PAD, y0 = p.y * CELL + PAD, x1 = (p.x + 1) * CELL - PAD, y1 = (p.y + 1) * CELL - PAD;
          return <path key={i} d={`M${x0} ${y0}L${x1} ${y1}M${x1} ${y0}L${x0} ${y1}`} stroke={p.red ? "var(--thread-red-lit)" : "var(--thread-white)"} />;
        })}
      </g>
    </svg>
  );
}
