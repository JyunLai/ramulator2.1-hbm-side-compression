#!/usr/bin/env python3
import csv
from pathlib import Path

inp = "results/fig8_normalized_reproduction.csv"
out = "results/fig8_normalized_reproduction.svg"

rows = []
with open(inp) as f:
    for r in csv.DictReader(f):
        rows.append({
            "seq_len": r["seq_len"],
            "HBM-PIM": float(r["HBM-PIM"]),
            "PriME": float(r["PriME"]),
        })

W, H = 760, 460
margin_l, margin_r = 80, 30
margin_t, margin_b = 45, 70
plot_w = W - margin_l - margin_r
plot_h = H - margin_t - margin_b
ymax = 5.0

bar_group_w = plot_w / len(rows)
bar_w = 42

def y(v):
    return margin_t + plot_h * (1 - v / ymax)

def rect(x, y0, w, h, fill):
    return f'<rect x="{x:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}"/>'

svg = []
svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
svg.append('<rect width="100%" height="100%" fill="white"/>')

# title
svg.append(f'<text x="{W/2}" y="24" text-anchor="middle" font-family="Arial" font-size="18" font-weight="bold">Fig. 8-like Normalized Performance</text>')

# axes
x0 = margin_l
y0 = margin_t + plot_h
svg.append(f'<line x1="{x0}" y1="{margin_t}" x2="{x0}" y2="{y0}" stroke="black"/>')
svg.append(f'<line x1="{x0}" y1="{y0}" x2="{W-margin_r}" y2="{y0}" stroke="black"/>')

# y grid and labels
for tick in range(0, 6):
    yy = y(tick)
    svg.append(f'<line x1="{x0}" y1="{yy:.1f}" x2="{W-margin_r}" y2="{yy:.1f}" stroke="#dddddd"/>')
    svg.append(f'<text x="{x0-10}" y="{yy+4:.1f}" text-anchor="end" font-family="Arial" font-size="12">{tick}</text>')

# bars
for i, r in enumerate(rows):
    cx = margin_l + bar_group_w * i + bar_group_w / 2

    hbm = r["HBM-PIM"]
    prime = r["PriME"]

    x_hbm = cx - bar_w - 5
    x_prime = cx + 5

    svg.append(rect(x_hbm, y(hbm), bar_w, y0 - y(hbm), "#9e9e9e"))
    svg.append(rect(x_prime, y(prime), bar_w, y0 - y(prime), "#4a78c2"))

    svg.append(f'<text x="{x_hbm + bar_w/2}" y="{y(hbm)-6:.1f}" text-anchor="middle" font-family="Arial" font-size="12">{hbm:.1f}</text>')
    svg.append(f'<text x="{x_prime + bar_w/2}" y="{y(prime)-6:.1f}" text-anchor="middle" font-family="Arial" font-size="12">{prime:.1f}</text>')

    svg.append(f'<text x="{cx}" y="{y0+24}" text-anchor="middle" font-family="Arial" font-size="13">{r["seq_len"]}</text>')

# labels
svg.append(f'<text x="{W/2}" y="{H-20}" text-anchor="middle" font-family="Arial" font-size="14">Sequence Length</text>')
svg.append(f'<text x="22" y="{H/2}" text-anchor="middle" font-family="Arial" font-size="14" transform="rotate(-90 22 {H/2})">Normalized Performance vs. GPU</text>')

# legend
legend_x = W - 210
legend_y = 55
svg.append(rect(legend_x, legend_y, 16, 16, "#9e9e9e"))
svg.append(f'<text x="{legend_x+24}" y="{legend_y+13}" font-family="Arial" font-size="13">HBM-PIM</text>')
svg.append(rect(legend_x, legend_y+24, 16, 16, "#4a78c2"))
svg.append(f'<text x="{legend_x+24}" y="{legend_y+37}" font-family="Arial" font-size="13">PriME</text>')

# note
svg.append(f'<text x="{W/2}" y="{H-2}" text-anchor="middle" font-family="Arial" font-size="10" fill="#555555">Paper-calibrated reproduction target, not raw Ramulator result</text>')

svg.append('</svg>')

Path(out).write_text("\n".join(svg))
print(f"Wrote {out}")
