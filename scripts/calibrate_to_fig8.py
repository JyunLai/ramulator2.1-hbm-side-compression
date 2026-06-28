#!/usr/bin/env python3
import csv
from pathlib import Path

TARGET_HBM_NORM = {
    128: 0.7,
    512: 0.3,
    1024: 0.3,
    2048: 0.3,
}

TARGET_PRIME_NORM = {
    128: 3.5,
    512: 3.8,
    1024: 4.0,
    2048: 4.5,
}

def read_csv_by_len(path):
    out = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            out[int(r["seq_len"])] = r
    return out

naive = read_csv_by_len("results/naive_smol135m_hbm2_fixedaddr.csv")
prime_readonly = read_csv_by_len("results/prime_readonly_smol135m_hbm2.csv")
prime_fullwrite = read_csv_by_len("results/prime_smol135m_hbm2_fixedaddr_fixedlayout.csv")

Path("results").mkdir(exist_ok=True)

out_path = "results/fig8_paper_calibrated.csv"
with open(out_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "seq_len",
        "naive_hbm_cycles",
        "paper_hbm_norm",
        "inferred_gpu_cycles",
        "paper_prime_norm",
        "paper_prime_target_cycles",
        "prime_readonly_cycles",
        "prime_fullwrite_cycles",
        "readonly_to_target_factor",
        "fullwrite_to_target_factor",
    ])

    for L in [128, 512, 1024, 2048]:
        naive_cycles = float(naive[L]["controller_cycles"])
        hbm_norm = TARGET_HBM_NORM[L]
        prime_norm = TARGET_PRIME_NORM[L]

        inferred_gpu_cycles = naive_cycles * hbm_norm
        prime_target_cycles = inferred_gpu_cycles / prime_norm

        readonly_cycles = float(prime_readonly[L]["controller_cycles"])
        fullwrite_cycles = float(prime_fullwrite[L]["controller_cycles"])

        readonly_factor = readonly_cycles / prime_target_cycles
        fullwrite_factor = fullwrite_cycles / prime_target_cycles

        w.writerow([
            L,
            round(naive_cycles, 3),
            hbm_norm,
            round(inferred_gpu_cycles, 3),
            prime_norm,
            round(prime_target_cycles, 3),
            round(readonly_cycles, 3),
            round(fullwrite_cycles, 3),
            round(readonly_factor, 3),
            round(fullwrite_factor, 3),
        ])

print(f"Wrote {out_path}")
print()

with open(out_path) as f:
    print(f.read())
