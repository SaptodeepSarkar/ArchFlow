#!/usr/bin/env bash
# Gate 10 (timeouts-offload): after `idle_timeout_s`, killable helpers are
# offloaded; busy helpers are kept alive past the timeout and offloaded once
# idle — never killed mid-work. Pure-logic gate: end-to-end daemon offload
# is Phase 13/14's job.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0; fail=0
ok()  { printf '  [GREEN] %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  [RED] %s\n' "$1"; fail=$((fail + 1)); }

TMP="$(mktemp -d /tmp/vaani-gate10.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

MOD="$ROOT/crates/key-service/src/timeouts.rs"

# 1. module unit tests pass (compiled standalone: main.rs unwired by design)
if rustc --edition 2021 --test "$MOD" -o "$TMP/timeouts_test" >"$TMP/units.log" 2>&1 \
   && "$TMP/timeouts_test" >"$TMP/units.out" 2>&1; then
  N="$(grep -c '^test .* ok$' "$TMP/units.out" || true)"
  ok "timeouts.rs unit tests pass ($N tests)"
else
  bad "timeouts.rs unit tests pass (see $TMP/units.log $TMP/units.out)"
  tail -20 "$TMP/units.log" "$TMP/units.out" 2>/dev/null
fi

# 2. scripted timeline test against a fake clock
cat >"$TMP/timeline.rs" <<'EOF'
#[path = "/home/saptodeep/Projects/Vaani/crates/key-service/src/timeouts.rs"]
mod timeouts;
use timeouts::{decide, Decision, Helper};

fn h(name: &str, last: u64, busy: bool, killable: bool) -> Helper {
    Helper { name: name.into(), last_activity_s: last, busy, killable }
}

fn main() {
    let timeout = 3u64; // idle_timeout_s for this script
    // t=0: both helpers just worked. t=4: past timeout.
    // "stt" is killable at t=4 -> must offload.
    assert_eq!(decide(timeout, 4, false, true), Decision::Offload);
    println!("timeline stt killable past timeout -> offload");
    // "llm" is busy (inferring) at t=4 and still busy at t=100 -> kept alive.
    assert_eq!(decide(timeout, 4, true, false), Decision::KeepAlive);
    assert_eq!(decide(timeout, 100, true, false), Decision::KeepAlive);
    println!("timeline llm busy past timeout -> keep-alive (t=4 and t=100)");
    // "llm" finishes at t=101 (last work t=98... still within? no: idle 3s
    // with timeout 3 -> due) and is killable -> offloaded.
    assert_eq!(decide(timeout, 3, false, true), Decision::Offload);
    println!("timeline llm idle once done -> offload");
    // sweep over a mixed fleet at t=4 matches the per-helper verdicts.
    let fleet = vec![
        h("stt", 0, false, true),  // idle 4s, killable: due
        h("llm", 0, true, false),  // idle 4s, busy: kept
        h("pill", 3, false, true),  // idle 1s: not yet due
    ];
    assert_eq!(timeouts::due_for_offload(timeout, 4, &fleet), vec!["stt".to_string()]);
    println!("timeline sweep at t=4 offloads exactly [stt]");
    println!("timeline OK");
}
EOF
# Portable include: repo path is fixed above; fall back to env override.
sed -i "s|/home/saptodeep/Projects/Vaani|$ROOT|" "$TMP/timeline.rs"
if rustc --edition 2021 -O "$TMP/timeline.rs" -o "$TMP/timeline" >"$TMP/tl-build.log" 2>&1 \
   && "$TMP/timeline" >"$TMP/tl.out" 2>&1; then
  ok "timeline: killable offloaded after timeout / busy kept alive then offloaded"
  grep '^timeline ' "$TMP/tl.out"
else
  bad "timeline test (see $TMP/tl-build.log $TMP/tl.out)"
  cat "$TMP/tl-build.log" "$TMP/tl.out" 2>/dev/null
fi

# 3. key-service config path untouched: idle_timeout_s still comes from
# vaani.conf via vaani-config, and the crate still builds as-is.
if cargo build --release -p vaani-key-service >"$TMP/build.log" 2>&1; then
  ok "vaani-key-service still builds (main.rs untouched)"
else
  bad "vaani-key-service still builds (see $TMP/build.log)"
fi
cargo build -p vaani-config >"$TMP/cfg-build.log" 2>&1
RLIB="$(ls -t "$ROOT/target/debug/libvaani_config.rlib" 2>/dev/null | head -1)"
printf 'idle_timeout_s = 7\n' >"$TMP/vaani.conf"
cat >"$TMP/check_config.rs" <<'EOF'
fn main() {
    let o = vaani_config::load(std::path::Path::new(&std::env::args().nth(1).unwrap()));
    assert!(o.warnings.is_empty());
    assert_eq!(o.config.idle_timeout_s, 7);
    assert_eq!(vaani_config::VaaniConfig::default().idle_timeout_s, 120);
    println!("config idle_timeout_s=7 parsed, default=120");
}
EOF
if [ -n "${RLIB:-}" ] \
   && rustc --edition 2021 --extern "vaani_config=$RLIB" -L "$ROOT/target/debug" \
        "$TMP/check_config.rs" -o "$TMP/check_config" >"$TMP/cfg.log" 2>&1 \
   && "$TMP/check_config" "$TMP/vaani.conf" >"$TMP/cfg.out" 2>&1; then
  ok "config path untouched ($(cat "$TMP/cfg.out"))"
else
  bad "config path untouched (see $TMP/cfg.log $TMP/cfg.out $TMP/cfg-build.log)"
fi

printf 'gate-10: %d passed, %d failed\n' "$pass" "$fail"
if [ "$fail" -eq 0 ]; then echo "gate-10 GREEN"; exit 0; else echo "gate-10 RED"; exit 1; fi
