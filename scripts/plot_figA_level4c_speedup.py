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

OUT_CSV = Path("results/final_prime_level4c_vs_gpu_seq_avg.csv")
OUT_SVG = Path("results/figA_speedup_over_gpu_seq_avg.svg")
OUT_PNG = Path("results/figA_speedup_over_gpu_seq_avg.png")


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def find_col(rows, preferred):
    if not rows:
        raise RuntimeError("empty CSV")
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

    tmp = defaultdict(list)
    for r in rows:
        model = r["model"].strip()
        seq_len = int(r["seq_len"])
        gpu_cycles = float(r[cycle_col])
        gpu_time_ns = gpu_cycles / GPU_CLOCK_MHZ * 1000.0
        tmp[(model, seq_len)].append(gpu_time_ns)

    return {k: mean(v) for k, v in tmp.items()}


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


def summarize_speedup(gpu_time, method_rows):
    by_seq = defaultdict(list)

    matched = 0
    for model, seq_len, method_time_ns in method_rows:
        key = (model, seq_len)
        if key not in gpu_time:
            continue
        speedup = gpu_time[key] / method_time_ns
        by_seq[seq_len].append(speedup)
        matched += 1

    if matched == 0:
        raise RuntimeError("No matched rows with GPU baseline")

    seq_stats = {}
    for seq_len, vals in by_seq.items():
        seq_stats[seq_len] = {
            "mean": mean(vals),
            "std": stdev(vals),
            "n": len(vals),
        }
    return seq_stats


def main():
    gpu_time = load_gpu()
    naive_rows = load_naive()
    prime_rows = load_prime()

    naive = summarize_speedup(gpu_time, naive_rows)
    prime = summarize_speedup(gpu_time, prime_rows)

    paper_hbmpim = {128: 0.7, 512: 0.3, 1024: 0.3, 2048: 0.3}
    paper_prime = {128: 3.5, 512: 3.8, 1024: 4.0, 2048: 4.5}

    seq_lens = [128, 512, 1024, 2048]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    with open(OUT_CSV, "w", newline="") as f:
        fieldnames = [
            "seq_len",
            "naive_hbm_speedup_mean",
            "naive_hbm_speedup_std",
            "naive_hbm_n",
            "prime_level4c_speedup_mean",
            "prime_level4c_speedup_std",
            "prime_level4c_n",
            "paper_hbmpim_target",
            "paper_prime_target",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for L in seq_lens:
            writer.writerow({
                "seq_len": L,
                "naive_hbm_speedup_mean": naive[L]["mean"],
                "naive_hbm_speedup_std": naive[L]["std"],
                "naive_hbm_n": naive[L]["n"],
                "prime_level4c_speedup_mean": prime[L]["mean"],
                "prime_level4c_speedup_std": prime[L]["std"],
                "prime_level4c_n": prime[L]["n"],
                "paper_hbmpim_target": paper_hbmpim[L],
                "paper_prime_target": paper_prime[L],
            })

    print(f"Wrote {OUT_CSV}")

    print()
    with open(OUT_CSV) as f:
        print(f.read())

    x_labels = [str(L) for L in seq_lens]
    x = np.arange(len(seq_lens))
    width = 0.20

    naive_y = [naive[L]["mean"] for L in seq_lens]
    prime_y = [prime[L]["mean"] for L in seq_lens]
    paper_hbm_y = [paper_hbmpim[L] for L in seq_lens]
    paper_prime_y = [paper_prime[L] for L in seq_lens]

    fig, ax = plt.subplots(figsize=(9.5, 4.8))

    ax.bar(x - 1.5 * width, naive_y, width, label="Our Naive HBM")
    ax.bar(x - 0.5 * width, prime_y, width, label="Our PriME Level4C")
    ax.bar(x + 0.5 * width, paper_hbm_y, width, label="Paper HBM-PIM target")
    ax.bar(x + 1.5 * width, paper_prime_y, width, label="Paper PriME target")

    ax.axhline(1.0, linestyle="--", linewidth=1, label="GPU baseline = 1.0")

    ax.set_xlabel("Sequence length")
    ax.set_ylabel("Normalized speedup over GPU")
    ax.set_title("Figure A: Sequence-length average speedup over GPU")
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels)
    ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.6)
    ax.legend(ncol=2, fontsize=9)

    fig.tight_layout()
    fig.savefig(OUT_SVG)
    fig.savefig(OUT_PNG, dpi=300)

    print(f"Wrote {OUT_SVG}")
    print(f"Wrote {OUT_PNG}")


if __name__ == "__main__":
    main()
