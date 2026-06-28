#!/usr/bin/env python3
import csv
from pathlib import Path
from collections import defaultdict

import matplotlib.pyplot as plt
import numpy as np

HF_PROFILE = Path("results/hf_embedding_fraction_profile.csv")
SPEEDUP_CSV = Path("results/final_prime_level4c_vs_gpu_seq_avg.csv")

OUT_CSV = Path("results/final_hf_profile_based_e2e_speedup.csv")
OUT_SVG = Path("results/figJ_hf_profile_based_e2e_improvement.svg")
OUT_PNG = Path("results/figJ_hf_profile_based_e2e_improvement.png")


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def e2e_speedup(f, s):
    return 1.0 / ((1.0 - f) + f / s)


def main():
    hf_rows = [r for r in read_csv(HF_PROFILE) if r["status"] == "ok"]
    speed_rows = read_csv(SPEEDUP_CSV)

    prime_speedup_by_seq = {}
    naive_speedup_by_seq = {}

    for r in speed_rows:
        seq_len = int(r["seq_len"])
        prime_speedup_by_seq[seq_len] = float(r["prime_level4c_speedup_mean"])
        naive_speedup_by_seq[seq_len] = float(r["naive_hbm_speedup_mean"])

    out_rows = []

    for r in hf_rows:
        model = r["model"]
        seq_len = int(r["seq_len"])
        f = float(r["embedding_fraction"])

        prime_s = prime_speedup_by_seq[seq_len]
        naive_s = naive_speedup_by_seq[seq_len]

        prime_e2e = e2e_speedup(f, prime_s)
        naive_e2e = e2e_speedup(f, naive_s)

        out_rows.append({
            "model": model,
            "seq_len": seq_len,
            "measured_full_forward_ms": float(r["full_forward_ms"]),
            "measured_embedding_ms": float(r["embedding_ms"]),
            "measured_embedding_fraction": f,
            "measured_embedding_fraction_percent": f * 100.0,
            "naive_embedding_speedup": naive_s,
            "prime_embedding_speedup": prime_s,
            "naive_e2e_speedup": naive_e2e,
            "prime_e2e_speedup": prime_e2e,
            "naive_e2e_improvement_percent": (naive_e2e - 1.0) * 100.0,
            "prime_e2e_improvement_percent": (prime_e2e - 1.0) * 100.0,
        })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "model",
        "seq_len",
        "measured_full_forward_ms",
        "measured_embedding_ms",
        "measured_embedding_fraction",
        "measured_embedding_fraction_percent",
        "naive_embedding_speedup",
        "prime_embedding_speedup",
        "naive_e2e_speedup",
        "prime_e2e_speedup",
        "naive_e2e_improvement_percent",
        "prime_e2e_improvement_percent",
    ]

    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Wrote {OUT_CSV}")

    # Plot grouped bar chart.
    model_order = []
    seq_lens = sorted(set(r["seq_len"] for r in out_rows))
    data = defaultdict(dict)

    for r in out_rows:
        model = r["model"]
        if model not in model_order:
            model_order.append(model)
        data[model][r["seq_len"]] = r["prime_e2e_improvement_percent"]

    x = np.arange(len(seq_lens))
    width = 0.22

    fig, ax = plt.subplots(figsize=(9.2, 5.0))

    for i, model in enumerate(model_order):
        ys = [data[model][L] for L in seq_lens]
        offset = (i - (len(model_order) - 1) / 2) * width
        ax.bar(x + offset, ys, width, label=model)

    ax.set_xlabel("Sequence length")
    ax.set_ylabel("Estimated E2E improvement from PriME (%)")
    ax.set_title("Figure J: E2E improvement using measured HF embedding fraction")
    ax.set_xticks(x)
    ax.set_xticklabels([str(L) for L in seq_lens])
    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.6)
    ax.legend(fontsize=9)

    fig.tight_layout()
    fig.savefig(OUT_SVG)
    fig.savefig(OUT_PNG, dpi=300)

    print(f"Wrote {OUT_SVG}")
    print(f"Wrote {OUT_PNG}")

    print()
    print("Measured-profile-based PriME E2E improvement:")
    for r in out_rows:
        print(
            f"{r['model']}, seq={r['seq_len']}, "
            f"embedding_fraction={r['measured_embedding_fraction_percent']:.6f}%, "
            f"PriME_embedding_speedup={r['prime_embedding_speedup']:.4f}x, "
            f"PriME_E2E_improvement={r['prime_e2e_improvement_percent']:.6f}%"
        )


if __name__ == "__main__":
    main()
