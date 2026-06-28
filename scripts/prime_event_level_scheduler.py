#!/usr/bin/env python3
import argparse
import csv
from collections import defaultdict
from pathlib import Path

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--completion-log", required=True)
    p.add_argument("--meta", required=True)
    p.add_argument("--decomp-latency", type=int, default=3)
    p.add_argument("--wb-costs", default="1,4",
                   help="Comma-separated writeback costs. Example: 1,4")
    p.add_argument("--output", default="")
    return p.parse_args()

def load_completion(path):
    """
    completion log columns:
      req_id,op,arrive_cycle,complete_cycle,channel,pseudochannel,bankgroup,bank,row,column

    For PriME bankpair trace:
      each 96B compressed chunk has 3 consecutive 32B reads.
      chunk_id = req_id // 3
    """
    by_chunk = defaultdict(list)
    max_complete = 0
    num_reads = 0

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r["op"] != "R":
                continue

            req_id = int(r["req_id"])
            chunk_id = req_id // 3
            complete = int(r["complete_cycle"])

            by_chunk[chunk_id].append({
                "req_id": req_id,
                "complete": complete,
                "channel": int(r["channel"]),
                "pseudochannel": int(r["pseudochannel"]),
                "bankgroup": int(r["bankgroup"]),
                "bank": int(r["bank"]),
                "row": int(r["row"]),
                "column": int(r["column"]),
            })

            max_complete = max(max_complete, complete)
            num_reads += 1

    return by_chunk, max_complete, num_reads

def load_meta(path):
    """
    metadata columns:
      seq_chunk_id,token_id,chunk_in_token,logical_chunk,channel,pseudochannel,
      bankgroup,even_bank,odd_bank,row,read_col_base,write_col_base
    """
    meta = {}

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            chunk_id = int(r["seq_chunk_id"])
            meta[chunk_id] = {
                "seq_chunk_id": chunk_id,
                "token_id": int(r["token_id"]),
                "chunk_in_token": int(r["chunk_in_token"]),
                "logical_chunk": int(r["logical_chunk"]),
                "channel": int(r["channel"]),
                "pseudochannel": int(r["pseudochannel"]),
                "bankgroup": int(r["bankgroup"]),
                "even_bank": int(r["even_bank"]),
                "odd_bank": int(r["odd_bank"]),
                "row": int(r["row"]),
                "read_col_base": int(r["read_col_base"]),
                "write_col_base": int(r["write_col_base"]),
            }

    return meta

def build_chunk_events(by_chunk, meta):
    events = []
    bad_chunks = []

    for chunk_id, m in meta.items():
        reads = by_chunk.get(chunk_id, [])

        if len(reads) != 3:
            bad_chunks.append((chunk_id, len(reads)))
            continue

        read_done = max(x["complete"] for x in reads)

        # Sanity checks. Keep them non-fatal for now.
        read_channels = {x["channel"] for x in reads}
        read_banks = {x["bank"] for x in reads}
        read_rows = {x["row"] for x in reads}

        events.append({
            "chunk_id": chunk_id,
            "read_done": read_done,
            "channel": m["channel"],
            "pseudochannel": m["pseudochannel"],
            "bankgroup": m["bankgroup"],
            "even_bank": m["even_bank"],
            "odd_bank": m["odd_bank"],
            "row": m["row"],
            "read_col_base": m["read_col_base"],
            "write_col_base": m["write_col_base"],
            "read_channels": len(read_channels),
            "read_banks": len(read_banks),
            "read_rows": len(read_rows),
        })

    # Event-level scheduling should follow when chunks become ready.
    events.sort(key=lambda x: (x["read_done"], x["chunk_id"]))
    return events, bad_chunks

def schedule(events, decomp_latency, wb_cost):
    """
    One pipelined decompressor per channel:
      latency = decomp_latency
      initiation interval = 1 cycle

    One internal writeback resource per paired odd bank:
      key = (channel, pseudochannel, bankgroup, odd_bank)
      cost = wb_cost cycles per decompressed 128B output
    """
    decomp_next_start = defaultdict(int)
    odd_bank_next = defaultdict(int)

    max_decomp_done = 0
    max_wb_done = 0

    detail_rows = []

    for e in events:
        ch = e["channel"]

        decomp_start = max(e["read_done"], decomp_next_start[ch])
        decomp_done = decomp_start + decomp_latency
        decomp_next_start[ch] = decomp_start + 1

        wb_key = (e["channel"], e["pseudochannel"], e["bankgroup"], e["odd_bank"])
        wb_start = max(decomp_done, odd_bank_next[wb_key])
        wb_done = wb_start + wb_cost
        odd_bank_next[wb_key] = wb_done

        max_decomp_done = max(max_decomp_done, decomp_done)
        max_wb_done = max(max_wb_done, wb_done)

        detail_rows.append({
            "chunk_id": e["chunk_id"],
            "read_done": e["read_done"],
            "channel": e["channel"],
            "pseudochannel": e["pseudochannel"],
            "bankgroup": e["bankgroup"],
            "even_bank": e["even_bank"],
            "odd_bank": e["odd_bank"],
            "decomp_start": decomp_start,
            "decomp_done": decomp_done,
            "wb_cost": wb_cost,
            "wb_start": wb_start,
            "wb_done": wb_done,
        })

    return max_decomp_done, max_wb_done, detail_rows

def main():
    args = parse_args()

    completion_path = Path(args.completion_log)
    meta_path = Path(args.meta)

    by_chunk, read_only_cycles, num_reads = load_completion(completion_path)
    meta = load_meta(meta_path)
    events, bad_chunks = build_chunk_events(by_chunk, meta)

    expected_reads = len(meta) * 3

    wb_costs = [int(x) for x in args.wb_costs.split(",") if x.strip()]

    summary = {
        "completion_log": str(completion_path),
        "meta": str(meta_path),
        "num_chunks_meta": len(meta),
        "num_chunks_scheduled": len(events),
        "num_reads": num_reads,
        "expected_reads": expected_reads,
        "bad_chunks": len(bad_chunks),
        "read_only_cycles": read_only_cycles,
        "decomp_latency": args.decomp_latency,
    }

    results = []

    for wb_cost in wb_costs:
        decomp_cycles, wb_cycles, detail_rows = schedule(
            events,
            decomp_latency=args.decomp_latency,
            wb_cost=wb_cost,
        )

        results.append({
            "wb_cost": wb_cost,
            "event_decomp_cycles": decomp_cycles,
            "event_decomp_wb_cycles": wb_cycles,
        })

        if args.output:
            detail_out = Path(args.output).with_suffix(f".wb{wb_cost}.detail.csv")
            with open(detail_out, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(detail_rows[0].keys()))
                writer.writeheader()
                writer.writerows(detail_rows)

    print("=== PriME event-level scheduler ===")
    for k, v in summary.items():
        print(f"{k}: {v}")

    for r in results:
        print(
            f"wb_cost={r['wb_cost']} "
            f"read_only={read_only_cycles} "
            f"decomp={r['event_decomp_cycles']} "
            f"decomp+wb={r['event_decomp_wb_cycles']}"
        )

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)

        out_rows = []
        base = dict(summary)
        for r in results:
            row = dict(base)
            row.update(r)
            out_rows.append(row)

        with open(out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
            writer.writeheader()
            writer.writerows(out_rows)

        print(f"Wrote {out}")

if __name__ == "__main__":
    main()
