#!/usr/bin/env bash
# Download the pinned weights of the study's models into the Hugging Face cache.
#
#   scripts/download_models.sh qwen3-1.7b          one model
#   scripts/download_models.sh all                 all fifteen
#   scripts/download_models.sh --print all         show what would be fetched; fetch nothing
#
# Each model is fetched at the one commit the study pins, so the files vLLM loads are
# the files the configs were checked against. It needs huggingface_hub, which comes
# with vLLM. gpt-oss's original/ and metal/ folders are skipped: vLLM loads neither.
# Fetch only the models your machine serves: configs/models.json says which is where.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m whowins.runner.serving download "$@"
