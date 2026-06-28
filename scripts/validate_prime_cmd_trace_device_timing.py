#!/usr/bin/env python3
import argparse
import csv
from collections import defaultdict

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--cmd-trace", required=True)
    p.add_argument("--completion-log", required=True)
    p.add_argument("--decomp-latency", type=int, default=3)
    p.add_argument("--wb-cost", type=int, default=4)
    return p.parse_args()

def main():
    args = parse_args()

    by_chunk = defaultdict(dict)
    with open(args.cmd_trace, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            cid = int(r["chunk_id"])
            cmd = r["cmd"]
            by_chunk[cid][cmd] = {
                "start": int(r["start_cycle"]),
                "end": int(r["end_cycle"]),
                "duration": int(r["duration"]),
            }

    comp = {}
    with open(args.completion_log, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            comp[int(r["chunk_id"])] = int(r["complete_cycle"])

    errors = []
    wait_cycles = []

    for cid, cmds in by_chunk.items():
        for cmd in ["PRIME_RD96", "XMC_DECOMP", "PRIME_WB"]:
            if cmd not in cmds:
                errors.append(f"chunk {cid}: missing {cmd}")
                continue

        if cid not in comp:
            errors.append(f"chunk {cid}: missing completion")
            continue

        if len(errors) > 100:
            break

        rd = cmds["PRIME_RD96"]
        de = cmds["XMC_DECOMP"]
        wb = cmds["PRIME_WB"]

        if de["start"] != rd["end"]:
            errors.append(f"chunk {cid}: decomp_start {de['start']} != rd_end {rd['end']}")

        if de["duration"] != args.decomp_latency:
            errors.append(f"chunk {cid}: decomp duration {de['duration']} != {args.decomp_latency}")

        if wb["start"] < de["end"]:
            errors.append(f"chunk {cid}: wb_start {wb['start']} < decomp_end {de['end']}")

        if wb["duration"] != args.wb_cost:
            errors.append(f"chunk {cid}: wb duration {wb['duration']} != {args.wb_cost}")

        if comp[cid] != wb["end"]:
            errors.append(f"chunk {cid}: completion {comp[cid]} != wb_end {wb['end']}")

        wait_cycles.append(wb["start"] - de["end"])

    print("chunks:", len(by_chunk))
    print("errors:", len(errors))
    print("chunks with wb wait:", sum(w > 0 for w in wait_cycles))
    print("max wb wait:", max(wait_cycles) if wait_cycles else 0)

    if errors:
        print()
        for e in errors[:30]:
            print(e)
        raise SystemExit(1)

    print("Device-timing validation passed.")

if __name__ == "__main__":
    main()
