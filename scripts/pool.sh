#!/usr/bin/env bash
# One fit across several finished runs: strengths every run shares, with a random shift of each
# source per model and, where the design can tell them apart, per harness. No GPU.
#
#   scripts/pool.sh main-ladder-qwen3-0.6b-nothink main-ladder-qwen3-1.7b-nothink ...
#   scripts/pool.sh RUN RUN --json pooled.json                  every number, to a file
#
# Reads each run's pairs, decided draws only. A harness is fitted only when some model was served
# in more than one; otherwise it says why it was left out.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m whowins.stats.pooled "$@"
