#!/usr/bin/env python3
import argparse
import csv
from collections import defaultdict
from pathlib import Path

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--cmd-trace", required=True)
    p.add_argument("--completion-log", required=True)
    p.add_argument("--decomp-latency", type=int, default=3)
    p.add_argument("--wb-cost", type=int, default=4)
    return p.parse_args()

def main():
    args = parse_args()

    completion = {}
    with open(args.completion_log, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            completion[int(r["chunk_id"])] = int(r["complete_cycle"])

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
                "row": r,
            }

    errors = []

    required = ["PRIME_RD96", "XMC_DECOMP", "PRIME_WB"]

    for cid, comp_cycle in completion.items():
        if cid not in by_chunk:
            errors.append(f"chunk {cid}: missing all command trace rows")
            continue

        cmds = by_chunk[cid]

        for c in required:
            if c not in cmds:
                errors.append(f"chunk {cid}: missing {c}")

        if any(c not in cmds for c in required):
            continue

        rd = cmds["PRIME_RD96"]
        dec = cmds["XMC_DECOMP"]
        wb = cmds["PRIME_WB"]

        if rd["end"] != dec["start"]:
            errors.append(f"chunk {cid}: RD96 end {rd['end']} != DECOMP start {dec['start']}")

        if dec["end"] != wb["start"]:
            errors.append(f"chunk {cid}: DECOMP end {dec['end']} != WB start {wb['start']}")

        if dec["duration"] != args.decomp_latency:
            errors.append(f"chunk {cid}: DECOMP duration {dec['duration']} != {args.decomp_latency}")

        if wb["duration"] != args.wb_cost:
            errors.append(f"chunk {cid}: WB duration {wb['duration']} != {args.wb_cost}")

        if wb["end"] != comp_cycle:
            errors.append(f"chunk {cid}: WB end {wb['end']} != completion {comp_cycle}")

    print(f"completion chunks: {len(completion)}")
    print(f"command-trace chunks: {len(by_chunk)}")
    print(f"errors: {len(errors)}")

    if errors:
        print()
        print("First errors:")
        for e in errors[:20]:
            print(e)
        raise SystemExit(1)

    print("Validation passed.")

if __name__ == "__main__":
    main()
