#!/usr/bin/env bash
# A strength per source, fitted to a finished run's conflict data. No GPU.
#
#   scripts/strengths.sh balanced-qwen3-14b
#   scripts/strengths.sh balanced-qwen3-1.7b --log results/balanced-qwen3-1.7b/rescored.jsonl
#   scripts/strengths.sh balanced-qwen3-14b --json strengths.json
#   scripts/strengths.sh ladder-qwen3-14b
#
# A run with triples or a five-way set also gets the composition test: fit the
# pairs, predict the larger sets. On a pairs-only run it says the test cannot run.
# It prints three fits that assume different things -- free pairs, the whole
# design, and the within-message pair whose position effect points the other
# way -- and never pools them.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m whowins.stats.strengths "$@"
