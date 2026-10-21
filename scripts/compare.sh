#!/usr/bin/env bash
# Two or more finished runs, read side by side. No GPU, no server.
#
#   scripts/analyse.sh balanced-qwen3-1.7b --json /tmp/a.json
#   scripts/analyse.sh balanced-qwen3-14b  --json /tmp/b.json
#   scripts/compare.sh /tmp/a.json /tmp/b.json
#
# It exists for the questions that are about the COLLECTION rather than about a
# run: "this model could not produce that option unopposed" is about the model,
# "no model can" is about the item, and only the second is grounds to go and
# read the scenario. One run cannot tell them apart.
#
# It fits nothing and tests nothing. It intersects lists and lines up numbers
# `analyse` already computed. Exits non-zero if the runs were scored by
# different checkers, because then every column mixes the instrument with the
# model -- which has happened here once already.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m whowins.runner.compare "$@"
