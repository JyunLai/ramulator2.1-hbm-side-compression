#!/usr/bin/env python3
import csv
from pathlib import Path
from collections import defaultdict
import math

import matplotlib.pyplot as plt
import numpy as np

GPU_CLOCK_MHZ = 1132.0
RAM_CLOCK_MHZ = 1000.0

GPU_CSV = Path("../gpu_baseline/accelsim_fig8_sm86_once.csv")
NAIVE_CSV = Path("results/fig8_ramulator_bankpair_ch8_seed0_9_raw.csv")
PRIME_CSV = Path("results/fig8_prime_controller_level4c_device_ch8_seed0_9.csv")

OUT_LAT_CSV = Path("results/final_latency_scaling_seq_avg.csv")
OUT_LAT_SVG = Path("results/figB_absolute_latency_seq_avg.svg")
OUT_LAT_PNG = Path("results/figB_absolute_latency_seq_avg.png")

OUT_PER_TOKEN_SVG = Path("results/figC_per_token_latency_seq_avg.svg")
OUT_PER_TOKEN_PNG = Path("results/figC_per_token_latency_seq_avg.png")


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def find_col(rows, preferred):
    cols = list(rows[0].keys())

    for c in preferred:
        if c in cols:
            return c

    candidates = []
    for c in cols:
        lc = c.lower()
        if "cycle" in lc and c not in {"seq_len"}:
            candidates.append(c)

    if len(candidates) == 1:
        return candidates[0]

    raise RuntimeError(f"Cannot infer cycle column. columns={cols}, candidates={candidates}")


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def stdev(xs):
    if len(xs) <= 1:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def load_gpu():
    rows = read_csv(GPU_CSV)
    print("[GPU columns]", list(rows[0].keys()))

    cycle_col = find_col(
        rows,
        ["gpu_cycles", "cycles", "kernel_cycles", "accelsim_cycles", "sim_cycles"],
    )

    out = []
    for r in rows:
        model = r["model"].strip()
        seq_len = int(r["seq_len"])
        cycles = float(r[cycle_col])
        time_ns = cycles / GPU_CLOCK_MHZ * 1000.0
        out.append((model, seq_len, time_ns))

    return out


def load_naive():
    rows = read_csv(NAIVE_CSV)
    print("[Naive columns]", list(rows[0].keys()))

    mode_col = None
    for c in ["mode", "method", "trace_mode", "type"]:
        if c in rows[0]:
            mode_col = c
            break

    if mode_col is not None:
        rows = [r for r in rows if "naive" in r[mode_col].lower()]

    cycle_col = find_col(
        rows,
        ["naive_cycles", "cycles", "controller_cycles", "dram_controller_cycles", "final_cycles"],
    )

    out = []
    for r in rows:
        model = r["model"].strip()
        seq_len = int(r["seq_len"])
        cycles = float(r[cycle_col])
        time_ns = cycles / RAM_CLOCK_MHZ * 1000.0
        out.append((model, seq_len, time_ns))

    return out


def load_prime():
    rows = read_csv(PRIME_CSV)
    print("[Prime columns]", list(rows[0].keys()))

    cycle_col = find_col(
        rows,
        ["prime_final_cycles", "final_cycles", "dram_controller_cycles", "cycles"],
    )

    out = []
    for r in rows:
        model = r["model"].strip()
        seq_len = int(r["seq_len"])
        cycles = float(r[cycle_col])
        time_ns = cycles / RAM_CLOCK_MHZ * 1000.0
        out.append((model, seq_len, time_ns))

    return out


def summarize_by_seq(rows):
    by_seq = defaultdict(list)
    for model, seq_len, time_ns in rows:
        by_seq[seq_len].append(time_ns)

    stats = {}
    for seq_len, vals in by_seq.items():
        stats[seq_len] = {
            "mean_ns": mean(vals),
            "std_ns": stdev(vals),
            "n": len(vals),
            "per_token_ns": mean(vals) / seq_len,
        }
    return stats


def main():
    gpu = summarize_by_seq(load_gpu())
    naive = summarize_by_seq(load_naive())
    prime = summarize_by_seq(load_prime())

    seq_lens = [128, 512, 1024, 2048]

    OUT_LAT_CSV.parent.mkdir(parents=True, exist_ok=True)

    with open(OUT_LAT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "seq_len",
                "gpu_mean_ns",
                "naive_hbm_mean_ns",
                "prime_level4c_mean_ns",
                "gpu_per_token_ns",
                "naive_hbm_per_token_ns",
                "prime_level4c_per_token_ns",
                "gpu_n",
                "naive_n",
                "prime_n",
            ],
        )
        writer.writeheader()

        for L in seq_lens:
            writer.writerow({
                "seq_len": L,
                "gpu_mean_ns": gpu[L]["mean_ns"],
                "naive_hbm_mean_ns": naive[L]["mean_ns"],
                "prime_level4c_mean_ns": prime[L]["mean_ns"],
                "gpu_per_token_ns": gpu[L]["per_token_ns"],
                "naive_hbm_per_token_ns": naive[L]["per_token_ns"],
                "prime_level4c_per_token_ns": prime[L]["per_token_ns"],
                "gpu_n": gpu[L]["n"],
                "naive_n": naive[L]["n"],
                "prime_n": prime[L]["n"],
            })

    print(f"Wrote {OUT_LAT_CSV}")
    print()
    with open(OUT_LAT_CSV) as f:
        print(f.read())

    x_labels = [str(L) for L in seq_lens]
    x = np.arange(len(seq_lens))

    gpu_y = [gpu[L]["mean_ns"] / 1000.0 for L in seq_lens]
    naive_y = [naive[L]["mean_ns"] / 1000.0 for L in seq_lens]
    prime_y = [prime[L]["mean_ns"] / 1000.0 for L in seq_lens]

    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    ax.plot(x, gpu_y, marker="o", label="GPU baseline")
    ax.plot(x, naive_y, marker="o", label="Naive HBM")
    ax.plot(x, prime_y, marker="o", label="PriME Level4C")

    ax.set_xlabel("Sequence length")
    ax.set_ylabel("Average latency (us)")
    ax.set_title("Figure B: Absolute latency scaling")
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels)
    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.6)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT_LAT_SVG)
    fig.savefig(OUT_LAT_PNG, dpi=300)

    gpu_pt = [gpu[L]["per_token_ns"] for L in seq_lens]
    naive_pt = [naive[L]["per_token_ns"] for L in seq_lens]
    prime_pt = [prime[L]["per_token_ns"] for L in seq_lens]

    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    ax.plot(x, gpu_pt, marker="o", label="GPU baseline")
    ax.plot(x, naive_pt, marker="o", label="Naive HBM")
    ax.plot(x, prime_pt, marker="o", label="PriME Level4C")

    ax.set_xlabel("Sequence length")
    ax.set_ylabel("Average latency per token (ns/token)")
    ax.set_title("Figure C: Per-token latency scaling")
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels)
    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.6)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT_PER_TOKEN_SVG)
    fig.savefig(OUT_PER_TOKEN_PNG, dpi=300)

    print(f"Wrote {OUT_LAT_SVG}")
    print(f"Wrote {OUT_LAT_PNG}")
    print(f"Wrote {OUT_PER_TOKEN_SVG}")
    print(f"Wrote {OUT_PER_TOKEN_PNG}")


if __name__ == "__main__":
    main()
