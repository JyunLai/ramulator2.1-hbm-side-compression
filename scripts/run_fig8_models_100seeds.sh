#!/usr/bin/env bash
set -euo pipefail

NUM_SEEDS=${NUM_SEEDS:-100}

mkdir -p results examples/traces

RAW_OUT=results/fig8_ramulator_100seed_raw.csv
AVG_OUT=results/fig8_ramulator_100seed_avg.csv

echo "model,seq_len,seed,naive_cycles,prime_readonly_cycles,naive_reads,prime_reads,prime_chunks,readonly_speedup" > "$RAW_OUT"

tail -n +2 results/fig8_model_configs.csv | while IFS=, read -r model repo vocab hidden status; do
  if [[ -z "$vocab" || -z "$hidden" ]]; then
    echo "[SKIP] $model missing vocab/hidden"
    continue
  fi

  safe_model=$(echo "$model" | tr '/.-' '___')

  for L in 128 512 1024 2048; do
    for seed in $(seq 0 $((NUM_SEEDS - 1))); do
      echo "===== model=$model seq_len=$L seed=$seed ====="

      naive_trace=examples/traces/naive_${safe_model}_seq${L}_seed${seed}.trace
      prime_trace=examples/traces/prime_readonly_${safe_model}_seq${L}_seed${seed}.trace

      python3 scripts/gen_naive_hbm_trace.py \
        --vocab-size "$vocab" \
        --hidden-dim "$hidden" \
        --seq-len "$L" \
        --seed "$seed" \
        --out "$naive_trace" > /dev/null

      python3 scripts/gen_prime_readonly_trace.py \
        --vocab-size "$vocab" \
        --hidden-dim "$hidden" \
        --seq-len "$L" \
        --seed "$seed" \
        --out "$prime_trace" > /dev/null

      PRIME_TRACE="$naive_trace" \
      PYTHONPATH=$PWD/python \
      python3 examples/prime_hbm2_config.py > results/tmp_naive_${safe_model}_${L}_${seed}.log

      PRIME_TRACE="$prime_trace" \
      PYTHONPATH=$PWD/python \
      python3 examples/prime_hbm2_config.py > results/tmp_prime_${safe_model}_${L}_${seed}.log

      naive_cycles=$(grep "Controller cycles" results/tmp_naive_${safe_model}_${L}_${seed}.log | awk '{print $3}')
      prime_cycles=$(grep "Controller cycles" results/tmp_prime_${safe_model}_${L}_${seed}.log | awk '{print $3}')
      naive_reads=$(grep "Read requests" results/tmp_naive_${safe_model}_${L}_${seed}.log | awk '{print $3}')
      prime_reads=$(grep "Read requests" results/tmp_prime_${safe_model}_${L}_${seed}.log | awk '{print $3}')
      prime_chunks=$((prime_reads / 3))

      speedup=$(python3 - << PY
n=float("$naive_cycles")
p=float("$prime_cycles")
print(f"{n/p:.6f}")
PY
)

      echo "$model,$L,$seed,$naive_cycles,$prime_cycles,$naive_reads,$prime_reads,$prime_chunks,$speedup" >> "$RAW_OUT"

      rm -f "$naive_trace" "$prime_trace"
      rm -f results/tmp_naive_${safe_model}_${L}_${seed}.log
      rm -f results/tmp_prime_${safe_model}_${L}_${seed}.log
    done
  done
done

python3 scripts/summarize_fig8_ramulator_100seeds.py

echo "Wrote $RAW_OUT"
echo "Wrote $AVG_OUT"
