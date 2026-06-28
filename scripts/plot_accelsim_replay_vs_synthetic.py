#!/usr/bin/env python3
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

INPUT = Path("results/compare_accelsim_replay_vs_synthetic_smol135m.csv")

OUT_SVG = Path("results/figM_accelsim_replay_vs_synthetic.svg")
OUT_PNG = Path("results/figM_accelsim_replay_vs_synthetic.png")
OUT_SUMMARY = Path("results/figM_accelsim_replay_vs_synthetic_summary.csv")


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def main():
    rows = read_csv(INPUT)

    seq_lens = [int(r["seq_len"]) for r in rows]
    replay = [float(r["accelsim_replay_ch8_cycles"]) for r in rows]
    naive = [float(r["synthetic_naive_ch8_cycles"]) for r in rows]
    prime = [float(r["synthetic_prime_level4c_ch8_cycles"]) for r in rows]

    # Write compact summary with per-token cycles.
    with open(OUT_SUMMARY, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "seq_len",
                "accelsim_replay_ch8_cycles",
                "synthetic_naive_ch8_cycles",
                "synthetic_prime_level4c_cycles",
                "accelsim_replay_cycles_per_token",
                "synthetic_naive_cycles_per_token",
                "synthetic_prime_cycles_per_token",
                "replay_over_synthetic_naive",
                "replay_over_prime",
                "synthetic_naive_over_prime",
            ],
        )
        writer.writeheader()

        for L, rcyc, ncyc, pcyc in zip(seq_lens, replay, naive, prime):
            writer.writerow({
                "seq_len": L,
                "accelsim_replay_ch8_cycles": rcyc,
                "synthetic_naive_ch8_cycles": ncyc,
                "synthetic_prime_level4c_cycles": pcyc,
                "accelsim_replay_cycles_per_token": rcyc / L,
                "synthetic_naive_cycles_per_token": ncyc / L,
                "synthetic_prime_cycles_per_token": pcyc / L,
                "replay_over_synthetic_naive": rcyc / ncyc,
                "replay_over_prime": rcyc / pcyc,
                "synthetic_naive_over_prime": ncyc / pcyc,
            })

    x = np.arange(len(seq_lens))

    fig, ax = plt.subplots(figsize=(8.8, 5.0))

    ax.plot(x, replay, marker="o", label="Accel-Sim replay ch8")
    ax.plot(x, naive, marker="o", label="Synthetic Naive HBM ch8")
    ax.plot(x, prime, marker="o", label="PriME Level4C ch8")

    ax.set_xlabel("Sequence length")
    ax.set_ylabel("Ramulator cycles")
    ax.set_title("Figure M: Accel-Sim replay vs synthetic traces")
    ax.set_xticks(x)
    ax.set_xticklabels([str(L) for L in seq_lens])
    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.6)
    ax.legend()

    fig.tight_layout()
    fig.savefig(OUT_SVG)
    fig.savefig(OUT_PNG, dpi=300)

    print(f"Wrote {OUT_SUMMARY}")
    print(f"Wrote {OUT_SVG}")
    print(f"Wrote {OUT_PNG}")

    print()
    print("seq,replay,naive,prime,replay/naive,replay/prime,naive/prime")
    for L, rcyc, ncyc, pcyc in zip(seq_lens, replay, naive, prime):
        print(
            f"{L},"
            f"{rcyc:.0f},"
            f"{ncyc:.0f},"
            f"{pcyc:.0f},"
            f"{rcyc/ncyc:.4f},"
            f"{rcyc/pcyc:.4f},"
            f"{ncyc/pcyc:.4f}"
        )


if __name__ == "__main__":
    main()
