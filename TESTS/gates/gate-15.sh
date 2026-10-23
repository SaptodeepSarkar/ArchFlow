#!/usr/bin/env bash
# Phase 15 gate (packaging): fresh PREFIX install, unit verify, binary smokes,
# STT env wiring, config-never-overwritten, uninstall-keeps-config.
# Hermetic: HOME+UNIT_DIR point under /tmp so real homes are untouched
# (deviation from the bare `PREFIX=... ./install.sh` form, same code path).
# Exits 0 (GREEN) only if every check passes.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0; fail=0
ok()  { printf '  [GREEN] %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  [RED] %s\n' "$1"; fail=$((fail + 1)); }

T=/tmp/vaani-pkg-test
rm -rf "$T"; mkdir -p "$T/home"

# 0. release binaries exist (build with the real HOME first: the hermetic
#    HOME below has no rustup/cargo config, so the installer must find
#    binaries, not build them).
if cargo build --release -p vaani-key-service -p audio-helper -p stt-manager -p llm-formatter -p typing-helper >"$T/build.log" 2>&1; then
  ok "release binaries build"
else
  bad "release binaries build (see $T/build.log)"
fi

export PREFIX="$T" HOME="$T/home" UNIT_DIR="$T/unit"
export PATH="$T/bin:$PATH"

# 1. fresh install succeeds.
if ./install.sh >"$T/install.log" 2>&1; then
  ok "PREFIX=$T ./install.sh succeeds"
else
  bad "PREFIX=$T ./install.sh succeeds (see $T/install.log)"
fi

# 2. all binaries + the trigger script installed and executable.
miss=""
for b in vaani-key-service capture transcribe llm-format type-text vaani-trigger; do
  [ -x "$T/bin/$b" ] || miss="$miss $b"
done
if [ -z "$miss" ]; then ok "all 6 binaries+trigger in $T/bin"; else bad "binaries installed (missing:$miss)"; fi

# 3. unit file validates.
if systemd-analyze verify "$T/unit/vaani-key.service" >"$T/verify.log" 2>&1; then
  ok "systemd-analyze verify passes"
else
  bad "systemd-analyze verify passes (see $T/verify.log)"
fi
grep -q "^ExecStart=$T/bin/vaani-key-service$" "$T/unit/vaani-key.service" \
  && ok "unit ExecStart points at PREFIX bindir" \
  || bad "unit ExecStart points at PREFIX bindir"
grep -q "^Restart=on-failure$" "$T/unit/vaani-key.service" \
  && ok "unit restart-on-failure" \
  || bad "unit restart-on-failure"
grep -q "StandardOutput=journal" "$T/unit/vaani-key.service" \
  && grep -q "StandardError=journal" "$T/unit/vaani-key.service" \
  && ok "unit logs to journal" \
  || bad "unit logs to journal"

# 4. STT env: installer+gate agree on discovered locations (owed-hardcode cover).
# shellcheck disable=SC1091
if [ -f "$T/vaani-stt.env" ] && . "$T/vaani-stt.env"; then
  ok "vaani-stt.env written and sourced"
else
  bad "vaani-stt.env written and sourced"
fi
if [ -n "${VAANI_STT_PYTHON:-}" ] && "$VAANI_STT_PYTHON" -c "import vosk" >/dev/null 2>&1; then
  ok "VAANI_STT_PYTHON has vosk ($VAANI_STT_PYTHON)"
else
  bad "VAANI_STT_PYTHON has vosk (got '${VAANI_STT_PYTHON:-unset}')"
fi
if [ -n "${VAANI_STT_MODEL:-}" ] && [ -d "$VAANI_STT_MODEL" ]; then
  ok "VAANI_STT_MODEL is a dir ($VAANI_STT_MODEL)"
else
  bad "VAANI_STT_MODEL is a dir (got '${VAANI_STT_MODEL:-unset}')"
fi
grep -q "Environment=VAANI_STT_PYTHON=" "$T/unit/vaani-key.service" \
  && grep -q "Environment=VAANI_STT_MODEL=" "$T/unit/vaani-key.service" \
  && awk '/^\[Install\]/{f=1} f&&/^Environment=/{bad=1} END{exit bad}' "$T/unit/vaani-key.service" \
  && ok "unit carries STT Environment= in [Service]" \
  || bad "unit carries STT Environment= in [Service]"
export VAANI_STT_PYTHON VAANI_STT_MODEL

# 5. installed binaries run.
"$T/bin/vaani-key-service" --handoff-test "gate fifteen" >"$T/smoke-key.log" 2>&1 \
  && grep -q "handoff ok" "$T/smoke-key.log" \
  && ok "vaani-key-service --handoff-test ok" \
  || bad "vaani-key-service --handoff-test ok (see $T/smoke-key.log)"
echo "umm hello world" | "$T/bin/llm-format" >"$T/smoke-llm.log" 2>&1 \
  && [ -s "$T/smoke-llm.log" ] \
  && ok "llm-format formats a line" \
  || bad "llm-format formats a line (see $T/smoke-llm.log)"
if "$T/bin/type-text" >"$T/smoke-type.log" 2>&1; then
  bad "type-text usage exits nonzero (ran without args and passed?)"
else
  grep -q "usage:" "$T/smoke-type.log" && ok "type-text usage smoke" || bad "type-text usage smoke"
fi
if "$T/bin/transcribe" >"$T/smoke-stt.log" 2>&1; then
  bad "transcribe usage exits nonzero (ran without args and passed?)"
else
  grep -q "usage:" "$T/smoke-stt.log" && ok "transcribe usage smoke" || bad "transcribe usage smoke"
fi
if "$T/bin/capture" --secs 0 >"$T/smoke-cap.log" 2>&1 && grep -q "capture samples=" "$T/smoke-cap.log"; then
  ok "capture --secs 0 smoke"
else
  bad "capture --secs 0 smoke (see $T/smoke-cap.log)"
fi

# 6. existing config never overwritten.
CONF="$T/home/.config/vaani/vaani.conf"
if [ -f "$CONF" ] && grep -q "^ui_words = " "$CONF"; then
  ok "default vaani.conf created"
else
  bad "default vaani.conf created"
fi
echo "sentinel = do-not-touch" >"$CONF"
./install.sh >"$T/reinstall.log" 2>&1
if grep -qx "sentinel = do-not-touch" "$CONF"; then
  ok "reinstall keeps existing config byte-identical"
else
  bad "reinstall keeps existing config byte-identical"
fi

# 7. uninstall removes unit+bins, keeps config with a warning.
if ./install.sh --uninstall >"$T/uninstall.log" 2>&1 && grep -q "kept $CONF" "$T/uninstall.log"; then
  ok "uninstall warns config is kept"
else
  bad "uninstall warns config is kept (see $T/uninstall.log)"
fi
left=""; for b in vaani-key-service capture transcribe llm-format type-text; do [ -e "$T/bin/$b" ] && left="$left $b"; done
[ -e "$T/unit/vaani-key.service" ] && left="$left unit"
if [ -z "$left" ]; then ok "uninstall removes bins+unit"; else bad "uninstall removes bins+unit (left:$left)"; fi
if grep -qx "sentinel = do-not-touch" "$CONF"; then
  ok "uninstall keeps config file"
else
  bad "uninstall keeps config file"
fi

printf 'gate-15: %d passed, %d failed\n' "$pass" "$fail"
if [ "$fail" -eq 0 ]; then echo "gate-15 GREEN"; exit 0; else echo "gate-15 RED"; exit 1; fi
