#!/usr/bin/env bash
# sandbox-run.sh — clean E2E run against the test vault
# Usage: ./scripts/sandbox-run.sh [--model <model-id>]
#   --model  model id from common/models.json (default: deepseek-v4-flash)

set -euo pipefail

usage() {
    echo "Usage: $0 [--model <model-id>]"
    echo ""
    echo "Options:"
    echo "  --model <id>   Model id from common/models.json (default: deepseek-v4-flash)"
    echo "  --help         Show this help"
    echo ""
    echo "Steps:"
    echo "  1. Pause OneDrive      — prompts for confirmation before proceeding"
    echo "  2. Reset Sandbox       — wipes graph/wiki/state, keeps config"
    echo "  3. Setup venv          — activates ~/Droidoes/Obsidian-KDB/.venv"
    echo "  4. Kick off the Run    — kdb-orchestrate --emit-kpis (always on)"
    echo "  5. Add to Leaderboard  — prompts to score run into benchmark leaderboard"
    echo "  6. Graph Viewer HTML   — prompts to generate interactive graph HTML"
    echo "  7. Resume OneDrive     — reminds to re-enable sync"
    exit 0
}

DEFAULT_MODEL="deepseek-v4-flash"
MODEL=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model) MODEL="$2"; shift 2 ;;
        --help|-h) usage ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done
MODEL="${MODEL:-$DEFAULT_MODEL}"

VAULT_ROOT=~/Obsidian/Vault-in-place-test-run
KDB_DIR="$VAULT_ROOT/KDB"
PROJECT_DIR=~/Droidoes/Obsidian-KDB

# ── 1. Pause OneDrive ────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════"
echo "  1. Pause OneDrive"
echo "══════════════════════════════════════════════════════"
echo ""
echo "  The test vault lives inside OneDrive. Syncing during a run"
echo "  can corrupt the Kuzu graph or source notes."
echo ""
echo "  → Pause OneDrive now via the Windows tray icon."
echo ""
read -rp "  OneDrive paused? [Y/n] " yn
case "${yn:-Y}" in
    [Yy]*) echo "  ✓ Proceeding." ;;
    *)     echo "  Aborted."; exit 0 ;;
esac

# ── 2. Reset Sandbox Source ──────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════"
echo "  2. Reset Sandbox Source"
echo "══════════════════════════════════════════════════════"
echo ""
echo "  Wiping: graph  graph-view.html  wiki  state/runs"
echo "          state/manifest.json  state/compile_result.json"
echo "          state/last_orchestrate.json"
echo "  Keeping: state/pipelines.json  KDB-Compiler-System-Prompt.md"
echo ""
(
    cd "$KDB_DIR"
    rm -rf graph graph-view.html wiki \
           state/runs state/manifest.json state/compile_result.json \
           state/last_orchestrate.json
)
echo "  ✓ Reset complete."

# ── 3. Setup venv ────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════"
echo "  3. Setup venv"
echo "══════════════════════════════════════════════════════"
echo ""
cd "$PROJECT_DIR"
# shellcheck disable=SC1091
source .venv/bin/activate
echo "  ✓ venv active: $(which kdb-orchestrate)"

# ── 4. Kick off the Run ──────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════"
echo "  4. Kick off the Run"
echo "══════════════════════════════════════════════════════"
echo ""
CMD="kdb-orchestrate --pipeline vault-test --vault-root $VAULT_ROOT --model $MODEL --emit-kpis"
echo "  $ $CMD"
echo ""
$CMD

echo ""
echo "══════════════════════════════════════════════════════"
echo "  Run complete."
echo "══════════════════════════════════════════════════════"

# ── 5. Add to Leaderboard ────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════"
echo "  5. Add to Leaderboard"
echo "══════════════════════════════════════════════════════"
echo ""
LATEST_RUN=$(ls -1td "$PROJECT_DIR/benchmark/runs/${MODEL}-"* 2>/dev/null | head -1)
if [[ -z "$LATEST_RUN" ]]; then
    echo "  ⚠ No benchmark run dir found for model '$MODEL' — skipping."
else
    LATEST_RUN_DIR=$(basename "$LATEST_RUN")
    echo "  Latest run: $LATEST_RUN_DIR"
    echo ""
    read -rp "  Add this run to the leaderboard? [Y/n] " lb
    case "${lb:-Y}" in
        [Yy]*)
            echo ""
            kdb-benchmark score "$LATEST_RUN_DIR"
            echo ""
            echo "  ✓ Leaderboard updated."
            ;;
        *) echo "  Skipped." ;;
    esac
fi

# ── 6. Generate graph viewer HTML ────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════"
echo "  6. Generate Graph Viewer HTML"
echo "══════════════════════════════════════════════════════"
echo ""
read -rp "  Generate interactive graph viewer HTML? [Y/n] " gen
case "${gen:-Y}" in
    [Yy]*)
        GRAPH_PATH="$KDB_DIR/graph"
        if [[ -n "$LATEST_RUN" ]]; then
            HTML_OUT="$LATEST_RUN/graph-view.html"
        else
            HTML_OUT="$KDB_DIR/graph-view.html"
        fi
        echo ""
        echo "  Generating..."
        python3 "$PROJECT_DIR/tools/viewer/kdb_graph_viewer.py" \
            --graph-path "$GRAPH_PATH" \
            --out "$HTML_OUT"
        echo ""
        echo "  ✓ Graph viewer written to:"
        echo "    $HTML_OUT"
        ;;
    *) echo "  Skipped." ;;
esac

# ── 7. Resume OneDrive ───────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════"
echo "  7. Resume OneDrive"
echo "══════════════════════════════════════════════════════"
echo ""
echo "  → Resume OneDrive sync now via the Windows tray icon."
echo ""
