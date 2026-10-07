#!/usr/bin/env bash
# One-command L1/note eval: deterministic per-class checks on generated notes,
# plus per-field scoring of a candidate extraction vs frozen gold (if present).
#
# Usage:
#   scripts/l1/eval.sh <generated_note_dir> [candidate_label_dir]
#
# Deterministic — immune to LLM-judge variance.
set -euo pipefail
cd "$(dirname "$0")/../.."   # backend/
PY=./venv/bin/python
GEN_DIR="${1:?usage: eval.sh <generated_note_dir> [candidate_label_dir]}"
CAND_DIR="${2:-}"
GOLD_DIR="../tests/l1_gold"
# Infer the matching source input dir from the generated dir's parent.
SRC_DIR="$(dirname "$GEN_DIR")"

echo "############ deterministic per-class checks ############"
PYTHONPATH=. $PY scripts/deterministic_checks.py "$SRC_DIR" "$GEN_DIR" | sed -n '1,8p'

if [ -n "$CAND_DIR" ] && [ -d "$GOLD_DIR/labels" ]; then
  echo
  echo "############ L1 per-field score vs gold ############"
  PYTHONPATH=. $PY scripts/l1/score.py "$GOLD_DIR" "$CAND_DIR"
else
  echo
  echo "(no candidate label dir / gold not frozen yet — skipping per-field score)"
fi
