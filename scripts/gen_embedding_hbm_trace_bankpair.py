#!/usr/bin/env python3
import argparse
import csv
import math
import random
from pathlib import Path


NUM_PSEUDOCHANNELS = 2
NUM_BANKGROUPS = 4
NUM_BANKS = 4
NUM_BANK_PAIRS = NUM_BANKS // 2
NUM_COLUMNS = 128
NUM_ROWS = 1 << 14


def map_naive_64b_block(logical_block, num_channels):
    """
    Naive FP16:
      one 64B block = two 32B column reads.
    We keep both 32B reads in the same channel/bank row to model a contiguous block.
    """
    channel = logical_block % num_channels
    x = logical_block // num_channels

    col_slots = NUM_COLUMNS // 2
    col_base = (x % col_slots) * 2
    x //= col_slots

    bank = x % NUM_BANKS
    x //= NUM_BANKS

    bg = x % NUM_BANKGROUPS
    x //= NUM_BANKGROUPS

    pc = x % NUM_PSEUDOCHANNELS
    x //= NUM_PSEUDOCHANNELS

    row = x % NUM_ROWS

    return channel, pc, bg, bank, row, col_base


def map_prime_96b_chunk(logical_chunk, num_channels):
    """
    PriME:
      one compressed 96B chunk = three 32B column reads from an even bank.
      decompressed 128B result is internally written to paired odd bank.
    """
    channel = logical_chunk % num_channels
    x = logical_chunk // num_channels

    read_col_slots = NUM_COLUMNS // 3
    read_col_base = (x % read_col_slots) * 3
    x //= read_col_slots

    bank_pair = x % NUM_BANK_PAIRS
    even_bank = bank_pair * 2
    odd_bank = even_bank + 1
    x //= NUM_BANK_PAIRS

    bg = x % NUM_BANKGROUPS
    x //= NUM_BANKGROUPS

    pc = x % NUM_PSEUDOCHANNELS
    x //= NUM_PSEUDOCHANNELS

    row = x % NUM_ROWS

    # Output writeback is 128B = four 32B units.
    # Use a separate 4-column slot index but keep same channel/pc/bg/bank-pair/row.
    write_col_slots = NUM_COLUMNS // 4
    write_col_base = (logical_chunk % write_col_slots) * 4

    return channel, pc, bg, even_bank, odd_bank, row, read_col_base, write_col_base


def emit_read(f, ch, pc, bg, bank, row, col):
    f.write(f"R {ch},{pc},{bg},{bank},{row},{col}\n")


def gen_naive_block(args):
    rng = random.Random(args.seed)

    embedding_bytes = args.hidden_dim * 2
    num_64b_blocks_per_token = math.ceil(embedding_bytes / 64)

    with open(args.output, "w") as f:
        for _ in range(args.seq_len):
            token_id = rng.randrange(args.vocab_size)

            for b in range(num_64b_blocks_per_token):
                logical_block = token_id * num_64b_blocks_per_token + b
                ch, pc, bg, bank, row, col_base = map_naive_64b_block(
                    logical_block, args.num_channels
                )

                emit_read(f, ch, pc, bg, bank, row, col_base + 0)
                emit_read(f, ch, pc, bg, bank, row, col_base + 1)


def gen_prime_bankpair(args):
    rng = random.Random(args.seed)

    embedding_bytes = args.hidden_dim * 2
    num_64b_blocks_per_token = math.ceil(embedding_bytes / 64)

    # PriME packs two 48B compressed blocks into one 96B chunk.
    num_chunks_per_token = math.ceil(num_64b_blocks_per_token / 2)

    meta_rows = []
    seq_chunk_id = 0

    with open(args.output, "w") as f:
        for _ in range(args.seq_len):
            token_id = rng.randrange(args.vocab_size)

            for c in range(num_chunks_per_token):
                logical_chunk = token_id * num_chunks_per_token + c

                ch, pc, bg, even_bank, odd_bank, row, read_col_base, write_col_base = (
                    map_prime_96b_chunk(logical_chunk, args.num_channels)
                )

                # Compressed 96B read: three 32B columns from even bank.
                emit_read(f, ch, pc, bg, even_bank, row, read_col_base + 0)
                emit_read(f, ch, pc, bg, even_bank, row, read_col_base + 1)
                emit_read(f, ch, pc, bg, even_bank, row, read_col_base + 2)

                meta_rows.append({
                    "seq_chunk_id": seq_chunk_id,
                    "token_id": token_id,
                    "chunk_in_token": c,
                    "logical_chunk": logical_chunk,
                    "channel": ch,
                    "pseudochannel": pc,
                    "bankgroup": bg,
                    "even_bank": even_bank,
                    "odd_bank": odd_bank,
                    "row": row,
                    "read_col_base": read_col_base,
                    "write_col_base": write_col_base,
                })
                seq_chunk_id += 1

    if args.meta_output is not None:
        args.meta_output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.meta_output, "w", newline="") as mf:
            fieldnames = list(meta_rows[0].keys()) if meta_rows else [
                "seq_chunk_id",
                "token_id",
                "chunk_in_token",
                "logical_chunk",
                "channel",
                "pseudochannel",
                "bankgroup",
                "even_bank",
                "odd_bank",
                "row",
                "read_col_base",
                "write_col_base",
            ]
            writer = csv.DictWriter(mf, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(meta_rows)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--mode",
        choices=["naive_block", "prime_bankpair_readonly"],
        required=True,
    )
    parser.add_argument("--vocab-size", type=int, required=True)
    parser.add_argument("--hidden-dim", type=int, required=True)
    parser.add_argument("--seq-len", type=int, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--num-channels", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--meta-output", type=Path, default=None)

    args = parser.parse_args()

    if args.num_channels < 1:
        raise ValueError("--num-channels must be >= 1")

    args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.mode == "naive_block":
        gen_naive_block(args)
    elif args.mode == "prime_bankpair_readonly":
        gen_prime_bankpair(args)
    else:
        raise ValueError(args.mode)

    print(f"Wrote {args.output}")
    if args.meta_output is not None:
        print(f"Wrote {args.meta_output}")


if __name__ == "__main__":
    main()
