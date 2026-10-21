#!/usr/bin/env bash
# Report what a finished run did, from the replies already on disk. No GPU, no server.
#
#   scripts/analyse.sh balanced-qwen3-1.7b                     every section
#   scripts/analyse.sh balanced-qwen3-1.7b --section position solo
#   scripts/analyse.sh balanced-qwen3-1.7b --json report.json  the same numbers, to a file
#
# It fits nothing and predicts nothing: descriptive counts and Wilson intervals over
# what is in records.jsonl, and no model of any kind behind them. The choice model and
# the composition test are scripts/strengths.sh, the power simulation is
# scripts/phase1.sh, and this is not them.
#
# Write the JSON for every run and two rungs of the ladder can be compared without
# anybody re-deriving a number by hand -- which is how two runs stop being comparable.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m whowins.runner.analyse "$@"
