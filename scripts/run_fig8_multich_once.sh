#!/usr/bin/env bash
set -euo pipefail

cd ~/prime-repro/ramulator2.1

CONFIG=results/fig8_model_configs.csv
OUT=results/fig8_ramulator_multich_ch${HBM_CHANNELS:-8}_once.csv

CH=${HBM_CHANNELS:-8}
SEED=${SEED:-0}

mkdir -p results examples/traces_multich logs_multich

echo "model,seq_len,seed,num_channels,naive_cycles,prime_readonly_cycles,naive_reads,prime_reads,prime_speedup" > "$OUT"

tail -n +2 "$CONFIG" | while IFS=, read -r model repo vocab hidden status; do
  for L in 128 512 1024 2048; do
    SAFE_MODEL=$(echo "$model" | sed 's/[^A-Za-z0-9_]/_/g')

    NAIVE_TRACE=examples/traces_multich/naive_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.trace
    PRIME_TRACE=examples/traces_multich/prime_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.trace

    NAIVE_LOG=logs_multich/naive_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.log
    PRIME_LOG=logs_multich/prime_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.log

    echo "===== model=$model seq_len=$L seed=$SEED channels=$CH ====="

    python3 scripts/gen_embedding_hbm_trace_multich.py \
      --mode naive \
      --vocab-size "$vocab" \
      --hidden-dim "$hidden" \
      --seq-len "$L" \
      --seed "$SEED" \
      --num-channels "$CH" \
      --output "$NAIVE_TRACE" > /dev/null

    python3 scripts/gen_embedding_hbm_trace_multich.py \
      --mode prime_readonly \
      --vocab-size "$vocab" \
      --hidden-dim "$hidden" \
      --seq-len "$L" \
      --seed "$SEED" \
      --num-channels "$CH" \
      --output "$PRIME_TRACE" > /dev/null

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

    speedup=$(python3 - <<PY
n = float("$naive_cycles")
p = float("$prime_cycles")
print(n / p)
PY
)

    echo "$model,$L,$SEED,$CH,$naive_cycles,$prime_cycles,$naive_reads,$prime_reads,$speedup" >> "$OUT"
  done
done

cat "$OUT"