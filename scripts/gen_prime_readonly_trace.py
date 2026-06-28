#!/usr/bin/env python3
import argparse
import math
import random


def logical_bank_to_addr(logical_bank: int):
    pseudochannel = logical_bank // 16
    rem = logical_bank % 16
    bankgroup = rem // 4
    bank = rem % 4
    return pseudochannel, bankgroup, bank


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--vocab-size", type=int, required=True)
    p.add_argument("--hidden-dim", type=int, required=True)
    p.add_argument("--seq-len", type=int, required=True)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--num-even-banks", type=int, default=16)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    random.seed(args.seed)

    bytes_per_token = args.hidden_dim * 2
    num_64b_blocks = math.ceil(bytes_per_token / 64)
    num_96b_chunks = math.ceil(num_64b_blocks / 2)

    cols_per_row = 128
    read_cols_per_chunk = 3
    read_chunks_per_row = cols_per_row // read_cols_per_chunk

    bank_capacity = math.ceil(args.vocab_size / args.num_even_banks)

    read_reqs = 0
    tokens = [random.randrange(args.vocab_size) for _ in range(args.seq_len)]

    with open(args.out, "w") as f:
        for token_id in tokens:
            even_bank = 2 * (token_id // bank_capacity)
            if even_bank >= 32:
                even_bank = 30

            pc, bg, bk = logical_bank_to_addr(even_bank)
            offset = token_id % bank_capacity

            for chunk in range(num_96b_chunks):
                linear_chunk = offset * num_96b_chunks + chunk
                row = linear_chunk // read_chunks_per_row
                col0 = (linear_chunk % read_chunks_per_row) * read_cols_per_chunk

                for dc in range(3):
                    f.write(f"R 0,{pc},{bg},{bk},{row},{col0 + dc}\n")
                    read_reqs += 1

    print("Generated PriME read-only compressed HBM2 trace")
    print(f"  output:           {args.out}")
    print(f"  vocab_size:       {args.vocab_size}")
    print(f"  hidden_dim:       {args.hidden_dim}")
    print(f"  seq_len:          {args.seq_len}")
    print(f"  bytes/token:      {bytes_per_token}")
    print(f"  64B blocks/token: {num_64b_blocks}")
    print(f"  96B chunks/token: {num_96b_chunks}")
    print(f"  read requests:    {read_reqs}")
    print(f"  write requests:   0")
    print(f"  total requests:   {read_reqs}")


if __name__ == "__main__":
    main()
