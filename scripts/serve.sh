#!/usr/bin/env bash
# Start the server for one model of the study, with its pinned settings and environment.
#
#   scripts/serve.sh qwen3-1.7b                      serve it (vLLM's default port, 8000)
#   scripts/serve.sh --gpus 2,3 qwen3-14b            serve on the cards you name
#   scripts/serve.sh --tp 2 --gpu-mem 0.85 qwen3-8b  override what the serve file pins
#   scripts/serve.sh --max-seqs 32 qwen3-1.7b        cap how many requests run at once
#   scripts/serve.sh qwen3-1.7b --port 8001          anything else goes to vllm serve
#   scripts/serve.sh --print qwen3-1.7b              show what would run; run nothing
#   scripts/serve.sh --env v100-vllm085 qwen3-4b     a model served in more than one place
#
# Run it on the GPU server, from a checkout of this repository. The settings in
# configs/vllm/<model>.yaml are part of the experiment: an override changes the serving
# snapshot, so it is printed loudly and belongs in the notes for that run.
#
# GPUs. On a shared machine the script picks free cards, or checks the ones you name with
# --gpus, and exports CUDA_VISIBLE_DEVICES. An already-exported CUDA_VISIBLE_DEVICES is
# left alone. --any-gpu skips the check entirely. vLLM takes a fraction of each card's
# total memory, not of what is free, so sharing a card either fails at startup or starves
# the job already on it.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pypath="$root/src${PYTHONPATH:+:$PYTHONPATH}"

usage() {
  echo "usage: scripts/serve.sh [--print] [--env ENV] [--gpus 0,1] [--tp N] [--gpu-mem F]" >&2
  echo "                        [--max-seqs N] [--any-gpu] <model-key> [extra vllm serve flags]" >&2
  echo "model keys: $(PYTHONPATH="$pypath" python3 -m whowins.runner.serving keys | tr '\n' ' ')" >&2
  exit 2
}

print_only=0; env_key=""; gpus=""; tp=""; gpu_mem=""; max_seqs=""; any_gpu=0
while [[ $# -gt 0 ]]; do
  case "${1:-}" in
    --print) print_only=1; shift ;;
    --env) env_key="${2:-}"; [[ -n "$env_key" ]] || usage; shift 2 ;;
    --gpus) gpus="${2:-}"; [[ -n "$gpus" ]] || usage; shift 2 ;;
    --tp) tp="${2:-}"; [[ -n "$tp" ]] || usage; shift 2 ;;
    --gpu-mem) gpu_mem="${2:-}"; [[ -n "$gpu_mem" ]] || usage; shift 2 ;;
    --max-seqs) max_seqs="${2:-}"; [[ -n "$max_seqs" ]] || usage; shift 2 ;;
    --any-gpu) any_gpu=1; shift ;;
    -*) usage ;;
    *) break ;;
  esac
done
[[ $# -ge 1 ]] || usage
key="$1"
shift

settings="$(PYTHONPATH="$pypath" python3 -m whowins.runner.serving shell "$key" ${env_key:+"$env_key"})"
eval "$settings"

cmd=(vllm serve --config "$root/$SERVE_CONFIG")
overrides=()
[[ -n "$tp" ]] && overrides+=(--tensor-parallel-size "$tp")
[[ -n "$gpu_mem" ]] && overrides+=(--gpu-memory-utilization "$gpu_mem")
[[ -n "$max_seqs" ]] && overrides+=(--max-num-seqs "$max_seqs")
if (( ${#overrides[@]} )); then
  cmd+=("${overrides[@]}")
  echo "serve.sh: OVERRIDING the serve file: ${overrides[*]}" >&2
  echo "          vLLM takes the command line over the config file. This is a different" >&2
  echo "          serving snapshot from the one configs/ pins: record it with the run." >&2
fi
if [[ $# -gt 0 ]]; then
  cmd+=("$@")
  echo "serve.sh: extra flags: $*" >&2
  echo "          --host, --port and --api-key change nothing measured. Anything else does: record it." >&2
fi

if (( print_only )); then
  for e in ${EXPORTS[@]+"${EXPORTS[@]}"}; do printf 'export %s\n' "$e"; done
  printf '%q ' "${cmd[@]}"
  printf '\n'
  exit 0
fi

have="$(python3 -c '
try:
    import importlib.metadata as m
    print(m.version("vllm"))
except Exception:
    import vllm
    print(vllm.__version__)
' 2>/dev/null | tail -n 1 || true)"
if [[ "$have" != "$ENGINE_VERSION" ]]; then
  echo "serve.sh: $ENVIRONMENT pins vLLM $ENGINE_VERSION, and this Python has '${have:-no vLLM}'." >&2
  echo "          Activate this machine's environment:  conda activate $CONDA_ENV" >&2
  echo "          Build it if it is not there yet:      scripts/create_env.sh $ENVIRONMENT" >&2
  echo "          A different version is a different serving snapshot. See configs/README.md." >&2
  exit 3
fi

need="${tp:-$GPUS_NEEDED}"
if (( any_gpu )); then
  echo "serve.sh: --any-gpu: not checking whether the cards are free" >&2
elif [[ -n "${CUDA_VISIBLE_DEVICES:-}" && -z "$gpus" ]]; then
  echo "serve.sh: CUDA_VISIBLE_DEVICES is already set to '$CUDA_VISIBLE_DEVICES'; using it" >&2
elif (( EXCLUSIVE_GPUS == 0 )) || [[ -n "$gpus" ]]; then
  if ! chosen="$(PYTHONPATH="$pypath" python3 -m whowins.runner.serving gpus "$key" \
        ${env_key:+"$env_key"} --need "$need" ${gpus:+--want "$gpus"})"; then
    echo "serve.sh: $key needs $need GPU(s) on $ENVIRONMENT. Name others with --gpus," >&2
    echo "          wait for the machine, or pass --any-gpu to try anyway." >&2
    exit 4
  fi
  export CUDA_VISIBLE_DEVICES="$chosen"
  echo "serve.sh: serving on GPU(s) $chosen of $ENVIRONMENT" >&2
fi

for e in ${EXPORTS[@]+"${EXPORTS[@]}"}; do export "$e"; done
exec "${cmd[@]}"
