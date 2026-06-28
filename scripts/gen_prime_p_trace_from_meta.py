#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--meta", required=True)
    p.add_argument("--output", required=True)
    return p.parse_args()

def main():
    args = parse_args()

    meta = Path(args.meta)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    with open(meta, newline="") as f, open(out, "w") as g:
        reader = csv.DictReader(f)

        for r in reader:
            fields = [
                r["channel"],
                r["pseudochannel"],
                r["bankgroup"],
                r["even_bank"],
                r["row"],
                r["read_col_base"],
                r["odd_bank"],
                r["write_col_base"],
            ]

            g.write("P " + ",".join(fields) + "\n")
            n += 1

    print(f"Wrote {out}")
    print(f"Prime chunks: {n}")

if __name__ == "__main__":
    main()
