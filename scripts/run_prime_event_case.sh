#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 SAFE_MODEL SEQ_LEN [SEED]"
  echo "Example: $0 SmolLM2_135M 2048 0"
  exit 1
fi

SAFE_MODEL="$1"
SEQ_LEN="$2"
SEED="${3:-0}"
CH="${HBM_CHANNELS:-8}"
DECOMP_LATENCY="${DECOMP_LATENCY:-3}"

TRACE="examples/traces_bankpair/prime_bankpair_${SAFE_MODEL}_seq${SEQ_LEN}_seed${SEED}_ch${CH}.trace"
META="examples/meta_bankpair/prime_bankpair_${SAFE_MODEL}_seq${SEQ_LEN}_seed${SEED}_ch${CH}.meta.csv"

mkdir -p logs_bankpair_event results

COMP="logs_bankpair_event/prime_bankpair_${SAFE_MODEL}_seq${SEQ_LEN}_seed${SEED}_ch${CH}.completion.csv"
RAMLOG="logs_bankpair_event/prime_bankpair_${SAFE_MODEL}_seq${SEQ_LEN}_seed${SEED}_ch${CH}.ramulator.log"
OUT="results/prime_event_${SAFE_MODEL}_seq${SEQ_LEN}_seed${SEED}_ch${CH}.csv"

if [ ! -f "$TRACE" ]; then
  echo "Missing trace: $TRACE"
  exit 1
fi

if [ ! -f "$META" ]; then
  echo "Missing meta: $META"
  exit 1
fi

echo "===== Event-level PriME case ====="
echo "model:   $SAFE_MODEL"
echo "seq_len: $SEQ_LEN"
echo "seed:    $SEED"
echo "ch:      $CH"
echo "trace:   $TRACE"
echo "meta:    $META"
echo

PYTHONPATH=$PWD/python \
HBM_CHANNELS="$CH" \
PRIME_TRACE="$TRACE" \
PRIME_COMPLETION_LOG="$COMP" \
python3 examples/prime_hbm2_multich_config.py | tee "$RAMLOG"

echo
python3 scripts/prime_event_level_scheduler.py \
  --completion-log "$COMP" \
  --meta "$META" \
  --decomp-latency "$DECOMP_LATENCY" \
  --wb-costs 1,4 \
  --output "$OUT"

echo
echo "Wrote:"
echo "  $COMP"
echo "  $RAMLOG"
echo "  $OUT"
