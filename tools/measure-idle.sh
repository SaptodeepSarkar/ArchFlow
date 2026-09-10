#!/usr/bin/env bash
# Idle resource report: Economy settled-idle, 10 s after transient helpers exit.
# Reports controller RSS/PSS (process tree), 60 s idle CPU, and checks for
# leaked workers/streams/GPU context. Never touches drop_caches/swap/VM.
set -u
DAEMON="${1:-vaanid}"
echo "== vaani idle report (10s settle, then 60s sample) =="
sleep 10
PIDS=$(pgrep -x "$DAEMON" || true)
if [ -z "$PIDS" ]; then echo "daemon not running"; exit 1; fi
echo "-- process tree RSS/PSS --"
for p in $PIDS; do
  rss=$(awk '/VmRSS/{print $2}' "/proc/$p/status" 2>/dev/null)
  pss=$(awk '/Pss:/{s+=$2} END{print s}' "/proc/$p/smaps" 2>/dev/null)
  echo "pid=$p rss_kb=$rss pss_kb=$pss cmd=$(tr '\0' ' ' < /proc/$p/cmdline)"
done
echo "-- 60s idle CPU sample (per-pid utime+stime delta) --"
declare -A t0
for p in $PIDS; do t0[$p]=$(awk '{print $14+$15}' "/proc/$p/stat" 2>/dev/null); done
sleep 60
for p in $PIDS; do
  t1=$(awk '{print $14+$15}' "/proc/$p/stat" 2>/dev/null)
  hz=$(getconf CLK_TCK)
  echo "pid=$p cpu_pct_60s=$(awk "BEGIN{printf \"%.3f\", (${t1:-0}-${t0[$p]:-0})/$hz/60*100}")"
done
echo "-- leak checks --"
pgrep -x vaani-worker >/dev/null && echo "LEAK: vaani-worker alive at idle (Economy)" || echo "ok: no worker resident"
pw-dump 2>/dev/null | grep -c "vaani" || echo "ok: no vaani pipewire nodes"
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader 2>/dev/null | grep -v "^$" || echo "ok: no GPU compute context"
echo "-- clipboard helper residency --"
pgrep -x wl-copy >/dev/null && echo "NOTE: wl-copy helper alive" || echo "ok: no clipboard helper"
