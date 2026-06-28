#!/usr/bin/env python3
import argparse
import csv
from collections import Counter

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--cmd-trace", required=True)
    return p.parse_args()

def main():
    args = parse_args()

    rows = []
    with open(args.cmd_trace, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    if not rows:
        raise RuntimeError("empty command trace")

    required_cols = {"chunk_id", "cmd_id", "cmd", "start_cycle", "end_cycle", "duration"}
    missing = required_cols - set(rows[0].keys())
    if missing:
        raise RuntimeError(f"missing columns: {sorted(missing)}")

    by_cmd = Counter()
    ids_by_cmd = {}

    for r in rows:
        cmd = r["cmd"]
        cmd_id = int(r["cmd_id"])
        by_cmd[cmd] += 1
        ids_by_cmd.setdefault(cmd, set()).add(cmd_id)

    expected_cmds = ["PRIME_RD96", "XMC_DECOMP", "PRIME_WB"]

    errors = []

    for cmd in expected_cmds:
        if cmd not in by_cmd:
            errors.append(f"missing command {cmd}")
        elif len(ids_by_cmd[cmd]) != 1:
            errors.append(f"command {cmd} has multiple cmd_ids: {sorted(ids_by_cmd[cmd])}")

    counts = [by_cmd[c] for c in expected_cmds]
    if len(set(counts)) != 1:
        errors.append(f"command counts mismatch: {dict(by_cmd)}")

    print("command counts:")
    for cmd in expected_cmds:
        print(f"  {cmd}: count={by_cmd[cmd]}, cmd_id={sorted(ids_by_cmd.get(cmd, []))}")

    print(f"errors: {len(errors)}")

    if errors:
        print()
        for e in errors[:20]:
            print(e)
        raise SystemExit(1)

    print("Command-id validation passed.")

if __name__ == "__main__":
    main()
