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
    p.add_argument("--num-banks", type=int, default=32)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    random.seed(args.seed)

    bytes_per_token = args.hidden_dim * 2
    num_64b_blocks = math.ceil(bytes_per_token / 64)

    cols_per_row = 128
    cols_per_64b_block = 2
    blocks_per_row = cols_per_row // cols_per_64b_block

    bank_capacity = math.ceil(args.vocab_size / args.num_banks)

    read_reqs = 0
    tokens = [random.randrange(args.vocab_size) for _ in range(args.seq_len)]

    with open(args.out, "w") as f:
        for token_id in tokens:
            bank_id = token_id // bank_capacity
            if bank_id >= 32:
                bank_id = 31

            pc, bg, bk = logical_bank_to_addr(bank_id)

            offset = token_id % bank_capacity

            for block in range(num_64b_blocks):
                linear_block = offset * num_64b_blocks + block

                row = linear_block // blocks_per_row
                col0 = (linear_block % blocks_per_row) * cols_per_64b_block

                # 64B FP16 read = 2 x 32B transfers
                for dc in range(2):
                    f.write(f"R 0,{pc},{bg},{bk},{row},{col0 + dc}\n")
                    read_reqs += 1

    print("Generated naive HBM FP16 trace")
    print(f"  output:           {args.out}")
    print(f"  vocab_size:       {args.vocab_size}")
    print(f"  hidden_dim:       {args.hidden_dim}")
    print(f"  seq_len:          {args.seq_len}")
    print(f"  bytes/token:      {bytes_per_token}")
    print(f"  64B blocks/token: {num_64b_blocks}")
    print(f"  read requests:    {read_reqs}")
    print(f"  write requests:   0")
    print(f"  total requests:   {read_reqs}")


if __name__ == "__main__":
    main()