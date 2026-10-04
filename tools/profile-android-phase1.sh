#!/usr/bin/env bash
# Read-only profiling. Run the same workload on baseline and candidate APKs.
set -euo pipefail
label="${1:-idle}"
duration="${2:-60}"
if [[ ! "$label" =~ ^[a-zA-Z0-9_-]+$ ]] || [[ ! "$duration" =~ ^[0-9]+$ ]] || (( duration < 5 || duration > 3600 )); then
  echo 'usage: profile-android-phase1.sh LABEL [SECONDS: 5..3600]' >&2
  exit 2
fi
adb_args=()
if [[ -n "${ANDROID_SERIAL:-}" ]]; then adb_args=(-s "$ANDROID_SERIAL"); fi
adb "${adb_args[@]}" get-state >/dev/null
package=org.vaani.keyboard
output="${VAANI_PROFILE_ROOT:-.vaani/phase1-profile}/$(date -u +%Y%m%dT%H%M%SZ)-$label"
mkdir -p "$output"
chmod 700 "$output"
adb "${adb_args[@]}" shell getprop ro.product.model > "$output/device-model.txt"
adb "${adb_args[@]}" shell getprop ro.build.version.sdk > "$output/api-level.txt"
adb "${adb_args[@]}" shell dumpsys package "$package" | awk '/versionCode=|versionName=/ {print}' > "$output/app-version.txt"
adb "${adb_args[@]}" shell dumpsys batterystats --checkin > "$output/battery-start.csv"
printf 'workload=%s\nrequested_seconds=%s\n' "$label" "$duration" > "$output/run.txt"
start=$SECONDS
while (( SECONDS - start < duration )); do
  sample=$((SECONDS - start))
  adb "${adb_args[@]}" shell dumpsys meminfo "$package" > "$output/memory-$sample.txt"
  adb "${adb_args[@]}" shell dumpsys cpuinfo | awk '/org\.vaani\.keyboard/ {print}' > "$output/cpu-$sample.txt"
  adb "${adb_args[@]}" shell cmd appops get "$package" RECORD_AUDIO > "$output/microphone-$sample.txt"
  sleep 5
done
adb "${adb_args[@]}" shell dumpsys batterystats --checkin > "$output/battery-end.csv"
printf 'observed_seconds=%s\n' "$((SECONDS - start))" >> "$output/run.txt"
echo "Profile saved locally in $output. Raw results stay ignored; publish only reviewed aggregate metrics."
