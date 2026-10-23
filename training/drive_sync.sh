#!/usr/bin/env bash
# Mirror the run output to Google Drive every minute, so a dead Colab VM
# leaves the latest state behind. Only the newest checkpoint per stage is kept
# on Drive (older ones are dropped), which is what makes the mirror fit a free
# 15 GB Drive: three STT checkpoints are ~15 GB on their own.
#
# usage: drive_sync.sh [src] [dst] [seconds]
set -uo pipefail

SRC="${1:-${VAANI_OUT_DIR:-/content/vaani-out}}"
DST="${2:-/content/drive/MyDrive/vaani-v8}"
EVERY="${3:-60}"
LOG="${VAANI_DRIVE_SYNC_LOG:-/content/drive_sync.log}"

mkdir -p "$DST"
export SRC DST

mounted() { grep -q " /content/drive " /proc/mounts; }

while true; do
  if ! mounted; then
    echo "$(date -u +%FT%TZ) skip: drive not mounted" >>"$LOG"
  elif [ ! -d "$SRC" ] || [ -z "$(ls -A "$SRC" 2>/dev/null)" ]; then
    echo "$(date -u +%FT%TZ) skip: $SRC empty/missing" >>"$LOG"
  else
    # --delay-updates stages on Drive and renames, so a reader never sees a
    # half-copied checkpoint. Excluded checkpoints survive --delete on purpose.
    flock -n /tmp/vaani-drive-sync.lock bash -c '
      rsync -a --delete --delay-updates --exclude checkpoints "$SRC"/ "$DST"/
      for stage in stt formatter; do
        latest=$(ls -d "$SRC/$stage/checkpoints"/step-* 2>/dev/null | sort | tail -1)
        [ -n "$latest" ] || continue
        name=$(basename "$latest")
        mkdir -p "$DST/$stage/checkpoints"
        find "$DST/$stage/checkpoints" -mindepth 1 -maxdepth 1 -type d ! -name "$name" -exec rm -rf {} +
        rsync -a --delay-updates "$latest"/ "$DST/$stage/checkpoints/$name"/
      done
    ' >>"$LOG" 2>&1
    echo "$(date -u +%FT%TZ) sync rc=$?" >>"$LOG"
  fi
  sleep "$EVERY"
done
