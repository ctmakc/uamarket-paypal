/**
 * "The shop is catching up": what a visitor sees while the API cannot be read.
 *
 * proxy.ts asks the API's /health (cached for a few seconds) before it lets a catalogue page
 * render, and answers HTTP 503 with this page when the API is down, so a search engine or a
 * shopper never mistakes an unreachable catalogue for an empty one. The page carries its own
 * styles because the layout that would style it needs the API too.
 */
import type { Lang } from "@/lib/i18n";
import { tb } from "@/lib/i18n.buy";

export const DOWN_DIGEST = "UAM_API_DOWN";

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function catchingUpHtml(lang: Lang, path: string): string {
  const d = tb(lang).down;
  const other = lang === "uk" ? tb("en").down : tb("uk").down;
  return `<!doctype html>
<html lang="${lang === "uk" ? "uk" : "en-CA"}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>${esc(d.title)} · UA Market</title>
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<style>
@font-face{font-family:"Fixel Display";font-weight:600;font-display:swap;src:url("/fonts/FixelDisplay-SemiBold.woff2") format("woff2")}
@font-face{font-family:"Fixel Text";font-weight:400;font-display:swap;src:url("/fonts/FixelText-Regular.woff2") format("woff2")}
@font-face{font-family:"Fira Mono";font-weight:400;font-display:swap;src:url("/fonts/fira-mono-latin-400-normal.woff2") format("woff2");unicode-range:U+0000-00FF}
@font-face{font-family:"Fira Mono";font-weight:400;font-display:swap;src:url("/fonts/fira-mono-cyrillic-400-normal.woff2") format("woff2");unicode-range:U+0400-045F,U+0490-0491}
:root{--linen:#D9D2C1;--bleached:#E8E3D6;--ink:#221E1B;--plate:#1E1A17;--red:#A11D2B;--white:#EFE9DC;--muted:#574F48;--st:12px}
*{box-sizing:border-box}body{margin:0;background:var(--linen);color:var(--ink);font:17px/24px "Fixel Text",system-ui,sans-serif}
.bar{border-bottom:1px solid rgba(42,35,32,.14)}.in{max-width:1440px;margin:0 auto;padding:0 120px}
@media(max-width:1023px){.in{padding:0 24px}}
.mark{display:flex;gap:12px;align-items:center;min-height:72px;font:900 22px/24px "Fixel Display",system-ui,sans-serif;letter-spacing:-.02em;color:var(--ink);text-decoration:none}
main{padding:96px 0}@media(max-width:719px){main{padding:48px 0}}.plate{background:var(--bleached);border-left:3px solid #715608;padding:24px;max-width:62ch}
h1{font:600 clamp(1.75rem,1.15rem + 1.8vw,2.75rem)/1.1 "Fixel Display",system-ui,sans-serif;letter-spacing:-.02em;margin:0 0 24px}
p{margin:0 0 24px}.mono{font:12px/24px "Fira Mono",ui-monospace,monospace;color:var(--muted)}
.btn{display:inline-flex;align-items:center;min-height:60px;padding:0 36px;background:var(--red);color:var(--white);font:500 17px/24px "Fixel Text",system-ui,sans-serif;text-decoration:none}
.btn:hover{background:var(--plate)}:focus-visible{outline:2px solid var(--red);outline-offset:2px}
</style></head>
<body><div class="bar"><div class="in"><a class="mark" href="${lang === "uk" ? "/uk" : "/"}"><svg width="18" height="18" viewBox="0 0 14 14" aria-hidden="true" style="color:var(--red)"><path d="M2 2 L12 12 M12 2 L2 12" stroke="currentColor" stroke-width="2.6" fill="none"/></svg>UA Market</a></div></div>
<main><div class="in"><div class="plate" data-catching-up>
<p class="mono">503</p>
<h1>${esc(d.title)}</h1>
<p>${esc(d.body)}</p>
<p><a class="btn" href="${esc(path)}">${esc(d.retry)}</a></p>
<p class="mono" lang="${lang === "uk" ? "en" : "uk"}">${esc(other.title)}. ${esc(other.body)}</p>
</div></div></main></body></html>`;
}
