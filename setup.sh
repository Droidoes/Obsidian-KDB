#!/usr/bin/env bash
# all-you-want-to-do-is-to-run-this-damn-script
#
# One-shot bootstrap for a fresh clone:
#   1. create .venv if missing
#   2. install the package (editable) + dev deps
#   3. seed .env from .env.example if .env is missing
#   4. run the test suite as a smoke check
#
# Idempotent: safe to re-run. Re-running just refreshes deps.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

PY="${PYTHON:-python3}"
VENV_DIR=".venv"

echo "==> Using repo root: $REPO_ROOT"

# --- 1. venv --------------------------------------------------------------
if [ ! -d "$VENV_DIR" ]; then
  echo "==> Creating venv at $VENV_DIR"
  "$PY" -m venv "$VENV_DIR"
else
  echo "==> venv already exists at $VENV_DIR (reusing)"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# --- 2. deps --------------------------------------------------------------
echo "==> Upgrading pip"
pip install --quiet --upgrade pip

echo "==> Installing package (editable) + dev extras"
pip install --quiet -e ".[dev]"

# --- 3. .env --------------------------------------------------------------
if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    cp .env.example .env
    echo "==> Seeded .env from .env.example — edit it and fill in ANTHROPIC_API_KEY"
  else
    echo "==> WARNING: no .env.example found; skipping .env bootstrap"
  fi
else
  echo "==> .env already present (leaving alone)"
fi

# --- 4. smoke test --------------------------------------------------------
echo "==> Running test suite"
pytest

cat <<'EOF'

==> Setup complete.

Next steps:
  1. Edit .env and set ANTHROPIC_API_KEY.
  2. Activate the venv:       source .venv/bin/activate
  3. Try the CLIs:            kdb-scan --help    kdb-compile --help
  4. Green-light live compile (costs one API call):
       KDB_RUN_LIVE_API=1 pytest kdb_compiler/tests/test_m2_first_compile.py -s
EOF
