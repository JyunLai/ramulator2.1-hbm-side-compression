#!/usr/bin/env python3
import csv
from pathlib import Path

CH = 8
SEED_BEGIN = 0
SEED_END = 9

level1_csv = Path(f"results/fig8_prime_p_level1_ch{CH}_seed{SEED_BEGIN}_{SEED_END}.csv")
level2_csv = Path(f"results/fig8_prime_controller_level2_ch{CH}_seed{SEED_BEGIN}_{SEED_END}.csv")
out_csv = Path(f"results/compare_level1_p_vs_level2_controller_ch{CH}_seed{SEED_BEGIN}_{SEED_END}.csv")

level1 = {}

with open(level1_csv, newline="") as f:
    reader = csv.DictReader(f)
    for r in reader:
        key = (r["model"], int(r["seq_len"]), int(r["seed"]))
        level1[key] = r

rows = []

with open(level2_csv, newline="") as f:
    reader = csv.DictReader(f)
    for r in reader:
        key = (r["model"], int(r["seq_len"]), int(r["seed"]))

        if key not in level1:
            raise RuntimeError(f"Missing Level 1 row for {key}")

        l1 = level1[key]

        l1_read = int(l1["max_read_done"])
        l1_final = int(l1["prime_final_cycles"])
        l2_final = int(r["prime_final_cycles"])

        overhead_cycles = l2_final - l1_read
        overhead_pct = overhead_cycles / l1_read * 100.0 if l1_read > 0 else 0.0

        rows.append({
            "model": key[0],
            "seq_len": key[1],
            "seed": key[2],
            "level1_read_done": l1_read,
            "level1_final": l1_final,
            "level2_final": l2_final,
            "final_diff": l2_final - l1_final,
            "level2_overhead_cycles_vs_read": overhead_cycles,
            "level2_overhead_pct_vs_read": overhead_pct,
        })

with open(out_csv, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

max_abs_final_diff = max(abs(r["final_diff"]) for r in rows)
num_final_mismatch = sum(1 for r in rows if r["final_diff"] != 0)

print(f"Wrote {out_csv}")
print(f"rows: {len(rows)}")
print(f"max_abs_final_diff: {max_abs_final_diff}")
print(f"num_final_mismatch: {num_final_mismatch}")

if num_final_mismatch > 0:
    print()
    print("First mismatches:")
    shown = 0
    for r in rows:
        if r["final_diff"] != 0:
            print(r)
            shown += 1
            if shown >= 10:
                break
