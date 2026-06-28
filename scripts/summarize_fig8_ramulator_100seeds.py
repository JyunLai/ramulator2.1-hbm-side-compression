#!/usr/bin/env python3
import csv
import math
from collections import defaultdict

raw_path = "results/fig8_ramulator_100seed_raw.csv"
avg_path = "results/fig8_ramulator_100seed_avg.csv"
seq_avg_path = "results/fig8_ramulator_100seed_seq_avg.csv"

groups = defaultdict(list)
seq_groups = defaultdict(list)

with open(raw_path) as f:
    for r in csv.DictReader(f):
        model = r["model"]
        seq_len = int(r["seq_len"])

        naive = float(r["naive_cycles"])
        prime = float(r["prime_readonly_cycles"])
        speedup = naive / prime

        item = {
            "model": model,
            "seq_len": seq_len,
            "naive_cycles": naive,
            "prime_cycles": prime,
            "speedup": speedup,
        }

        groups[(model, seq_len)].append(item)
        seq_groups[seq_len].append(item)


def mean(xs):
    return sum(xs) / len(xs)


def std(xs):
    if len(xs) <= 1:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


with open(avg_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "model",
        "seq_len",
        "num_runs",
        "avg_naive_cycles",
        "std_naive_cycles",
        "avg_prime_readonly_cycles",
        "std_prime_readonly_cycles",
        "naive_norm",
        "prime_readonly_norm",
        "std_readonly_speedup",
    ])

    for model, seq_len in sorted(groups.keys(), key=lambda x: (x[0], x[1])):
        rows = groups[(model, seq_len)]

        naive_vals = [x["naive_cycles"] for x in rows]
        prime_vals = [x["prime_cycles"] for x in rows]
        speedups = [x["speedup"] for x in rows]

        avg_naive = mean(naive_vals)
        avg_prime = mean(prime_vals)

        # For plotting, normalize to averaged naive cycles.
        prime_norm = avg_naive / avg_prime

        w.writerow([
            model,
            seq_len,
            len(rows),
            round(avg_naive, 3),
            round(std(naive_vals), 3),
            round(avg_prime, 3),
            round(std(prime_vals), 3),
            1.0,
            round(prime_norm, 6),
            round(std(speedups), 6),
        ])


with open(seq_avg_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "seq_len",
        "num_runs",
        "avg_naive_cycles",
        "avg_prime_readonly_cycles",
        "naive_norm",
        "prime_readonly_norm",
    ])

    for seq_len in [128, 512, 1024, 2048]:
        rows = seq_groups[seq_len]

        naive_vals = [x["naive_cycles"] for x in rows]
        prime_vals = [x["prime_cycles"] for x in rows]

        avg_naive = mean(naive_vals)
        avg_prime = mean(prime_vals)
        prime_norm = avg_naive / avg_prime

        w.writerow([
            seq_len,
            len(rows),
            round(avg_naive, 3),
            round(avg_prime, 3),
            1.0,
            round(prime_norm, 6),
        ])

print(f"Wrote {avg_path}")
print(f"Wrote {seq_avg_path}")

with open(seq_avg_path) as f:
    print(f.read())
