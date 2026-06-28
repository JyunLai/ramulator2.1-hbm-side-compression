#!/usr/bin/env python3
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

FRACTION_CSV = Path("results/final_embedding_fraction_analytical.csv")
E2E_CSV = Path("results/final_realistic_end_to_end_speedup.csv")

OUT_SUMMARY = Path("results/final_model_level_embedding_impact_summary.csv")
OUT_TOP_FRAC = Path("results/final_top_embedding_fraction_cases.csv")
OUT_TOP_E2E = Path("results/final_top_realistic_e2e_improvement_cases.csv")

OUT_FIG_G_SVG = Path("results/figG_top_embedding_fraction_cases.svg")
OUT_FIG_G_PNG = Path("results/figG_top_embedding_fraction_cases.png")

OUT_FIG_H_SVG = Path("results/figH_top_realistic_e2e_improvement_cases.svg")
OUT_FIG_H_PNG = Path("results/figH_top_realistic_e2e_improvement_cases.png")

TOPK = 10


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    frac_rows = read_csv(FRACTION_CSV)
    e2e_rows = read_csv(E2E_CSV)

    # Build lookup for realistic e2e rows.
    e2e_lookup = {}
    for r in e2e_rows:
        key = (
            r["model"],
            int(r["seq_len"]),
            float(r["effective_tflops"]),
        )
        e2e_lookup[key] = r

    summary = []

    for r in frac_rows:
        model = r["model"]
        seq_len = int(r["seq_len"])
        tflops = float(r["effective_tflops"])
        key = (model, seq_len, tflops)

        e = e2e_lookup[key]

        summary.append({
            "model": model,
            "seq_len": seq_len,
            "effective_tflops": tflops,
            "gpu_embedding_ns": float(r["gpu_embedding_ns"]),
            "estimated_transformer_compute_ns": float(r["estimated_transformer_compute_ns"]),
            "estimated_total_ns": float(r["estimated_total_ns"]),
            "embedding_fraction_percent": float(r["embedding_fraction"]) * 100.0,
            "prime_embedding_speedup": float(e["prime_embedding_speedup"]),
            "prime_e2e_speedup": float(e["prime_e2e_speedup"]),
            "prime_e2e_improvement_percent": float(e["prime_e2e_improvement_percent"]),
        })

    fieldnames = [
        "model",
        "seq_len",
        "effective_tflops",
        "gpu_embedding_ns",
        "estimated_transformer_compute_ns",
        "estimated_total_ns",
        "embedding_fraction_percent",
        "prime_embedding_speedup",
        "prime_e2e_speedup",
        "prime_e2e_improvement_percent",
    ]

    summary_sorted = sorted(
        summary,
        key=lambda r: (
            -r["embedding_fraction_percent"],
            -r["prime_e2e_improvement_percent"],
        ),
    )

    top_frac = summary_sorted[:20]

    top_e2e = sorted(
        summary,
        key=lambda r: -r["prime_e2e_improvement_percent"],
    )[:20]

    write_csv(OUT_SUMMARY, summary, fieldnames)
    write_csv(OUT_TOP_FRAC, top_frac, fieldnames)
    write_csv(OUT_TOP_E2E, top_e2e, fieldnames)

    print(f"Wrote {OUT_SUMMARY}")
    print(f"Wrote {OUT_TOP_FRAC}")
    print(f"Wrote {OUT_TOP_E2E}")

    print()
    print("Top embedding-fraction cases:")
    for r in top_frac[:10]:
        print(
            f"{r['model']}, seq={r['seq_len']}, "
            f"TFLOPS={r['effective_tflops']:g}, "
            f"embedding_fraction={r['embedding_fraction_percent']:.6f}%, "
            f"PriME_E2E_improvement={r['prime_e2e_improvement_percent']:.6f}%"
        )

    print()
    print("Top realistic PriME E2E-improvement cases:")
    for r in top_e2e[:10]:
        print(
            f"{r['model']}, seq={r['seq_len']}, "
            f"TFLOPS={r['effective_tflops']:g}, "
            f"embedding_fraction={r['embedding_fraction_percent']:.6f}%, "
            f"PriME_E2E_improvement={r['prime_e2e_improvement_percent']:.6f}%"
        )

    # Figure G: top embedding fraction cases.
    fig_rows = top_frac[:TOPK]
    labels = [
        f"{r['model']}\\nseq={r['seq_len']}, {r['effective_tflops']:g} TF"
        for r in fig_rows
    ]
    vals = [r["embedding_fraction_percent"] for r in fig_rows]

    y = np.arange(len(fig_rows))

    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    ax.barh(y, vals)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Embedding fraction of estimated total latency (%)")
    ax.set_title("Figure G: Top model-level embedding-fraction cases")
    ax.grid(axis="x", linestyle="--", linewidth=0.5, alpha=0.6)
    fig.tight_layout()
    fig.savefig(OUT_FIG_G_SVG)
    fig.savefig(OUT_FIG_G_PNG, dpi=300)

    # Figure H: top realistic PriME e2e improvement cases.
    fig_rows = top_e2e[:TOPK]
    labels = [
        f"{r['model']}\\nseq={r['seq_len']}, {r['effective_tflops']:g} TF"
        for r in fig_rows
    ]
    vals = [r["prime_e2e_improvement_percent"] for r in fig_rows]

    y = np.arange(len(fig_rows))

    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    ax.barh(y, vals)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Estimated full-transformer improvement from PriME (%)")
    ax.set_title("Figure H: Top realistic PriME end-to-end improvement cases")
    ax.grid(axis="x", linestyle="--", linewidth=0.5, alpha=0.6)
    fig.tight_layout()
    fig.savefig(OUT_FIG_H_SVG)
    fig.savefig(OUT_FIG_H_PNG, dpi=300)

    print()
    print(f"Wrote {OUT_FIG_G_SVG}")
    print(f"Wrote {OUT_FIG_G_PNG}")
    print(f"Wrote {OUT_FIG_H_SVG}")
    print(f"Wrote {OUT_FIG_H_PNG}")


if __name__ == "__main__":
    main()
