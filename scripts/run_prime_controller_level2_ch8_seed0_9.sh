#!/usr/bin/env bash
set -euo pipefail

cd ~/prime-repro/ramulator2.1

CONFIG=results/fig8_model_configs.csv
CH=${HBM_CHANNELS:-8}
SEED_BEGIN=${SEED_BEGIN:-0}
SEED_END=${SEED_END:-9}
DECOMP_LATENCY=${DECOMP_LATENCY:-3}
WB_COST=${PRIME_WB_COST:-4}
KEEP_P_TRACE=${KEEP_P_TRACE:-1}
KEEP_COMPLETION_LOGS=${KEEP_COMPLETION_LOGS:-0}
KEEP_CONTROLLER_EVENT_LOGS=${KEEP_CONTROLLER_EVENT_LOGS:-0}

OUT=results/fig8_prime_controller_level2_ch${CH}_seed${SEED_BEGIN}_${SEED_END}.csv

mkdir -p results examples/traces_p logs_prime_controller_tmp logs_prime_controller_summary

echo "model,seq_len,seed,num_channels,num_chunks,prime_final_cycles,dram_controller_cycles,wb_overhead_cycles,wb_overhead_pct" > "$OUT"

for SEED in $(seq "$SEED_BEGIN" "$SEED_END"); do
  tail -n +2 "$CONFIG" | while IFS=, read -r model repo vocab hidden status; do
    SAFE_MODEL=$(echo "$model" | sed 's/[^A-Za-z0-9_]/_/g')

    for L in 128 512 1024 2048; do
      META="examples/meta_bankpair/prime_bankpair_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.meta.csv"
      PTRACE="examples/traces_p/prime_p_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.trace"
      COMPLETION_LOG="logs_prime_controller_tmp/prime_req_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.completion.csv"
      CTRL_EVENT_LOG="logs_prime_controller_tmp/prime_ctrl_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.event.csv"
      RAMLOG="logs_prime_controller_summary/prime_controller_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.ramulator.log"

      if [ ! -f "$META" ]; then
        echo "Missing meta: $META"
        exit 1
      fi

      echo "===== Level 2B PrimeHBM12: seed=$SEED model=$model seq_len=$L ch=$CH ====="

      python3 scripts/gen_prime_p_trace_from_meta.py \
        --meta "$META" \
        --output "$PTRACE" > /dev/null

      rm -f "$COMPLETION_LOG"
      rm -f "${CTRL_EVENT_LOG%.csv}".ch*.csv 2>/dev/null || true

      PYTHONPATH=$PWD/python \
      HBM_CHANNELS="$CH" \
      PRIME_TRACE="$PTRACE" \
      PRIME_DECOMP_LATENCY="$DECOMP_LATENCY" \
      PRIME_WB_COST="$WB_COST" \
      PRIME_REQUEST_COMPLETION_LOG="$COMPLETION_LOG" \
      PRIME_CONTROLLER_EVENT_LOG="$CTRL_EVENT_LOG" \
      python3 examples/prime_hbm2_primecontroller_config.py > "$RAMLOG"

      python3 - "$COMPLETION_LOG" "$RAMLOG" "$model" "$L" "$SEED" "$CH" "$OUT" <<'PY'
import csv
import re
import sys
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

dram_controller_cycles = -1
m = re.search(r"Controller cycles:\s+(\d+)", text)
if m:
    dram_controller_cycles = int(m.group(1))

# For Level 2B, the completion cycle already includes read + decomp + writeback.
# The overhead relative to read-only will be computed in the comparison script.
with open(out, "a", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        model,
        seq_len,
        seed,
        ch,
        num_chunks,
        max_complete,
        dram_controller_cycles,
        "",
        "",
    ])
PY

      if [ "$KEEP_COMPLETION_LOGS" = "0" ]; then
        rm -f "$COMPLETION_LOG"
      fi

      if [ "$KEEP_CONTROLLER_EVENT_LOGS" = "0" ]; then
        rm -f "${CTRL_EVENT_LOG%.csv}".ch*.csv 2>/dev/null || true
      fi

      if [ "$KEEP_P_TRACE" = "0" ]; then
        rm -f "$PTRACE"
      fi
    done
  done
done

echo "Wrote $OUT"
wc -l "$OUT"
