#!/usr/bin/env python3
import csv
from pathlib import Path

CH = 8
SEED_BEGIN = 0
SEED_END = 9

level2_csv = Path(f"results/fig8_prime_controller_level2_ch{CH}_seed{SEED_BEGIN}_{SEED_END}.csv")
level4c_csv = Path(f"results/fig8_prime_controller_level4c_device_ch{CH}_seed{SEED_BEGIN}_{SEED_END}.csv")
out_csv = Path(f"results/compare_level2_vs_level4c_device_ch{CH}_seed{SEED_BEGIN}_{SEED_END}.csv")

level2 = {}
with open(level2_csv, newline="") as f:
    reader = csv.DictReader(f)
    for r in reader:
        key = (r["model"], int(r["seq_len"]), int(r["seed"]))
        level2[key] = int(r["prime_final_cycles"])

rows = []
with open(level4c_csv, newline="") as f:
    reader = csv.DictReader(f)
    for r in reader:
        key = (r["model"], int(r["seq_len"]), int(r["seed"]))
        if key not in level2:
            raise RuntimeError(f"Missing Level 2 row for {key}")

        l2 = level2[key]
        l4c = int(r["prime_final_cycles"])

        rows.append({
            "model": key[0],
            "seq_len": key[1],
            "seed": key[2],
            "level2_final": l2,
            "level4c_device_final": l4c,
            "diff": l4c - l2,
        })

with open(out_csv, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

max_abs_diff = max(abs(r["diff"]) for r in rows)
num_mismatch = sum(1 for r in rows if r["diff"] != 0)

print(f"Wrote {out_csv}")
print(f"rows: {len(rows)}")
print(f"max_abs_diff: {max_abs_diff}")
print(f"num_mismatch: {num_mismatch}")

if num_mismatch:
    print()
    print("First mismatches:")
    shown = 0
    for r in rows:
        if r["diff"] != 0:
            print(r)
            shown += 1
            if shown >= 10:
                break
