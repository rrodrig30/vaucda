#!/usr/bin/env bash
# HIPAA PHI purge — removes every on-disk sink that can hold patient data:
# backend/console logs, debug scratch files, and temp/batch note dirs.
# Safe to run anytime; touches only known-ephemeral PHI locations.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "PHI purge from: $ROOT"

# 1) Backend / console logs (redirected stdout+stderr can contain PHI)
for f in "$ROOT"/logs/backend.log "$ROOT"/backend/logs/backend.log \
         /tmp/vaucda_backend.log; do
  [ -f "$f" ] && : > "$f" && echo "  truncated $f"
done

# 2) Debug scratch files (manual chart/note dumps)
for f in "$ROOT"/logs/input.txt "$ROOT"/logs/output.txt; do
  [ -f "$f" ] && shred -u "$f" 2>/dev/null || rm -f "$f" 2>/dev/null
  [ -e "$f" ] || echo "  removed $f"
done

# 3) Temp / batch note directories (charts + generated notes)
shopt -s nullglob
for d in /tmp/vaucda_batch_* /tmp/vaucda_uploads* /tmp/moreno_* /tmp/adt_* \
         /tmp/villareal* /tmp/vill_* /tmp/hpi_* /tmp/*_out /tmp/*_out2 \
         /tmp/*_out3 /tmp/out_* ; do
  [ -e "$d" ] && rm -rf "$d" && echo "  removed $d"
done
for f in /tmp/adt_smoke*.txt /tmp/adt_smoke*.json /tmp/adt_smoke*.log \
         /tmp/*_note.txt /tmp/moreno_*.log /tmp/adt_*.log ; do
  [ -e "$f" ] && rm -f "$f" && echo "  removed $f"
done

echo "PHI purge complete."
