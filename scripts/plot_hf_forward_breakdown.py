#!/usr/bin/env python3
import csv
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

INPUT = Path("results/hf_forward_breakdown_profile.csv")
OUT_SVG = Path("results/figK_hf_forward_breakdown.svg")
OUT_PNG = Path("results/figK_hf_forward_breakdown.png")
OUT_SUMMARY = Path("results/hf_forward_breakdown_summary.csv")

rows = []
with open(INPUT, newline="") as f:
    for r in csv.DictReader(f):
        if r["status"] == "ok":
            rows.append(r)

labels = [f"{r['model']}\nseq={r['seq_len']}" for r in rows]
emb = [float(r["embedding_fraction_percent"]) for r in rows]
lm = [float(r["lm_head_fraction_percent"]) for r in rows]
rest = [float(r["rest_fraction_percent"]) for r in rows]

x = np.arange(len(rows))

fig, ax = plt.subplots(figsize=(12.5, 5.8))
ax.bar(x, emb, label="Input embedding")
ax.bar(x, lm, bottom=emb, label="lm_head / output projection")
ax.bar(x, rest, bottom=np.array(emb) + np.array(lm), label="Rest of forward")

ax.set_ylabel("Fraction of full forward latency (%)")
ax.set_title("Figure K: HuggingFace/PyTorch forward latency breakdown")
ax.set_xticks(x)
ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
ax.set_ylim(0, 100)
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
            "full_forward_ms",
            "embedding_fraction_percent",
            "lm_head_fraction_percent",
            "rest_fraction_percent",
        ],
    )
    writer.writeheader()
    for r in rows:
        writer.writerow({
            "model": r["model"],
            "seq_len": r["seq_len"],
            "full_forward_ms": r["full_forward_ms"],
            "embedding_fraction_percent": r["embedding_fraction_percent"],
            "lm_head_fraction_percent": r["lm_head_fraction_percent"],
            "rest_fraction_percent": r["rest_fraction_percent"],
        })

print(f"Wrote {OUT_SUMMARY}")
print(f"Wrote {OUT_SVG}")
print(f"Wrote {OUT_PNG}")

print()
print("Key ranges:")
print(f"embedding min/max = {min(emb):.4f}% / {max(emb):.4f}%")
print(f"lm_head min/max = {min(lm):.4f}% / {max(lm):.4f}%")
print(f"rest min/max = {min(rest):.4f}% / {max(rest):.4f}%")
