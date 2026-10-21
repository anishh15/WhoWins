#!/usr/bin/env bash
# Capacity on declared tiers, from a finished declared-tiers run. Calls no model and needs no GPU.
#
#   scripts/capacity.sh main-tier-qwen3-14b-think              R(q) at 0.9, 0.95 and 0.99
#   scripts/capacity.sh main-tier-qwen3-14b-think --q 0.97     at one reliability
#   scripts/capacity.sh main-tier-qwen3-14b-think --json c.json  every number, to a file
#
# R(q) is the largest set of tiers the model keeps in the stated order, with a lower and an
# upper bound that hold together. docs/codebase/11_statistics.md says how it is computed.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m whowins.stats.capacity "$@"
