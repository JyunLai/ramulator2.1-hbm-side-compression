#!/usr/bin/env python3
import csv
from pathlib import Path

REPLAY_CSV = Path("results/accelsim_read_replay_smol135m_ch8.csv")
SYN_NAIVE_CSV = Path("results/fig8_ramulator_bankpair_ch8_seed0_9_raw.csv")
SYN_PRIME_CSV = Path("results/fig8_prime_controller_level4c_device_ch8_seed0_9.csv")

OUT_CSV = Path("results/compare_accelsim_replay_vs_synthetic_smol135m.csv")

MODEL = "SmolLM2-135M"
SEED = 0


def read_csv(path):
    if not path.exists():
        raise SystemExit(f"ERROR: missing file: {path}")
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def find_cycle_col(rows, preferred):
    cols = list(rows[0].keys())
    for c in preferred:
        if c in cols:
            return c

    candidates = [c for c in cols if "cycle" in c.lower()]
    if len(candidates) == 1:
        return candidates[0]

    raise SystemExit(f"ERROR: cannot infer cycle column from {cols}; candidates={candidates}")


def find_mode_col(rows):
    cols = list(rows[0].keys())
    for c in ["mode", "method", "trace_mode", "type", "config"]:
        if c in cols:
            return c
    return None


def is_model(row, model):
    return row.get("model", "") == model


def is_seed(row, seed):
    if "seed" not in row:
        return True
    try:
        return int(row["seed"]) == seed
    except Exception:
        return False


def load_replay():
    rows = read_csv(REPLAY_CSV)
    cyc = find_cycle_col(rows, ["ramulator_cycles", "cycles", "controller_cycles"])
    out = {}
    for r in rows:
        if r.get("model", "") != MODEL:
            continue
        L = int(r["seq_len"])
        out[L] = int(float(r[cyc]))
    return out


def load_synthetic_naive():
    rows = read_csv(SYN_NAIVE_CSV)
    print("[synthetic naive columns]", list(rows[0].keys()))

    cyc = find_cycle_col(
        rows,
        ["naive_cycles", "ramulator_cycles", "controller_cycles", "final_cycles", "cycles"],
    )
    mode_col = find_mode_col(rows)

    out = {}

    for r in rows:
        if not is_model(r, MODEL):
            continue
        if not is_seed(r, SEED):
            continue

        if mode_col is not None:
            mode = r[mode_col].lower()
            if "naive" not in mode:
                continue

        L = int(r["seq_len"])
        out[L] = int(float(r[cyc]))

    return out


def load_synthetic_prime():
    rows = read_csv(SYN_PRIME_CSV)
    print("[synthetic prime columns]", list(rows[0].keys()))

    cyc = find_cycle_col(
        rows,
        ["prime_final_cycles", "ramulator_cycles", "controller_cycles", "final_cycles", "cycles"],
    )

    out = {}

    for r in rows:
        if not is_model(r, MODEL):
            continue
        if not is_seed(r, SEED):
            continue

        L = int(r["seq_len"])
        out[L] = int(float(r[cyc]))

    return out


def main():
    replay = load_replay()
    naive = load_synthetic_naive()
    prime = load_synthetic_prime()

    print()
    print("loaded replay:", replay)
    print("loaded synthetic naive:", naive)
    print("loaded synthetic prime:", prime)
    print()

    seq_lens = sorted(set(replay) | set(naive) | set(prime))

    rows = []
    for L in seq_lens:
        rcyc = replay.get(L)
        ncyc = naive.get(L)
        pcyc = prime.get(L)

        row = {
            "model": MODEL,
            "seed": SEED,
            "seq_len": L,
            "accelsim_replay_ch8_cycles": rcyc if rcyc is not None else "",
            "synthetic_naive_ch8_cycles": ncyc if ncyc is not None else "",
            "synthetic_prime_level4c_ch8_cycles": pcyc if pcyc is not None else "",
            "replay_over_synthetic_naive": (rcyc / ncyc) if rcyc is not None and ncyc else "",
            "synthetic_prime_over_replay": (pcyc / rcyc) if pcyc is not None and rcyc else "",
            "synthetic_prime_speedup_over_replay": (rcyc / pcyc) if pcyc is not None and pcyc else "",
            "synthetic_naive_speedup_over_prime": (ncyc / pcyc) if ncyc is not None and pcyc else "",
        }
        rows.append(row)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "model",
        "seed",
        "seq_len",
        "accelsim_replay_ch8_cycles",
        "synthetic_naive_ch8_cycles",
        "synthetic_prime_level4c_ch8_cycles",
        "replay_over_synthetic_naive",
        "synthetic_prime_over_replay",
        "synthetic_prime_speedup_over_replay",
        "synthetic_naive_speedup_over_prime",
    ]

    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {OUT_CSV}")
    print()
    print("seq,replay,synthetic_naive,synthetic_prime,replay/naive,prime/replay,replay/prime,naive/prime")
    for r in rows:
        print(
            f"{r['seq_len']},"
            f"{r['accelsim_replay_ch8_cycles']},"
            f"{r['synthetic_naive_ch8_cycles']},"
            f"{r['synthetic_prime_level4c_ch8_cycles']},"
            f"{r['replay_over_synthetic_naive']},"
            f"{r['synthetic_prime_over_replay']},"
            f"{r['synthetic_prime_speedup_over_replay']},"
            f"{r['synthetic_naive_speedup_over_prime']}"
        )


if __name__ == "__main__":
    main()
