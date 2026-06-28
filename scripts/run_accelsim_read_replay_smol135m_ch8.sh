#!/usr/bin/env bash
set -euo pipefail

OUT=results/accelsim_read_replay_smol135m_ch8.csv
mkdir -p results logs_accelsim_replay

echo "model,seq_len,channels,ramulator_cycles" > "$OUT"

for L in 128 512 1024 2048; do
  TRACE=$PWD/traces_accelsim_replay/smol135m_seq${L}_reads_ch8.trace
  LOG=$PWD/logs_accelsim_replay/smol135m_seq${L}_reads_ch8.log

  echo "===== Ramulator replay SmolLM2-135M seq=$L ch=8 =====" >&2

  PYTHONPATH=$PWD/python \
  PRIME_TRACE="$TRACE" \
  HBM_CHANNELS=8 \
  python3 examples/prime_hbm2_multich_config.py \
    > "$LOG" 2>&1

  cycles=$(grep -E "Controller cycles" "$LOG" | tail -1 | awk '{print $NF}')

  if [[ -z "$cycles" ]]; then
    echo "[ERROR] cannot extract Controller cycles from $LOG" >&2
    tail -80 "$LOG" >&2
    exit 1
  fi

  echo "SmolLM2-135M,$L,8,$cycles" | tee -a "$OUT"
done

echo "[DONE] wrote $OUT" >&2
cat "$OUT"
