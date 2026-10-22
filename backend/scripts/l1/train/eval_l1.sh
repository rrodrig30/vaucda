#!/usr/bin/env bash
# Evaluate a fine-tuned L1 adapter against the FROZEN GOLD (the answer key),
# alongside the regex baseline it must beat.
#
# Usage: scripts/l1/train/eval_l1.sh <adapter_dir> [base_model]
set -euo pipefail
cd "$(dirname "$0")/../../.."   # -> backend/
PY=python
ADAPTER="${1:?usage: eval_l1.sh <adapter_dir> [base_model]}"
BASE="${2:-google/medgemma-27b-text-it}"
GOLD=../tests/l1_gold
OUT=../tests/l1_model/pred_gold

echo "### generating L1 predictions on the gold segments ###"
$PY scripts/l1/train/predict_l1.py "$ADAPTER" "$GOLD" "$OUT" --base "$BASE"

echo
echo "################  REGEX BASELINE (the bar)  ################"
$PY scripts/l1/score.py "$GOLD" ../tests/l1_gold_regex

echo
echo "################  FINE-TUNED L1 vs GOLD  ################"
$PY scripts/l1/score.py "$GOLD" "$OUT"
echo
echo "Target: beat the baseline on treatment-event recall (0.07) and diagnoses"
echo "recall (0.18); grade-by-system should stay >=0.9."
