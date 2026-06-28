#!/usr/bin/env python3
import argparse
import math
import random


def logical_bank_to_addr(logical_bank: int):
    """
    HBM2 address vector:
      [Channel, PseudoChannel, BankGroup, Bank, Row, Column]

    Flattened bank units:
      2 pseudochannels × 4 bankgroups × 4 banks = 32 bank units
    """
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

    # Original FP16 embedding blocks.
    num_64b_blocks = math.ceil(bytes_per_token / 64)

    # XMC compresses each 64B block into 48B.
    # PriME packs two 48B compressed blocks into one 96B chunk.
    num_96b_chunks = math.ceil(num_64b_blocks / 2)

    # HBM2 exported layout has 128 columns per row.
    # In this trace-level model, one column = one 32B transfer.
    cols_per_row = 128

    # Compressed read: 96B = 3 × 32B.
    read_cols_per_chunk = 3
    read_chunks_per_row = cols_per_row // read_cols_per_chunk

    # Decompressed writeback: 128B = 4 × 32B.
    write_cols_per_chunk = 4
    write_chunks_per_row = cols_per_row // write_cols_per_chunk

    bank_capacity = math.ceil(args.vocab_size / args.num_even_banks)

    read_reqs = 0
    write_reqs = 0

    tokens = [random.randrange(args.vocab_size) for _ in range(args.seq_len)]

    with open(args.out, "w") as f:
        for token_id in tokens:
            even_bank = 2 * (token_id // bank_capacity)
            if even_bank >= 32:
                even_bank = 30

            odd_bank = even_bank + 1

            even_pc, even_bg, even_bk = logical_bank_to_addr(even_bank)
            odd_pc, odd_bg, odd_bk = logical_bank_to_addr(odd_bank)

            offset = token_id % bank_capacity

            for chunk in range(num_96b_chunks):
                linear_chunk = offset * num_96b_chunks + chunk

                # Even bank compressed layout: 96B chunks.
                read_row = linear_chunk // read_chunks_per_row
                read_col0 = (linear_chunk % read_chunks_per_row) * read_cols_per_chunk

                # Odd bank decompressed layout: 128B chunks.
                write_row = linear_chunk // write_chunks_per_row
                write_col0 = (linear_chunk % write_chunks_per_row) * write_cols_per_chunk

                # 96B compressed read from Even Bank = 3 × 32B.
                for dc in range(3):
                    f.write(f"R 0,{even_pc},{even_bg},{even_bk},{read_row},{read_col0 + dc}\n")
                    read_reqs += 1

                # 128B decompressed writeback to Odd Bank = 4 × 32B.
                for dc in range(4):
                    f.write(f"W 0,{odd_pc},{odd_bg},{odd_bk},{write_row},{write_col0 + dc}\n")
                    write_reqs += 1

    print("Generated PriME-like HBM2 trace")
    print(f"  output:           {args.out}")
    print(f"  vocab_size:       {args.vocab_size}")
    print(f"  hidden_dim:       {args.hidden_dim}")
    print(f"  seq_len:          {args.seq_len}")
    print(f"  bytes/token:      {bytes_per_token}")
    print(f"  64B blocks/token: {num_64b_blocks}")
    print(f"  96B chunks/token: {num_96b_chunks}")
    print(f"  read requests:    {read_reqs}")
    print(f"  write requests:   {write_reqs}")
    print(f"  total requests:   {read_reqs + write_reqs}")


if __name__ == "__main__":
    main()
