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
KEEP_P_EVENT_LOGS=${KEEP_P_EVENT_LOGS:-0}

OUT=results/fig8_prime_p_level1_ch${CH}_seed${SEED_BEGIN}_${SEED_END}.csv

mkdir -p results examples/traces_p logs_prime_p_tmp logs_prime_p_summary

echo "model,seq_len,seed,num_channels,num_chunks,max_read_done,prime_final_cycles,wb_overhead_cycles,wb_overhead_pct,dram_controller_cycles" > "$OUT"

for SEED in $(seq "$SEED_BEGIN" "$SEED_END"); do
  tail -n +2 "$CONFIG" | while IFS=, read -r model repo vocab hidden status; do
    SAFE_MODEL=$(echo "$model" | sed 's/[^A-Za-z0-9_]/_/g')

    for L in 128 512 1024 2048; do
      META="examples/meta_bankpair/prime_bankpair_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.meta.csv"
      PTRACE="examples/traces_p/prime_p_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.trace"
      EVENTLOG="logs_prime_p_tmp/prime_p_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.event.csv"
      RAMLOG="logs_prime_p_summary/prime_p_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.ramulator.log"

      if [ ! -f "$META" ]; then
        echo "Missing meta: $META"
        exit 1
      fi

      echo "===== Level 1 P command: seed=$SEED model=$model seq_len=$L ch=$CH ====="

      python3 scripts/gen_prime_p_trace_from_meta.py \
        --meta "$META" \
        --output "$PTRACE" > /dev/null

      PYTHONPATH=$PWD/python \
      HBM_CHANNELS="$CH" \
      PRIME_TRACE="$PTRACE" \
      PRIME_DECOMP_LATENCY="$DECOMP_LATENCY" \
      PRIME_WB_COST="$WB_COST" \
      PRIME_P_EVENT_LOG="$EVENTLOG" \
      python3 examples/prime_hbm2_p_config.py > "$RAMLOG"

      python3 - "$EVENTLOG" "$RAMLOG" "$model" "$L" "$SEED" "$CH" "$OUT" <<'PY'
import csv
import sys
import re
from pathlib import Path

eventlog, ramlog, model, seq_len, seed, ch, out = sys.argv[1:]

num_chunks = 0
max_read_done = 0
max_wb_done = 0

with open(eventlog, newline="") as f:
    reader = csv.DictReader(f)
    for r in reader:
        num_chunks += 1
        max_read_done = max(max_read_done, int(r["read_done"]))
        max_wb_done = max(max_wb_done, int(r["wb_done"]))

dram_controller_cycles = -1
text = Path(ramlog).read_text()
m = re.search(r"Controller cycles:\s+(\d+)", text)
if m:
    dram_controller_cycles = int(m.group(1))

overhead_cycles = max_wb_done - max_read_done
overhead_pct = overhead_cycles / max_read_done * 100.0 if max_read_done > 0 else 0.0

with open(out, "a", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        model,
        seq_len,
        seed,
        ch,
        num_chunks,
        max_read_done,
        max_wb_done,
        overhead_cycles,
        overhead_pct,
        dram_controller_cycles,
    ])
PY

      if [ "$KEEP_P_EVENT_LOGS" = "0" ]; then
        rm -f "$EVENTLOG"
      fi

      if [ "$KEEP_P_TRACE" = "0" ]; then
        rm -f "$PTRACE"
      fi
    done
  done
done

echo "Wrote $OUT"
wc -l "$OUT"
