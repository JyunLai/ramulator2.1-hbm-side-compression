#!/usr/bin/env python3
import csv
from pathlib import Path
from collections import defaultdict

import matplotlib.pyplot as plt
import numpy as np

INPUT = Path("results/hf_embedding_fraction_profile.csv")

OUT_SUMMARY = Path("results/hf_embedding_fraction_profile_summary.csv")
OUT_SVG = Path("results/figI_hf_embedding_fraction_profile.svg")
OUT_PNG = Path("results/figI_hf_embedding_fraction_profile.png")


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def main():
    rows = [r for r in read_csv(INPUT) if r["status"] == "ok"]

    if not rows:
        raise SystemExit("ERROR: no ok rows found")

    model_order = []
    seq_lens = sorted(set(int(r["seq_len"]) for r in rows))

    data = defaultdict(dict)

    for r in rows:
        model = r["model"]
        if model not in model_order:
            model_order.append(model)

        seq_len = int(r["seq_len"])
        frac = float(r["embedding_fraction_percent"])
        full_ms = float(r["full_forward_ms"])
        emb_ms = float(r["embedding_ms"])

        data[model][seq_len] = {
            "embedding_fraction_percent": frac,
            "full_forward_ms": full_ms,
            "embedding_ms": emb_ms,
        }

    # Write compact summary.
    with open(OUT_SUMMARY, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "model",
                "seq_len",
                "full_forward_ms",
                "embedding_ms",
                "embedding_fraction_percent",
            ],
        )
        writer.writeheader()

        for model in model_order:
            for L in seq_lens:
                if L not in data[model]:
                    continue
                d = data[model][L]
                writer.writerow({
                    "model": model,
                    "seq_len": L,
                    "full_forward_ms": d["full_forward_ms"],
                    "embedding_ms": d["embedding_ms"],
                    "embedding_fraction_percent": d["embedding_fraction_percent"],
                })

    # Grouped bar chart.
    x = np.arange(len(seq_lens))
    width = 0.22

    fig, ax = plt.subplots(figsize=(9.2, 5.0))

    for i, model in enumerate(model_order):
        ys = []
        for L in seq_lens:
            ys.append(data[model][L]["embedding_fraction_percent"])

        offset = (i - (len(model_order) - 1) / 2) * width
        ax.bar(x + offset, ys, width, label=model)

    ax.set_xlabel("Sequence length")
    ax.set_ylabel("Measured embedding fraction of full forward latency (%)")
    ax.set_title("Figure I: HuggingFace/PyTorch measured embedding fraction")
    ax.set_xticks(x)
    ax.set_xticklabels([str(L) for L in seq_lens])
    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.6)
    ax.legend(fontsize=9)

    fig.tight_layout()
    fig.savefig(OUT_SVG)
    fig.savefig(OUT_PNG, dpi=300)

    print(f"Wrote {OUT_SUMMARY}")
    print(f"Wrote {OUT_SVG}")
    print(f"Wrote {OUT_PNG}")

    print()
    print("Measured embedding fraction summary:")
    for model in model_order:
        for L in seq_lens:
            d = data[model][L]
            print(
                f"{model}, seq={L}, "
                f"full={d['full_forward_ms']:.4f} ms, "
                f"embedding={d['embedding_ms']:.6f} ms, "
                f"fraction={d['embedding_fraction_percent']:.6f}%"
            )


if __name__ == "__main__":
    main()
