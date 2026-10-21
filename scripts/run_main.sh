#!/usr/bin/env bash
# Every main run of one model, against a server that is already up (scripts/serve.sh MODEL).
#
#   scripts/run_main.sh qwen3.5-27b                                  run them all, or resume
#   scripts/run_main.sh qwen3.5-27b --only ladder,operator           only these kinds
#   scripts/run_main.sh qwen3.5-27b --skip realism                   every kind but these
#   scripts/run_main.sh qwen3.5-27b --concurrency 16 --timeout 1800  other flags go to every run
#   scripts/run_main.sh qwen3.5-27b --dry-run                        build and check each one
#
# The kinds go in priority order, each in both thinking modes before the next starts (gpt-oss
# has only on): ladder, operator, realism, message, free, load, tier. A run cut short then
# holds whole experiments, most important first. The configs are
# configs/runs/main-KIND-MODEL-MODE.json. Each run is scripts/run_trials.sh, so the same
# command resumes, and it stops at the first run that fails so a broken server does not burn
# through the rest.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
kinds="ladder operator realism message free load tier"
usage() {
    echo "usage: scripts/run_main.sh MODEL [--only K,K] [--skip K,K] [run_trials.sh flags...]" >&2
    echo "kinds, in priority order: $kinds" >&2
    exit 2
}
[ $# -ge 1 ] || usage
model="$1"
shift
only=""; skip=""; pass=()
while [ $# -gt 0 ]; do
    case "$1" in
        --only) [ $# -ge 2 ] || usage; only="${2//,/ }"; shift 2 ;;
        --skip) [ $# -ge 2 ] || usage; skip="${2//,/ }"; shift 2 ;;
        *) pass+=("$1"); shift ;;
    esac
done
for kind in $only $skip; do
    case " $kinds " in *" $kind "*) ;; *) echo "unknown kind: $kind" >&2; usage ;; esac
done
ran=0
for kind in $kinds; do
    if [ -n "$only" ]; then case " $only " in *" $kind "*) ;; *) continue ;; esac; fi
    case " $skip " in *" $kind "*) continue ;; esac
    for mode in nothink think; do
        run="main-$kind-$model-$mode"
        [ -f "$root/configs/runs/$run.json" ] || continue
        echo "== $run" >&2
        "$root/scripts/run_trials.sh" "$run" ${pass[@]+"${pass[@]}"}
        ran=$((ran + 1))
    done
done
if [ "$ran" -eq 0 ]; then
    echo "no main run for $model in configs/runs/" >&2
    exit 2
fi
