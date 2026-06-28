#!/usr/bin/env bash
set -euo pipefail

mkdir -p results examples/traces

OUT=results/fig8_ramulator_once.csv
echo "model,seq_len,naive_cycles,prime_readonly_cycles,naive_reads,prime_reads,prime_chunks,readonly_speedup" > "$OUT"

tail -n +2 results/fig8_model_configs.csv | while IFS=, read -r model repo vocab hidden status; do
  if [[ -z "$vocab" || -z "$hidden" ]]; then
    echo "[SKIP] $model missing vocab/hidden"
    continue
  fi

  safe_model=$(echo "$model" | tr '/.-' '___')

  for L in 128 512 1024 2048; do
    echo "===== $model seq_len=$L ====="

    naive_trace=examples/traces/naive_${safe_model}_seq${L}.trace
    prime_trace=examples/traces/prime_readonly_${safe_model}_seq${L}.trace

    python3 scripts/gen_naive_hbm_trace.py \
      --vocab-size "$vocab" \
      --hidden-dim "$hidden" \
      --seq-len "$L" \
      --seed 0 \
      --out "$naive_trace" > /dev/null

    python3 scripts/gen_prime_readonly_trace.py \
      --vocab-size "$vocab" \
      --hidden-dim "$hidden" \
      --seq-len "$L" \
      --seed 0 \
      --out "$prime_trace" > /dev/null

    PRIME_TRACE="$naive_trace" \
    PYTHONPATH=$PWD/python \
    python3 examples/prime_hbm2_config.py > results/tmp_naive_${safe_model}_${L}.log

    PRIME_TRACE="$prime_trace" \
    PYTHONPATH=$PWD/python \
    python3 examples/prime_hbm2_config.py > results/tmp_prime_${safe_model}_${L}.log

    naive_cycles=$(grep "Controller cycles" results/tmp_naive_${safe_model}_${L}.log | awk '{print $3}')
    prime_cycles=$(grep "Controller cycles" results/tmp_prime_${safe_model}_${L}.log | awk '{print $3}')
    naive_reads=$(grep "Read requests" results/tmp_naive_${safe_model}_${L}.log | awk '{print $3}')
    prime_reads=$(grep "Read requests" results/tmp_prime_${safe_model}_${L}.log | awk '{print $3}')
    prime_chunks=$((prime_reads / 3))

    speedup=$(python3 - << PY
n=float("$naive_cycles")
p=float("$prime_cycles")
print(f"{n/p:.4f}")
PY
)

    echo "$model,$L,$naive_cycles,$prime_cycles,$naive_reads,$prime_reads,$prime_chunks,$speedup" >> "$OUT"
  done
done

cat "$OUT"
