#!/usr/bin/env python3
import csv
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

INPUT = Path("results/hf_forward_breakdown_profile.csv")
OUT_SVG = Path("results/figL_hf_embedding_vs_lmhead_zoom.svg")
OUT_PNG = Path("results/figL_hf_embedding_vs_lmhead_zoom.png")
OUT_SUMMARY = Path("results/hf_embedding_vs_lmhead_zoom_summary.csv")

rows = []
with open(INPUT, newline="") as f:
    for r in csv.DictReader(f):
        if r["status"] == "ok":
            rows.append(r)

labels = [f"{r['model']}\nseq={r['seq_len']}" for r in rows]
emb = [float(r["embedding_fraction_percent"]) for r in rows]
lm = [float(r["lm_head_fraction_percent"]) for r in rows]

x = np.arange(len(rows))
width = 0.38

fig, ax = plt.subplots(figsize=(12.5, 5.8))

ax.bar(x - width / 2, emb, width, label="Input embedding")
ax.bar(x + width / 2, lm, width, label="lm_head / output projection")

ax.set_ylabel("Fraction of full forward latency (%)")
ax.set_title("Figure L: Zoom-in of input embedding and lm_head latency fractions")
ax.set_xticks(x)
ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.6)
ax.legend()

fig.tight_layout()
fig.savefig(OUT_SVG)
fig.savefig(OUT_PNG, dpi=300)

with open(OUT_SUMMARY, "w", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "model",
            "seq_len",
            "input_embedding_fraction_percent",
            "lm_head_fraction_percent",
            "lm_head_over_embedding_ratio",
        ],
    )
    writer.writeheader()

    for r in rows:
        e = float(r["embedding_fraction_percent"])
        l = float(r["lm_head_fraction_percent"])
        writer.writerow({
            "model": r["model"],
            "seq_len": r["seq_len"],
            "input_embedding_fraction_percent": e,
            "lm_head_fraction_percent": l,
            "lm_head_over_embedding_ratio": l / e if e > 0 else "",
        })

print(f"Wrote {OUT_SUMMARY}")
print(f"Wrote {OUT_SVG}")
print(f"Wrote {OUT_PNG}")

print()
print("Key ranges:")
print(f"input embedding min/max = {min(emb):.4f}% / {max(emb):.4f}%")
print(f"lm_head min/max = {min(lm):.4f}% / {max(lm):.4f}%")
print(f"lm_head/input embedding ratio min/max = {min(l/e for l, e in zip(lm, emb)):.2f}x / {max(l/e for l, e in zip(lm, emb)):.2f}x")
