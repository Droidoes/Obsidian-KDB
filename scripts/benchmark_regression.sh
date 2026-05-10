#!/usr/bin/env bash
#
# benchmark_regression.sh — re-fire all active models from the latest final
# scorecard so the resulting final scorecard reflects current code's behavior
# across the full active candidate set.
#
# See `--help` for objective, behavior, output, exit codes, and cost notes.
#

set -euo pipefail

show_help() {
  cat <<'EOF'
benchmark_regression.sh — re-fire all active models from the latest final scorecard

OBJECTIVE
  Build a fresh final scorecard reflecting current code's behavior across the
  full active candidate set. Useful after architectural changes (e.g. a measure
  swap like Task #59's body_link_jaccard → body_emit_set_coverage) that
  invalidate prior cross-model rankings on M-axes whose semantics changed.

BEHAVIOR
  1. Reads benchmark/scores/final/<latest>.json (most recent file by mtime).
  2. Extracts the active model list from `models[].model_id`. Excludes
     anything in `dropped_models[]` (preserved as audit-trail-only).
  3. For each model — sorted alphabetically for predictability — runs:
         kdb-benchmark --models <model_id> --sources benchmark/sources
     using the existing single-model invocation contract (Task #46).
     Each invocation merges its run into a NEW versioned final/<ts>.json
     (Task #42 cross-run merge, default behavior — NOT --no-merge).
  4. Models are fired SERIALLY. Per-fire wall time is 2–10 minutes
     depending on model speed and corpus size; total runtime for the
     current ~8-model active set is roughly 20–30 minutes.
  5. After fire N of N, the latest final/<ts>.json contains all N models
     freshly fired against current code. Intermediate finals from fires
     1..N-1 remain on disk as audit trail of the sweep's progression.

OUTPUT
  - One new versioned final scorecard per model fire (N new files for an
    N-model sweep). The LAST one (after the final fire) is the canonical
    "regression scorecard" representing the full sweep.
  - Per-model run dirs under benchmark/runs/<run_id>/ with state/, vault/,
    score_trace.txt (standard kdb-benchmark Task #36 behavior, unchanged).
  - Per-run scorecards under benchmark/scores/runs/<scorecard_id>.{json,txt}
    (standard Task #38 sidecar behavior, unchanged).

USAGE
  scripts/benchmark_regression.sh [--help|-h]

  No arguments needed. Always reads the latest final scorecard for the model
  list and uses benchmark/sources/ as the corpus. The script must be invoked
  from a shell with kdb-benchmark on PATH (i.e. the repo's venv activated).

EXIT CODES
  0    — all model fires succeeded.
  N>0  — N model fires failed. The script continues past failures so a single
         flaky provider doesn't abort the entire sweep; check stderr for the
         list of failed model_ids. The latest final scorecard contains all
         models that DID succeed.

DESIGN NOTES
  - Single-model-per-invocation kept intact: Task #46 locked `kdb-benchmark`
    to one `--models` value per fire. This script orchestrates many fires
    rather than batching them server-side.
  - Default merge kept intact: each invocation goes through kdb-benchmark's
    Task #42 cross-run merge, producing a fresh final at each step. This
    leaves a chain of finals that documents the sweep's progression — and
    means you can interrupt the sweep mid-way and still have a partial final.
  - Per project memory `feedback_user_fires_api_cost_runs`, this script is
    intended to be run interactively by the user. It costs money to run;
    the current 8-model active set runs about ~$1.20 against the canonical
    5-source corpus. Don't invoke from automation without budget awareness.
  - Per memory `feedback_no_imaginary_risk`, this is a single-user single-
    machine tool. No locking, no daemon, no retry queues. Run, watch the
    output, intervene if anything looks off.

EOF
}

# Parse flags
case "${1:-}" in
  -h|--help)
    show_help
    exit 0
    ;;
  "")
    ;;
  *)
    echo "error: unrecognized argument '$1' (try --help)" >&2
    exit 64
    ;;
esac

# Anchor to repo root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# 1. Find latest final scorecard
LATEST_FINAL="$(ls -1t benchmark/scores/final/*.json 2>/dev/null | head -1 || true)"
if [[ -z "$LATEST_FINAL" ]]; then
  echo "error: no final scorecards found in benchmark/scores/final/" >&2
  echo "       (run kdb-benchmark at least once before regression-sweeping)" >&2
  exit 1
fi
echo "Source of model list: $LATEST_FINAL"

# 2. Extract active model list (excluding dropped_models), alphabetically sorted
MODELS="$(python3 -c "
import json, sys
with open('$LATEST_FINAL') as f:
    d = json.load(f)
active = {m['model_id'] for m in d.get('models', []) if isinstance(m, dict) and 'model_id' in m}
dropped = {m['model_id'] for m in d.get('dropped_models', []) if isinstance(m, dict) and 'model_id' in m}
for mid in sorted(active - dropped):
    print(mid)
")"

if [[ -z "$MODELS" ]]; then
  echo "error: no active models in latest final scorecard" >&2
  exit 1
fi

N_MODELS=$(printf '%s\n' "$MODELS" | wc -l | tr -d ' ')
echo "Active models ($N_MODELS):"
printf '  - %s\n' $MODELS

# 3. Fire each model serially
START_TS="$(date -Iseconds)"
echo
echo "================================================================"
echo "Regression sweep starting at $START_TS"
echo "================================================================"

FAILED_MODELS=()
i=0
while IFS= read -r model; do
  [[ -z "$model" ]] && continue
  i=$((i + 1))
  echo
  echo "[$i/$N_MODELS] firing: $model"
  echo "----------------------------------------------------------------"
  if kdb-benchmark --models "$model" --sources benchmark/sources; then
    echo "[$i/$N_MODELS] $model: ✓ done"
  else
    rc=$?
    echo "[$i/$N_MODELS] $model: ✗ FAILED (exit $rc)" >&2
    FAILED_MODELS+=("$model")
  fi
done <<< "$MODELS"

# 4. Summary
END_TS="$(date -Iseconds)"
echo
echo "================================================================"
echo "Regression sweep finished at $END_TS"
echo "================================================================"

NEW_LATEST="$(ls -1t benchmark/scores/final/*.json 2>/dev/null | head -1 || true)"
if [[ -n "$NEW_LATEST" ]]; then
  echo "Latest final scorecard: $NEW_LATEST"
  TXT_SIDECAR="${NEW_LATEST%.json}.txt"
  if [[ -f "$TXT_SIDECAR" ]]; then
    echo "Render sidecar:         $TXT_SIDECAR"
  fi
fi

if [[ ${#FAILED_MODELS[@]} -gt 0 ]]; then
  echo
  echo "FAILURES (${#FAILED_MODELS[@]}):" >&2
  for m in "${FAILED_MODELS[@]}"; do
    echo "  - $m" >&2
  done
  exit "${#FAILED_MODELS[@]}"
fi

echo
echo "All $N_MODELS models fired successfully."
exit 0
