#!/usr/bin/env bash
set -euo pipefail

cd ~/prime-repro/ramulator2.1

OUT=results/smol135m_channel_sweep.csv
mkdir -p results examples/traces_multich logs_multich

echo "mode,seq_len,seed,num_channels,cycles,reads,writes,row_hits,row_misses,row_conflicts" > "$OUT"

for CH in 1 2 4 8 16 32; do
  for L in 128 512 1024 2048; do
    for MODE in naive prime_readonly; do
      TRACE=examples/traces_multich/${MODE}_smol135m_seq${L}_ch${CH}.trace
      LOG=logs_multich/${MODE}_smol135m_seq${L}_ch${CH}.log

      echo "===== mode=$MODE seq_len=$L channels=$CH ====="

      python3 scripts/gen_embedding_hbm_trace_multich.py \
        --mode "$MODE" \
        --vocab-size 49152 \
        --hidden-dim 576 \
        --seq-len "$L" \
        --seed 0 \
        --num-channels "$CH" \
        --output "$TRACE" > /dev/null

      PYTHONPATH=$PWD/python \
      HBM_CHANNELS="$CH" \
      PRIME_TRACE="$TRACE" \
      python3 examples/prime_hbm2_multich_config.py > "$LOG"

      cycles=$(grep "Controller cycles" "$LOG" | awk '{print $3}')
      reads=$(grep "Read requests" "$LOG" | awk '{print $3}')
      writes=$(grep "Write requests" "$LOG" | awk '{print $3}')
      row_hits=$(grep "Row hits" "$LOG" | awk '{print $3}')
      row_misses=$(grep "Row misses" "$LOG" | awk '{print $3}')
      row_conflicts=$(grep "Row conflicts" "$LOG" | awk '{print $3}')

      echo "$MODE,$L,0,$CH,$cycles,$reads,$writes,$row_hits,$row_misses,$row_conflicts" >> "$OUT"
    done
  done
done

cat "$OUT"