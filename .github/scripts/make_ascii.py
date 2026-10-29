#!/usr/bin/env python3
"""
Turn a photo/avatar into a colored ASCII-art portrait SVG.

    python make_ascii.py <input image> <output.svg>

Static — run once (or whenever the source image changes). Not part of the
daily workflow. Needs Pillow.
"""
import colorsys
import sys

from PIL import Image

COLS = 84                       # character columns
ROWS = 42                       # character rows (~COLS/2 keeps the aspect square)
RAMP = " .:-=+*#%@"             # brightness ramp, dark -> dense
BG = "#0b1017"                  # matches the console panels
FS = 9                          # font size px
CW = FS * 0.6                   # monospace advance
LH = FS                         # line height
PAD = 16
DARK_CUT = 44                   # below this luminance -> background (blank)


def quantize(v, step=20):
    return max(0, min(255, int(round(v / step) * step)))


def main():
    src, out = sys.argv[1], sys.argv[2]
    img = Image.open(src).convert("RGB").resize((COLS, ROWS), Image.LANCZOS)
    px = img.load()

    rows_svg = []
    for r in range(ROWS):
        cells = []  # (char, color|None)
        for c in range(COLS):
            R, G, B = px[c, r]
            lum = 0.299 * R + 0.587 * G + 0.114 * B
            if lum < DARK_CUT:
                cells.append((" ", None))
                continue
            # punch up saturation a little so the neon reads
            h, s, v = colorsys.rgb_to_hsv(R / 255, G / 255, B / 255)
            s = min(1.0, s * 1.35)
            v = min(1.0, v * 1.08)
            nr, ng, nb = colorsys.hsv_to_rgb(h, s, v)
            color = "#%02x%02x%02x" % (quantize(nr * 255), quantize(ng * 255), quantize(nb * 255))
            ch = RAMP[min(len(RAMP) - 1, int(lum / 256 * len(RAMP)))]
            cells.append((ch, color))

        # run-length encode consecutive same-color cells into tspans
        spans, i = [], 0
        while i < COLS:
            ch, col = cells[i]
            j = i
            run = []
            while j < COLS and cells[j][1] == col:
                run.append(cells[j][0])
                j += 1
            text = "".join(run).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if col is None:
                spans.append(f"<tspan>{text}</tspan>")
            else:
                spans.append(f'<tspan fill="{col}">{text}</tspan>')
            i = j
        y = PAD + (r + 1) * LH
        rows_svg.append(f'<tspan x="{PAD}" y="{y}">{"".join(spans)}</tspan>')

    w = int(COLS * CW + PAD * 2)
    h = int(ROWS * LH + PAD * 2)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'role="img" aria-label="ASCII portrait">\n'
        f'  <rect x="0" y="0" width="{w}" height="{h}" rx="12" fill="{BG}" stroke="#1b2a1f" stroke-width="1.5"/>\n'
        f'  <text xml:space="preserve" font-family="\'JetBrains Mono\',\'Fira Code\',ui-monospace,monospace" '
        f'font-size="{FS}" letter-spacing="0">\n    '
        + "\n    ".join(rows_svg)
        + "\n  </text>\n</svg>\n"
    )
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {out} ({len(svg)} bytes, {COLS}x{ROWS})")


if __name__ == "__main__":
    main()
