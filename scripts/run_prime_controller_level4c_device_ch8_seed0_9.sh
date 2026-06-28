#!/usr/bin/env bash
set -euo pipefail

cd ~/prime-repro/ramulator2.1

CONFIG=results/fig8_model_configs.csv
CH=${HBM_CHANNELS:-8}
SEED_BEGIN=${SEED_BEGIN:-0}
SEED_END=${SEED_END:-9}
DECOMP_LATENCY=${DECOMP_LATENCY:-3}
WB_COST=${PRIME_WB_COST:-4}
MODE=${PRIME_WB_TIMING_MODE:-device}

OUT=results/fig8_prime_controller_level4c_${MODE}_ch${CH}_seed${SEED_BEGIN}_${SEED_END}.csv

mkdir -p results examples/traces_p logs_prime_level4c_tmp logs_prime_level4c_summary

echo "model,seq_len,seed,num_channels,num_chunks,prime_final_cycles,dram_controller_cycles" > "$OUT"

for SEED in $(seq "$SEED_BEGIN" "$SEED_END"); do
  tail -n +2 "$CONFIG" | while IFS=, read -r model repo vocab hidden status; do
    SAFE_MODEL=$(echo "$model" | sed 's/[^A-Za-z0-9_]/_/g')

    for L in 128 512 1024 2048; do
      META="examples/meta_bankpair/prime_bankpair_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.meta.csv"
      PTRACE="examples/traces_p/prime_p_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.trace"
      COMPLETION_LOG="logs_prime_level4c_tmp/prime_req_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}_${MODE}.completion.csv"
      RAMLOG="logs_prime_level4c_summary/prime_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}_${MODE}.ramulator.log"

      if [ ! -f "$META" ]; then
        echo "Missing meta: $META"
        exit 1
      fi

      echo "===== Level 4C ${MODE}: seed=$SEED model=$model seq_len=$L ch=$CH ====="

      python3 scripts/gen_prime_p_trace_from_meta.py \
        --meta "$META" \
        --output "$PTRACE" > /dev/null

      PYTHONPATH=$PWD/python \
      HBM_CHANNELS="$CH" \
      PRIME_TRACE="$PTRACE" \
      PRIME_WB_TIMING_MODE="$MODE" \
      PRIME_DECOMP_LATENCY="$DECOMP_LATENCY" \
      PRIME_WB_COST="$WB_COST" \
      PRIME_REQUEST_COMPLETION_LOG="$COMPLETION_LOG" \
      python3 examples/prime_hbm2_primecontroller_config.py > "$RAMLOG"

      python3 - "$COMPLETION_LOG" "$RAMLOG" "$model" "$L" "$SEED" "$CH" "$OUT" <<'PY'
import csv, re, sys
from pathlib import Path

completion_log, ramlog, model, seq_len, seed, ch, out = sys.argv[1:]

num_chunks = 0
max_complete = 0

with open(completion_log, newline="") as f:
    reader = csv.DictReader(f)
    for r in reader:
        num_chunks += 1
        max_complete = max(max_complete, int(r["complete_cycle"]))

text = Path(ramlog).read_text()
m = re.search(r"Controller cycles:\s+(\d+)", text)
dram_controller_cycles = int(m.group(1)) if m else -1

with open(out, "a", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([model, seq_len, seed, ch, num_chunks, max_complete, dram_controller_cycles])
PY

      rm -f "$COMPLETION_LOG"
    done
  done
done

echo "Wrote $OUT"
wc -l "$OUT"
