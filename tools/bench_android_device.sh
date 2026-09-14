#!/usr/bin/env bash
set -euo pipefail

# Host-side smoke benchmark. It never prints dictated text or records audio.
APK="${1:-android/app/build/outputs/apk/debug/app-debug.apk}"
PACKAGE="org.vaani.keyboard"
ACTIVITY="org.vaani.keyboard/.MainActivity"

if [[ ! -f "$APK" ]]; then
  echo "APK not found: $APK" >&2
  exit 2
fi

mapfile -t DEVICES < <(adb devices | awk '$2 == "device" {print $1}')
if [[ "${#DEVICES[@]}" -ne 1 ]]; then
  echo "Expected exactly one authorized Android device; found ${#DEVICES[@]}." >&2
  adb devices >&2 || true
  exit 3
fi
DEVICE="${DEVICES[0]}"

adb -s "$DEVICE" install -r "$APK" >/dev/null
adb -s "$DEVICE" shell am force-stop "$PACKAGE"
start_ms=$(date +%s%3N)
adb -s "$DEVICE" shell am start -n "$ACTIVITY" >/dev/null
end_ms=$(date +%s%3N)

echo "device=$DEVICE"
echo "package=$PACKAGE"
echo "launch_ms=$((end_ms - start_ms))"
echo "memory_snapshot_begin"
adb -s "$DEVICE" shell dumpsys meminfo "$PACKAGE" | awk '/TOTAL PSS|TOTAL RSS|Private Dirty|Native Heap|Dalvik Heap/ {print}'
echo "memory_snapshot_end"
echo "Speech-to-insertion timing requires a manual utterance on the connected device; this script intentionally does not log audio or transcript text."
