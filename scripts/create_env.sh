#!/usr/bin/env bash
# Build this machine's conda environment, the one the study's server runs in.
#
#   scripts/create_env.sh --print v100-vllm085    show the commands, run nothing
#   scripts/create_env.sh v100-vllm085            build it
#   scripts/create_env.sh                         which environments there are
#
# Its own environment, never a share of another project's: this study pins an engine
# and a transformers version, and an upgrade made for something else would silently
# become a new serving snapshot here. The pins live in configs/environments.json, and
# `whowins.runner.serving check` refuses them if they disagree with anything else.
#
# conda cannot activate an environment for the shell that started this script, so the
# last line tells you what to run yourself.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pypath="$root/src${PYTHONPATH:+:$PYTHONPATH}"

print_only=0
if [[ "${1:-}" == "--print" ]]; then print_only=1; shift; fi

if [[ $# -eq 0 ]]; then
  echo "environments (key, conda env, who runs it):" >&2
  PYTHONPATH="$pypath" exec python3 -m whowins.runner.serving env
fi

key="$1"
steps="$(PYTHONPATH="$pypath" python3 -m whowins.runner.serving env "$key")"

if (( print_only )); then
  printf '%s\n' "$steps"
  exit 0
fi

command -v conda >/dev/null || { echo "create_env.sh: no conda on this machine" >&2; exit 3; }
eval "$(conda shell.bash hook)"
while IFS= read -r step; do
  [[ -n "$step" ]] || continue
  echo "+ $step" >&2
  eval "$step"
done <<< "$steps"
echo >&2
echo "Done. In a new shell: $(printf '%s\n' "$steps" | grep '^conda activate ')" >&2
