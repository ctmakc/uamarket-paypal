/**
 * Procedural cross-stitch motif, generated deterministically from a product slug.
 *
 * A 24×24 chart with four-fold symmetry (mirrored across both axes) built from
 * a 12×12 quadrant that is itself mirrored across its diagonal, so every motif
 * has the eight-fold regularity of a real geometric embroidery pattern.
 * Cells are 0 (empty), 1 (black thread) or 2 (red thread). A deterministic
 * subset of cells is "planned" (drawn faint) so a tile reads as work in progress
 * and completes on hover.
 */

export type Cell = 0 | 1 | 2;
export type Motif = { size: number; cells: Cell[][]; planned: boolean[][] };

function hash(str: string): number {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function rng(seed: number) {
  let s = seed || 1;
  return () => {
    s ^= s << 13; s >>>= 0;
    s ^= s >>> 17;
    s ^= s << 5; s >>>= 0;
    return (s >>> 0) / 4294967296;
  };
}

export function generateMotif(seed: string, size = 24): Motif {
  const half = size / 2;
  const rand = rng(hash(seed));
  // quadrant, diagonal-symmetric
  const q: Cell[][] = Array.from({ length: half }, () => Array<Cell>(half).fill(0));
  const density = 0.34 + rand() * 0.14;
  const redShare = 0.28 + rand() * 0.3;
  for (let y = 0; y < half; y++) {
    for (let x = y; x < half; x++) {
      // structure: rings + diagonals + noise, so it looks charted, not random
      const ring = Math.max(half - 1 - x, half - 1 - y);
      const onRing = ring % 3 === 0 && rand() < 0.75;
      const onDiag = x === y && rand() < 0.8;
      const noise = rand() < density * 0.55;
      let v: Cell = onRing || onDiag || noise ? 1 : 0;
      if (v && rand() < redShare) v = 2;
      q[y][x] = v;
      q[x][y] = v;
    }
  }
  // smoothing pass: kill isolated single stitches (real charts are clumps)
  for (let y = 0; y < half; y++) for (let x = 0; x < half; x++) {
    if (!q[y][x]) continue;
    let n = 0;
    for (const [dy, dx] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
      const yy = y + dy, xx = x + dx;
      if (yy >= 0 && yy < half && xx >= 0 && xx < half && q[yy][xx]) n++;
    }
    if (n === 0 && rand() < 0.7) q[y][x] = 0;
  }
  // centre medallion so the motif always has a heart
  const c = half - 1;
  q[c][c] = 2; q[c - 1][c] = q[c][c - 1] = 1; q[c - 1][c - 1] = 2;

  const cells: Cell[][] = Array.from({ length: size }, () => Array<Cell>(size).fill(0));
  const planned: boolean[][] = Array.from({ length: size }, () => Array<boolean>(size).fill(false));
  const plannedFrom = Math.floor(size * 0.6); // the lower 40% of rows are still planned
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const qy = y < half ? half - 1 - y : y - half;
    const qx = x < half ? half - 1 - x : x - half;
    cells[y][x] = q[qy][qx];
    planned[y][x] = y >= plannedFrom;
  }
  return { size, cells, planned };
}

/** Compact string form for the SVG component: one char per cell (0/1/2, p/q for planned). */
export function motifRows(m: Motif): string[] {
  return m.cells.map((row, y) => row.map((v, x) => {
    if (!v) return "0";
    return m.planned[y][x] ? (v === 2 ? "q" : "p") : String(v);
  }).join(""));
}
