#!/usr/bin/env bash
# Check a running vLLM server against the study's pins before sending it any trial.
#
#   scripts/preflight.sh qwen3-1.7b
#   scripts/preflight.sh qwen3-1.7b --base-url http://gpu-box:8000
#   scripts/preflight.sh qwen3-4b --environment v100-vllm085
#
# Reads the server's /version and /v1/models, neither of which runs the model, and
# checks the chat template in this machine's Hugging Face cache against the pins of
# the environment that server belongs to. Run it on the server host so the cache check
# can be made. Exits 1 if anything fails.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m whowins.runner.preflight "$@"
