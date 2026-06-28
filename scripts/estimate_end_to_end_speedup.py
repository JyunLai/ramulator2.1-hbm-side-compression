#!/usr/bin/env python3
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

INPUT = Path("results/final_prime_level4c_vs_gpu_seq_avg.csv")

OUT_CSV = Path("results/final_end_to_end_speedup_estimate.csv")
OUT_SVG = Path("results/figD_end_to_end_speedup_estimate.svg")
OUT_PNG = Path("results/figD_end_to_end_speedup_estimate.png")

# Assume embedding lookup occupies these fractions of total GPU inference time.
EMBEDDING_FRACTIONS = [0.05, 0.10, 0.25, 0.50, 0.75]


def e2e_speedup(embedding_fraction, embedding_speedup):
    f = embedding_fraction
    s = embedding_speedup
    return 1.0 / ((1.0 - f) + f / s)


def read_input():
    with open(INPUT, newline="") as f:
        return list(csv.DictReader(f))


def main():
    rows = read_input()

    out_rows = []

    for r in rows:
        seq_len = int(r["seq_len"])

        naive_s = float(r["naive_hbm_speedup_mean"])
        prime_s = float(r["prime_level4c_speedup_mean"])

        for f in EMBEDDING_FRACTIONS:
            out_rows.append({
                "seq_len": seq_len,
                "embedding_fraction": f,
                "naive_embedding_speedup": naive_s,
                "prime_embedding_speedup": prime_s,
                "naive_end_to_end_speedup": e2e_speedup(f, naive_s),
                "prime_end_to_end_speedup": e2e_speedup(f, prime_s),
            })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "seq_len",
                "embedding_fraction",
                "naive_embedding_speedup",
                "prime_embedding_speedup",
                "naive_end_to_end_speedup",
                "prime_end_to_end_speedup",
            ],
        )
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Wrote {OUT_CSV}")
    print()
    with open(OUT_CSV) as f:
        print(f.read())

    # Plot: x-axis embedding fraction, y-axis E2E speedup.
    seq_lens = sorted(set(int(r["seq_len"]) for r in out_rows))
    x = np.array(EMBEDDING_FRACTIONS) * 100.0

    fig, ax = plt.subplots(figsize=(9.0, 5.0))

    for L in seq_lens:
        ys = [
            float(r["prime_end_to_end_speedup"])
            for r in out_rows
            if int(r["seq_len"]) == L
        ]
        ax.plot(x, ys, marker="o", label=f"PriME seq={L}")

    ax.axhline(1.0, linestyle="--", linewidth=1, label="GPU-only baseline = 1.0")

    ax.set_xlabel("Embedding lookup fraction of GPU total latency (%)")
    ax.set_ylabel("Estimated end-to-end speedup")
    ax.set_title("Figure D: End-to-end speedup estimate with PriME embedding acceleration")
    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.6)
    ax.legend(ncol=2, fontsize=9)

    fig.tight_layout()
    fig.savefig(OUT_SVG)
    fig.savefig(OUT_PNG, dpi=300)

    print(f"Wrote {OUT_SVG}")
    print(f"Wrote {OUT_PNG}")


if __name__ == "__main__":
    main()
