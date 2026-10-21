#!/usr/bin/env bash
# The operator test, the one-message test or the realism set, from a finished run. Calls no
# model and needs no GPU.
#
#   scripts/layouts.sh main-operator-qwen3-14b-think                 every layout and contrast
#   scripts/layouts.sh main-realism-qwen3-14b-think --json r.json    every number, to a file
#
# Each rate is a mean over items, and every contrast pairs two layouts of the same item;
# docs/codebase/17_layouts.md says what each design asks.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m whowins.stats.layouts "$@"
