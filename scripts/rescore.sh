#!/usr/bin/env bash
# Score a finished run again, with today's checkers, against the replies already
# on disk. Calls no model and needs no GPU.
#
#   scripts/rescore.sh initial-qwen3-1.7b                what today's checkers say
#   scripts/rescore.sh initial-qwen3-1.7b --changed 20   the trials whose verdict moved
#   scripts/rescore.sh initial-qwen3-1.7b --write        also write rescored.jsonl
#
# records.jsonl is never touched: it is what came back from the server, and the
# rescore is a second file beside it.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m whowins.runner.rescore "$@"
