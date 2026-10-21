#!/usr/bin/env bash
# The load cell, from a finished load-bundles (or load-cell) run. Calls no model and needs no GPU.
#
#   scripts/load_cell.sh main-load-qwen3-14b-think                 every trial, contrast and check
#   scripts/load_cell.sh main-load-qwen3-14b-think --json l.json   every number, to a file
#
# Each rate is a mean over bundles, the replicates; docs/codebase/16_load_bundles_and_tiers.md
# says what each block answers.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m whowins.stats.load_cell "$@"
