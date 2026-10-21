#!/usr/bin/env bash
# Send one run's trials to a server that is already up, and score every reply.
#
#   scripts/run_trials.sh balanced-qwen3-1.7b                 run it, or resume it
#   scripts/run_trials.sh balanced-qwen3-1.7b --limit 20      a smoke test first
#   scripts/run_trials.sh balanced-qwen3-1.7b --report        where it stands
#   scripts/run_trials.sh balanced-qwen3-1.7b --dry-run       build and check, send nothing
#   scripts/run_trials.sh balanced-qwen3-1.7b --base-url http://gpu-box:8000
#
# The same command resumes: every answer is appended to results/<run>/records.jsonl as it
# lands, and a trial already answered is never sent again. Draws go out breadth first --
# every trial once, then every trial again -- so a run stopped early is a whole
# single-draw dataset. Start the server first with scripts/serve.sh, and check it with
# scripts/preflight.sh. To re-score replies already on disk: scripts/rescore.sh.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m whowins.runner.batch "$@"
