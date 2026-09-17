/**
 * The social card: /og?title=…&seed=…&kicker=…&lang=…
 *
 * 1200×630, drawn as the shop's own object — a counted cross-stitch chart on
 * linen. The right third is a chart region: the 24×24 motif that the product
 * page generates from the same slug, bleeding to the panel edges, with the
 * chart's own counted lines behind it. The left holds the wordmark, the title
 * and one line of place.
 *
 * Fonts: Satori reads ttf/otf/woff, and web/public/fonts holds woff2 only, so
 * the card uses the renderer's built-in face by default. OG_TITLE_FONT_PATH may
 * point at a ttf or otf (Fixel Display, say) to draw the title in the site's own
 * type; a face without Ukrainian Cyrillic would break the Ukrainian cards, so
 * the default is unset. See docs/OWNER-ACTIONS.md.
 *
 * Colours below repeat the tokens in app/globals.css :root. Satori resolves no
 * CSS variables and never sees the stylesheet, so this is the one place in web/
 * that carries the values literally; change a token and change it here too.
 */
import { ImageResponse } from "next/og";
import { generateMotif, motifRows } from "@/lib/motif";
import { isLang } from "@/lib/i18n";
import type { Lang } from "@/lib/i18n";
import { seoText } from "@/lib/i18n.seo";
import { OG_IMAGE_SIZE, siteHost } from "@/lib/seo";

export const dynamic = "force-dynamic";

const INK = "#221E1B";
const LINEN = "#D9D2C1";
const LINEN_BLEACHED = "#E8E3D6";
const THREAD_BLACK = "#2A2320";
const THREAD_RED = "#A11D2B";
const MUTED = "#574F48";
const COUNT_MINOR = "rgba(42,35,32,0.06)";
const COUNT_MAJOR = "rgba(42,35,32,0.14)";

const W = OG_IMAGE_SIZE.width;
const H = OG_IMAGE_SIZE.height;
const CELL = 18; // one stitch on the card
const MOTIF = 24; // the chart is 24 stitches square, as on the product tiles
const PANEL_W = CELL * MOTIF; // 432 — the motif bleeds edge to edge
const PANEL_X = W - PANEL_W;
const MOTIF_Y = (H - PANEL_W) / 2; // 99 — the chart sits centred in the panel
const MARGIN = 72; // six stitches

function esc(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** One path with every line of the chart grid inside the panel. */
function gridPath(step: number): string {
  const parts: string[] = [];
  for (let x = PANEL_X; x <= W; x += step) parts.push(`M${x} 0V${H}`);
  // Rows are counted from the motif's top edge, so the lines meet the stitches.
  for (let y = MOTIF_Y; y <= H; y += step) parts.push(`M${PANEL_X} ${y}H${W}`);
  for (let y = MOTIF_Y - step; y >= 0; y -= step) parts.push(`M${PANEL_X} ${y}H${W}`);
  return parts.join("");
}

/**
 * The whole card as one SVG: ground, chart panel, counted lines, the motif in
 * two threads and a plain rule under the wordmark.
 *
 * The origin stitch-marks (red X, running stitch, dotted square) are absent on
 * purpose: each one states how a specific thing was made, and a card that
 * carries one decoratively would be claiming a provenance it does not know. The
 * red thread appears here only where the motif itself is stitched in red.
 */
function cardSvg(seed: string, label: string): string {
  const rows = motifRows(generateMotif(seed, MOTIF));
  const black: string[] = [];
  const red: string[] = [];
  const PAD = 2.8;
  rows.forEach((row, y) => {
    for (let x = 0; x < row.length; x++) {
      const ch = row[x];
      if (ch === "0") continue;
      const x0 = PANEL_X + x * CELL + PAD;
      const y0 = MOTIF_Y + y * CELL + PAD;
      const x1 = PANEL_X + (x + 1) * CELL - PAD;
      const y1 = MOTIF_Y + (y + 1) * CELL - PAD;
      const d = `M${x0} ${y0}L${x1} ${y1}M${x1} ${y0}L${x0} ${y1}`;
      (ch === "2" || ch === "q" ? red : black).push(d);
    }
  });

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}">
<rect width="${W}" height="${H}" fill="${LINEN}"/>
<rect x="${PANEL_X}" y="0" width="${PANEL_W}" height="${H}" fill="${LINEN_BLEACHED}"/>
<path d="${gridPath(CELL)}" stroke="${COUNT_MINOR}" stroke-width="1" fill="none"/>
<path d="${gridPath(CELL * 10)}" stroke="${COUNT_MAJOR}" stroke-width="1" fill="none"/>
<g fill="none" stroke-width="3.6" stroke-linecap="square">
<path d="${black.join("")}" stroke="${THREAD_BLACK}"/>
<path d="${red.join("")}" stroke="${THREAD_RED}"/>
</g>
<path d="M${MARGIN} 116H${MARGIN + 216}" stroke="${THREAD_BLACK}" stroke-width="2" fill="none"/>
</svg>`;
}

/** Long titles step down through fixed sizes so a card never overflows. */
function titleSize(text: string): number {
  const n = text.length;
  if (n <= 22) return 78;
  if (n <= 38) return 64;
  if (n <= 60) return 52;
  if (n <= 88) return 42;
  return 36;
}

type CardFont = { name: string; data: Buffer };
let fontCache: CardFont | null | undefined;

async function titleFont(): Promise<CardFont | null> {
  if (fontCache !== undefined) return fontCache;
  const path = process.env.OG_TITLE_FONT_PATH;
  if (!path) {
    fontCache = null;
    return null;
  }
  try {
    const { readFile } = await import("node:fs/promises");
    fontCache = { name: "UA Market Card", data: await readFile(path) };
  } catch {
    // A missing or unreadable file falls back to the built-in face rather than
    // failing the card.
    fontCache = null;
  }
  return fontCache;
}

export async function GET(request: Request): Promise<Response> {
  const params = new URL(request.url).searchParams;
  const langParam = params.get("lang") || undefined;
  const lang: Lang = isLang(langParam) ? langParam : "en";
  const words = seoText(lang);

  const title = (params.get("title") || "").trim().slice(0, 120) || words.ogTitleFallback;
  const kicker = (params.get("kicker") || "").trim().slice(0, 80) || words.ogKicker;
  const seed = (params.get("seed") || title).trim().slice(0, 120);

  const svg = `data:image/svg+xml;base64,${Buffer.from(cardSvg(seed, words.ogChartLabel), "utf-8").toString("base64")}`;
  const font = await titleFont();
  const face = font ? { fontFamily: font.name } : {};
  const size = titleSize(title);

  return new ImageResponse(
    (
      <div
        style={{
          display: "flex",
          position: "relative",
          width: `${W}px`,
          height: `${H}px`,
          backgroundColor: LINEN,
          color: INK,
        }}
      >
        <img src={svg} width={W} height={H} style={{ position: "absolute", top: 0, left: 0 }} alt="" />
        <div
          style={{
            display: "flex",
            position: "absolute",
            top: "70px",
            left: `${MARGIN}px`,
            fontSize: "24px",
            letterSpacing: "0.04em",
            color: INK,
            ...face,
          }}
        >
          UA MARKET
        </div>
        <div
          style={{
            display: "flex",
            position: "absolute",
            bottom: "148px",
            left: `${MARGIN}px`,
            width: `${PANEL_X - MARGIN * 2}px`,
            fontSize: `${size}px`,
            lineHeight: 1.08,
            letterSpacing: "-0.02em",
            color: INK,
            ...face,
          }}
        >
          {title}
        </div>
        <div
          style={{
            display: "flex",
            position: "absolute",
            bottom: "72px",
            left: `${MARGIN}px`,
            width: `${PANEL_X - MARGIN * 2}px`,
            fontSize: "22px",
            lineHeight: 1.3,
            color: MUTED,
            ...face,
          }}
        >
          {kicker}
        </div>
        <div
          style={{
            display: "flex",
            position: "absolute",
            bottom: "72px",
            left: `${MARGIN}px`,
            width: `${PANEL_X - MARGIN * 2}px`,
            justifyContent: "flex-end",
            fontSize: "20px",
            lineHeight: 1.3,
            letterSpacing: "0.02em",
            color: MUTED,
            ...face,
          }}
        >
          {siteHost()}
        </div>
      </div>
    ),
    {
      width: W,
      height: H,
      headers: {
        "cache-control":
          process.env.NODE_ENV === "development"
            ? "no-store"
            : "public, max-age=600, s-maxage=86400, stale-while-revalidate=604800",
      },
      ...(font ? { fonts: [{ name: font.name, data: font.data, weight: 400 as const, style: "normal" as const }] } : {}),
    },
  );
}
