#!/usr/bin/env python3
import argparse
import csv
import glob
from pathlib import Path

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input-glob", required=True)
    p.add_argument("--output", required=True)
    return p.parse_args()

def main():
    args = parse_args()

    files = sorted(glob.glob(args.input_glob))
    if not files:
      raise RuntimeError(f"No files matched: {args.input_glob}")

    rows = []
    for fp in files:
        with open(fp, newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                r["source_file"] = Path(fp).name
                rows.append(r)

    rows.sort(key=lambda r: (
        int(r["start_cycle"]),
        int(r["end_cycle"]),
        int(r["chunk_id"]),
        r["cmd"],
    ))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = list(rows[0].keys())
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Input files: {len(files)}")
    print(f"Merged rows: {len(rows)}")
    print(f"Wrote {out}")

if __name__ == "__main__":
    main()
