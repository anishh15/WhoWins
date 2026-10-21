#!/usr/bin/env bash
# The phase-1 gate: does the strengths fit recover a truth, and does the
# pipeline detect the published pairwise-insufficiency counterexample?
#
#   scripts/phase1.sh                      the gate, about 50 seconds
#   scripts/phase1.sh --full               more replicates and more sizes, about 5 minutes
#   scripts/phase1.sh --json phase1.json   every number, to a file
#
# Exits non-zero if any check fails. Everything it runs is SIMULATED: no model
# is called and no run is read. The composition test on real data is
# scripts/strengths.sh <run>.
#
# Passing this does not release phase 2 on its own: the command prints what it is
# silent about. There is no pre-registration, by the owner's decision, so every
# result is exploratory.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m whowins.stats.phase1 "$@"
