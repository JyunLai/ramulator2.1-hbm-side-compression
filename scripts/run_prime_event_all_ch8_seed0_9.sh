#!/usr/bin/env bash
set -euo pipefail

cd ~/prime-repro/ramulator2.1

CONFIG=results/fig8_model_configs.csv
CH=${HBM_CHANNELS:-8}
SEED_BEGIN=${SEED_BEGIN:-0}
SEED_END=${SEED_END:-9}
DECOMP_LATENCY=${DECOMP_LATENCY:-3}
KEEP_COMPLETION_LOGS=${KEEP_COMPLETION_LOGS:-0}

OUT=results/fig8_prime_event_ch${CH}_seed${SEED_BEGIN}_${SEED_END}.csv

mkdir -p results logs_bankpair_event_tmp logs_bankpair_event_summary

echo "model,seq_len,seed,num_channels,num_chunks,num_reads,read_only_cycles,event_decomp_cycles,event_decomp_wb1_cycles,event_decomp_wb4_cycles,wb1_overhead_pct,wb4_overhead_pct" > "$OUT"

for SEED in $(seq "$SEED_BEGIN" "$SEED_END"); do
  tail -n +2 "$CONFIG" | while IFS=, read -r model repo vocab hidden status; do
    SAFE_MODEL=$(echo "$model" | sed 's/[^A-Za-z0-9_]/_/g')

    for L in 128 512 1024 2048; do
      TRACE="examples/traces_bankpair/prime_bankpair_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.trace"
      META="examples/meta_bankpair/prime_bankpair_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.meta.csv"

      COMP="logs_bankpair_event_tmp/prime_bankpair_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.completion.csv"
      RAMLOG="logs_bankpair_event_summary/prime_bankpair_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.ramulator.log"
      SCHED_OUT="logs_bankpair_event_summary/prime_bankpair_${SAFE_MODEL}_seq${L}_seed${SEED}_ch${CH}.event.csv"

      if [ ! -f "$TRACE" ]; then
        echo "Missing trace: $TRACE"
        exit 1
      fi

      if [ ! -f "$META" ]; then
        echo "Missing meta: $META"
        exit 1
      fi

      echo "===== seed=$SEED model=$model seq_len=$L ch=$CH ====="

      PYTHONPATH=$PWD/python \
      HBM_CHANNELS="$CH" \
      PRIME_TRACE="$TRACE" \
      PRIME_COMPLETION_LOG="$COMP" \
      python3 examples/prime_hbm2_multich_config.py > "$RAMLOG"

      python3 scripts/prime_event_level_scheduler.py \
        --completion-log "$COMP" \
        --meta "$META" \
        --decomp-latency "$DECOMP_LATENCY" \
        --wb-costs 1,4 \
        --output "$SCHED_OUT" > /dev/null

      python3 - "$SCHED_OUT" "$model" "$L" "$SEED" "$CH" "$OUT" <<'PY'
import csv
import sys

sched_out, model, seq_len, seed, ch, out = sys.argv[1:]

rows = []
with open(sched_out, newline="") as f:
    reader = csv.DictReader(f)
    for r in reader:
        rows.append(r)

if len(rows) != 2:
    raise RuntimeError(f"Expected 2 rows from scheduler, got {len(rows)} in {sched_out}")

by_wb = {int(r["wb_cost"]): r for r in rows}

r1 = by_wb[1]
r4 = by_wb[4]

read_only = float(r1["read_only_cycles"])
decomp = float(r1["event_decomp_cycles"])
wb1 = float(r1["event_decomp_wb_cycles"])
wb4 = float(r4["event_decomp_wb_cycles"])

num_chunks = int(r1["num_chunks_scheduled"])
num_reads = int(r1["num_reads"])

wb1_overhead = (wb1 - read_only) / read_only * 100.0
wb4_overhead = (wb4 - read_only) / read_only * 100.0

with open(out, "a", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        model,
        seq_len,
        seed,
        ch,
        num_chunks,
        num_reads,
        int(read_only),
        int(decomp),
        int(wb1),
        int(wb4),
        wb1_overhead,
        wb4_overhead,
    ])
PY

      if [ "$KEEP_COMPLETION_LOGS" = "0" ]; then
        rm -f "$COMP"
      fi
    done
  done
done

echo "Wrote $OUT"
wc -l "$OUT"
