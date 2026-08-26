#!/usr/bin/env bash
# Autoresearch benchmark harness — canonical entrypoint.
# Deterministic: fixed seed, no network, double-run equality guard.
# Emits METRIC lines; exit 0 = valid benchmark, non-zero = failure.
set -euo pipefail
cd "$(dirname "$0")"
exec python scripts/autoresearch_bench.py
