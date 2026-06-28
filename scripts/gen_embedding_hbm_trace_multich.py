#!/usr/bin/env python3
import argparse
import math
import random
from pathlib import Path


NUM_PSEUDOCHANNELS = 2
NUM_BANKGROUPS = 4
NUM_BANKS = 4
NUM_COLUMNS = 128
NUM_ROWS = 1 << 14


def map_logical_32b_to_hbm(logical_32b, num_channels):
    channel = logical_32b % num_channels
    x = logical_32b // num_channels

    col = x % NUM_COLUMNS
    x //= NUM_COLUMNS

    bank = x % NUM_BANKS
    x //= NUM_BANKS

    bg = x % NUM_BANKGROUPS
    x //= NUM_BANKGROUPS

    pc = x % NUM_PSEUDOCHANNELS
    x //= NUM_PSEUDOCHANNELS

    row = x % NUM_ROWS

    return channel, pc, bg, bank, row, col


def emit_read(f, logical_32b, num_channels):
    ch, pc, bg, bank, row, col = map_logical_32b_to_hbm(logical_32b, num_channels)
    f.write(f"R {ch},{pc},{bg},{bank},{row},{col}\n")


def gen_naive(args):
    rng = random.Random(args.seed)

    embedding_bytes = args.hidden_dim * 2
    num_64b_blocks_per_token = math.ceil(embedding_bytes / 64)

    with open(args.output, "w") as f:
        for _ in range(args.seq_len):
            token_id = rng.randrange(args.vocab_size)

            for b in range(num_64b_blocks_per_token):
                logical_64b = token_id * num_64b_blocks_per_token + b

                # One 64B FP16 block = two 32B HBM column reads.
                emit_read(f, logical_64b * 2 + 0, args.num_channels)
                emit_read(f, logical_64b * 2 + 1, args.num_channels)


def gen_prime_readonly(args):
    rng = random.Random(args.seed)

    embedding_bytes = args.hidden_dim * 2
    num_64b_blocks_per_token = math.ceil(embedding_bytes / 64)

    # PriME packs two 48B compressed blocks into one 96B chunk.
    num_chunks_per_token = math.ceil(num_64b_blocks_per_token / 2)

    with open(args.output, "w") as f:
        for _ in range(args.seq_len):
            token_id = rng.randrange(args.vocab_size)

            for c in range(num_chunks_per_token):
                logical_chunk = token_id * num_chunks_per_token + c

                # One 96B compressed chunk = three 32B HBM column reads.
                emit_read(f, logical_chunk * 3 + 0, args.num_channels)
                emit_read(f, logical_chunk * 3 + 1, args.num_channels)
                emit_read(f, logical_chunk * 3 + 2, args.num_channels)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--mode", choices=["naive", "prime_readonly"], required=True)
    parser.add_argument("--vocab-size", type=int, required=True)
    parser.add_argument("--hidden-dim", type=int, required=True)
    parser.add_argument("--seq-len", type=int, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--num-channels", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()

    if args.num_channels < 1:
        raise ValueError("--num-channels must be >= 1")

    args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.mode == "naive":
        gen_naive(args)
    elif args.mode == "prime_readonly":
        gen_prime_readonly(args)
    else:
        raise ValueError(args.mode)

    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()