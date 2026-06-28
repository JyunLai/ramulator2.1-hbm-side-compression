#!/usr/bin/env python3
import csv
from pathlib import Path

CH = 8
SEED_BEGIN = 0
SEED_END = 9

level0_csv = Path(f"results/fig8_prime_event_ch{CH}_seed{SEED_BEGIN}_{SEED_END}.csv")
level1_csv = Path(f"results/fig8_prime_p_level1_ch{CH}_seed{SEED_BEGIN}_{SEED_END}.csv")
out_csv = Path(f"results/compare_level0_event_vs_level1_p_ch{CH}_seed{SEED_BEGIN}_{SEED_END}.csv")

level0 = {}
with open(level0_csv, newline="") as f:
    reader = csv.DictReader(f)
    for r in reader:
        key = (r["model"], int(r["seq_len"]), int(r["seed"]))
        level0[key] = r

rows = []

with open(level1_csv, newline="") as f:
    reader = csv.DictReader(f)
    for r in reader:
        key = (r["model"], int(r["seq_len"]), int(r["seed"]))
        if key not in level0:
            raise RuntimeError(f"Missing Level 0 row for {key}")

        l0 = level0[key]

        l0_read = int(l0["read_only_cycles"])
        l0_wb4 = int(l0["event_decomp_wb4_cycles"])

        l1_read = int(r["max_read_done"])
        l1_final = int(r["prime_final_cycles"])

        rows.append({
            "model": key[0],
            "seq_len": key[1],
            "seed": key[2],
            "level0_read_only": l0_read,
            "level1_max_read_done": l1_read,
            "read_diff": l1_read - l0_read,
            "level0_event_wb4": l0_wb4,
            "level1_p_final": l1_final,
            "final_diff": l1_final - l0_wb4,
        })

with open(out_csv, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

max_abs_read_diff = max(abs(r["read_diff"]) for r in rows)
max_abs_final_diff = max(abs(r["final_diff"]) for r in rows)

num_read_mismatch = sum(1 for r in rows if r["read_diff"] != 0)
num_final_mismatch = sum(1 for r in rows if r["final_diff"] != 0)

print(f"Wrote {out_csv}")
print(f"rows: {len(rows)}")
print(f"max_abs_read_diff: {max_abs_read_diff}")
print(f"max_abs_final_diff: {max_abs_final_diff}")
print(f"num_read_mismatch: {num_read_mismatch}")
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
