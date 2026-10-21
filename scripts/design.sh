#!/usr/bin/env bash
# What a run would send, and how evenly. Builds nothing that is sent, no GPU.
#
#   scripts/design.sh ladder-qwen3-14b --balance   # read this before a run
#   scripts/design.sh ladder-qwen3-14b --show 3    # the first 3 trials, rendered
#
# Every other command here has a wrapper that sets PYTHONPATH; this one did not,
# so the command the runbook tells you to run FIRST was the one that failed with
# ModuleNotFoundError.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m whowins.runner.design "$@"
