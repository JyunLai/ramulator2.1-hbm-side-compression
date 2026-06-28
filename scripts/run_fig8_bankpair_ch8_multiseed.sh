#!/usr/bin/env bash
set -euo pipefail

cd ~/prime-repro/ramulator2.1

CONFIG=results/fig8_model_configs.csv
CH=${HBM_CHANNELS:-8}
SEED_BEGIN=${SEED_BEGIN:-0}
SEED_END=${SEED_END:-9}

OUT=results/fig8_ramulator_bankpair_ch${CH}_seed${SEED_BEGIN}_${SEED_END}_raw.csv

mkdir -p results examples/traces_bankpair examples/meta_bankpair logs_bankpair

echo "model,seq_len,seed,num_channels,naive_cycles,prime_readonly_cycles,naive_reads,prime_reads,prime_chunks,max_chunks_per_channel,max_chunks_per_odd_bank,prime_speedup" > "$OUT"

for SEED in $(seq "$SEED_BEGIN" "$SEED_END"); do
  tail -n +2 "$CONFIG" | while IFS=, read -r model repo vocab hidden status; do
    for L in 128 512 1024 2048; do
      SAFE_MODEL=$(echo "$model" | sed 's/[^A-Za-z0-9_]/_/g')

      NAIVE_TRACE=examples/traces_bankpair/naive_block_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.trace
      PRIME_TRACE=examples/traces_bankpair/prime_bankpair_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.trace
      PRIME_META=examples/meta_bankpair/prime_bankpair_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.meta.csv

      NAIVE_LOG=logs_bankpair/naive_block_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.log
      PRIME_LOG=logs_bankpair/prime_bankpair_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.log

      echo "===== seed=$SEED model=$model seq_len=$L channels=$CH ====="

      python3 scripts/gen_embedding_hbm_trace_bankpair.py \
        --mode naive_block \
        --vocab-size "$vocab" \
        --hidden-dim "$hidden" \
        --seq-len "$L" \
        --seed "$SEED" \
        --num-channels "$CH" \
        --output "$NAIVE_TRACE" > /dev/null

      python3 scripts/gen_embedding_hbm_trace_bankpair.py \
        --mode prime_bankpair_readonly \
        --vocab-size "$vocab" \
        --hidden-dim "$hidden" \
        --seq-len "$L" \
        --seed "$SEED" \
        --num-channels "$CH" \
        --output "$PRIME_TRACE" \
        --meta-output "$PRIME_META" > /dev/null

      PYTHONPATH=$PWD/python \
      HBM_CHANNELS="$CH" \
      PRIME_TRACE="$NAIVE_TRACE" \
      python3 examples/prime_hbm2_multich_config.py > "$NAIVE_LOG"

      PYTHONPATH=$PWD/python \
      HBM_CHANNELS="$CH" \
      PRIME_TRACE="$PRIME_TRACE" \
      python3 examples/prime_hbm2_multich_config.py > "$PRIME_LOG"

      naive_cycles=$(grep "Controller cycles" "$NAIVE_LOG" | awk '{print $3}')
      prime_cycles=$(grep "Controller cycles" "$PRIME_LOG" | awk '{print $3}')
      naive_reads=$(grep "Read requests" "$NAIVE_LOG" | awk '{print $3}')
      prime_reads=$(grep "Read requests" "$PRIME_LOG" | awk '{print $3}')

      meta_stats=$(python3 - "$PRIME_META" <<'PY'
import csv
import sys
from collections import Counter

path = sys.argv[1]

per_channel = Counter()
per_odd_bank = Counter()
total = 0

with open(path, newline="") as f:
    reader = csv.DictReader(f)
    for r in reader:
        total += 1
        ch = int(r["channel"])
        pc = int(r["pseudochannel"])
        bg = int(r["bankgroup"])
        odd = int(r["odd_bank"])

        per_channel[ch] += 1
        per_odd_bank[(ch, pc, bg, odd)] += 1

max_ch = max(per_channel.values()) if per_channel else 0
max_odd = max(per_odd_bank.values()) if per_odd_bank else 0

print(f"{total},{max_ch},{max_odd}")
PY
)

      IFS=, read -r prime_chunks max_chunks_per_channel max_chunks_per_odd_bank <<< "$meta_stats"

      speedup=$(python3 - <<PY
n = float("$naive_cycles")
p = float("$prime_cycles")
print(n / p)
PY
)

      echo "$model,$L,$SEED,$CH,$naive_cycles,$prime_cycles,$naive_reads,$prime_reads,$prime_chunks,$max_chunks_per_channel,$max_chunks_per_odd_bank,$speedup" >> "$OUT"
    done
  done
done

echo "Wrote $OUT"
wc -l "$OUT"
