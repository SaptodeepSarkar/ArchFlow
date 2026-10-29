#!/usr/bin/env bash
# The systemd unit carries install.sh's env (server launchers, endpoints, STT
# interpreter); a bare `cargo run` does not, so the daemon would own no servers
# and call the built-in defaults. This is the same run with that env sourced.
set -eu

ENV="${PREFIX:-$HOME/.local}/vaani-stt.env"
if [ -r "$ENV" ]; then . "$ENV"; else echo "dev-run: no $ENV, running without the install's env" >&2; fi
exec cargo run -q --bin vaani-key-service -- "$@"
