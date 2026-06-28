#!/usr/bin/env python3
import csv
from pathlib import Path
from collections import defaultdict

import matplotlib.pyplot as plt
import numpy as np

SPEEDUP_CSV = Path("results/final_prime_level4c_vs_gpu_seq_avg.csv")
FRACTION_CSV = Path("results/final_embedding_fraction_analytical.csv")

OUT_CSV = Path("results/final_realistic_end_to_end_speedup.csv")
OUT_SVG = Path("results/figF_realistic_end_to_end_improvement.svg")
OUT_PNG = Path("results/figF_realistic_end_to_end_improvement.png")


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def e2e_speedup(f, s):
    return 1.0 / ((1.0 - f) + f / s)


def main():
    speed_rows = read_csv(SPEEDUP_CSV)
    frac_rows = read_csv(FRACTION_CSV)

    prime_speedup_by_seq = {}
    naive_speedup_by_seq = {}

    for r in speed_rows:
        seq_len = int(r["seq_len"])
        prime_speedup_by_seq[seq_len] = float(r["prime_level4c_speedup_mean"])
        naive_speedup_by_seq[seq_len] = float(r["naive_hbm_speedup_mean"])

    out_rows = []

    for r in frac_rows:
        model = r["model"]
        seq_len = int(r["seq_len"])
        effective_tflops = float(r["effective_tflops"])
        f = float(r["embedding_fraction"])

        prime_s = prime_speedup_by_seq[seq_len]
        naive_s = naive_speedup_by_seq[seq_len]

        prime_e2e = e2e_speedup(f, prime_s)
        naive_e2e = e2e_speedup(f, naive_s)

        out_rows.append({
            "model": model,
            "seq_len": seq_len,
            "effective_tflops": effective_tflops,
            "embedding_fraction": f,
            "embedding_fraction_percent": f * 100.0,
            "naive_embedding_speedup": naive_s,
            "prime_embedding_speedup": prime_s,
            "naive_e2e_speedup": naive_e2e,
            "prime_e2e_speedup": prime_e2e,
            "naive_e2e_improvement_percent": (naive_e2e - 1.0) * 100.0,
            "prime_e2e_improvement_percent": (prime_e2e - 1.0) * 100.0,
        })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "model",
                "seq_len",
                "effective_tflops",
                "embedding_fraction",
                "embedding_fraction_percent",
                "naive_embedding_speedup",
                "prime_embedding_speedup",
                "naive_e2e_speedup",
                "prime_e2e_speedup",
                "naive_e2e_improvement_percent",
                "prime_e2e_improvement_percent",
            ],
        )
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Wrote {OUT_CSV}")

    # Plot sequence-average PriME realistic E2E improvement.
    by_tflops_seq = defaultdict(list)

    for r in out_rows:
        key = (float(r["effective_tflops"]), int(r["seq_len"]))
        by_tflops_seq[key].append(float(r["prime_e2e_improvement_percent"]))

    seq_lens = sorted(set(int(r["seq_len"]) for r in out_rows))
    tflops_values = sorted(set(float(r["effective_tflops"]) for r in out_rows))

    x = np.arange(len(seq_lens))

    fig, ax = plt.subplots(figsize=(9.0, 5.0))

    for tflops in tflops_values:
        ys = []
        for L in seq_lens:
            vals = by_tflops_seq[(tflops, L)]
            ys.append(sum(vals) / len(vals))
        ax.plot(x, ys, marker="o", label=f"{tflops:g} effective TFLOPS")

    ax.set_xlabel("Sequence length")
    ax.set_ylabel("Estimated end-to-end improvement (%)")
    ax.set_title("Figure F: Realistic full-transformer improvement from PriME embedding acceleration")
    ax.set_xticks(x)
    ax.set_xticklabels([str(L) for L in seq_lens])
    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.6)
    ax.legend()

    fig.tight_layout()
    fig.savefig(OUT_SVG)
    fig.savefig(OUT_PNG, dpi=300)

    print(f"Wrote {OUT_SVG}")
    print(f"Wrote {OUT_PNG}")

    print()
    print("Sequence-average realistic PriME end-to-end improvement (%):")
    print("effective_tflops,seq_len,prime_e2e_improvement_percent")
    for tflops in tflops_values:
        for L in seq_lens:
            vals = by_tflops_seq[(tflops, L)]
            print(f"{tflops:g},{L},{sum(vals)/len(vals):.6f}")


if __name__ == "__main__":
    main()
