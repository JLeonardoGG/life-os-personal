#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
PNPM="${PNPM:-pnpm}"

"$PYTHON" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e '.[dev]'

if command -v "$PNPM" >/dev/null 2>&1; then
  "$PNPM" install --ignore-scripts --frozen-lockfile=false
  "$PNPM" run build
fi

.venv/bin/lifeos-install
open "http://127.0.0.1:8765/lifeos_dashboard.html?v=v27-local-backend"
