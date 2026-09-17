"""Generate the storefront icons from the footer's cross-stitch wordmark.

    .venv/bin/python tools/brand_assets.py

Writes, from the same 5×7 stitch alphabet as web/components/WordmarkChart.tsx:
    web/app/icon.svg          the browser tab icon (vector)
    web/app/favicon.ico       16, 32 and 48 px for browsers that ask for /favicon.ico
    web/app/apple-icon.png    180 px, the home-screen icon on a phone
    web/public/logo-512.png   512 px, the logo in structured data and for the owner to reuse

The mark is "UA" stitched in red on the ink plate, with the chart's minor grid under it, the
way the footer draws the whole word. Colours are the КАНВА tokens (web/app/globals.css).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
PLATE = (0x1E, 0x1A, 0x17)
RED = (0xE5, 0x52, 0x5B)
GRID = (0x33, 0x2E, 0x2A)

GLYPHS = {
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
}


def cells(text: str = "UA") -> tuple[list[tuple[int, int]], int, int]:
    out, cursor = [], 0
    for ch in text:
        glyph = GLYPHS[ch]
        for y, row in enumerate(glyph):
            for x, c in enumerate(row):
                if c == "1":
                    out.append((cursor + x, y))
        cursor += len(glyph[0]) + 1
    return out, cursor - 1, 7


def layout(size: float):
    """Cell size and offsets so the 11×7 word sits centred with a two-cell margin each side."""
    stitched, w, h = cells()
    cols = w + 4
    cell = size / cols
    ox = 2 * cell
    oy = (size - h * cell) / 2
    return stitched, cell, ox, oy


def svg() -> str:
    size = 64
    stitched, cell, ox, oy = layout(size)
    pad = cell * 0.2
    grid = "".join(f'<path d="M{i * cell:.3f} 0V{size}M0 {i * cell:.3f}H{size}"/>' for i in range(1, 15))
    xs = "".join(
        f'<path d="M{ox + x * cell + pad:.3f} {oy + y * cell + pad:.3f}L{ox + (x + 1) * cell - pad:.3f} {oy + (y + 1) * cell - pad:.3f}'
        f'M{ox + (x + 1) * cell - pad:.3f} {oy + y * cell + pad:.3f}L{ox + x * cell + pad:.3f} {oy + (y + 1) * cell - pad:.3f}"/>'
        for x, y in stitched
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">'
        f'<rect width="{size}" height="{size}" fill="#1E1A17"/>'
        f'<g stroke="#332E2A" stroke-width="0.4">{grid}</g>'
        f'<g stroke="#E5525B" stroke-width="{cell * 0.26:.3f}" stroke-linecap="square" fill="none">{xs}</g>'
        "</svg>\n"
    )


def png(size: int, *, grid: bool = True) -> Image.Image:
    scale = 4
    big = size * scale
    img = Image.new("RGB", (big, big), PLATE)
    draw = ImageDraw.Draw(img)
    stitched, cell, ox, oy = layout(big)
    if grid and size >= 64:
        cols = round(big / cell)
        for i in range(1, cols):
            p = round(i * cell)
            draw.line([(p, 0), (p, big)], fill=GRID, width=max(1, scale // 2))
            draw.line([(0, p), (big, p)], fill=GRID, width=max(1, scale // 2))
    pad = cell * (0.2 if size >= 64 else 0.08)
    width = max(1, round(cell * (0.26 if size >= 64 else 0.36)))
    for x, y in stitched:
        x0, y0 = ox + x * cell + pad, oy + y * cell + pad
        x1, y1 = ox + (x + 1) * cell - pad, oy + (y + 1) * cell - pad
        draw.line([(x0, y0), (x1, y1)], fill=RED, width=width)
        draw.line([(x1, y0), (x0, y1)], fill=RED, width=width)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    (ROOT / "web/app/icon.svg").write_text(svg(), encoding="utf-8")
    png(180).convert("RGBA").save(ROOT / "web/app/apple-icon.png", optimize=True)
    png(512).save(ROOT / "web/public/logo-512.png", optimize=True)
    ico = png(48, grid=False).convert("RGBA")
    ico.save(ROOT / "web/app/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print("wrote web/app/icon.svg, web/app/favicon.ico, web/app/apple-icon.png, web/public/logo-512.png")


if __name__ == "__main__":
    main()
