#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python3 -m venv "$ROOT/.venv"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
python -m pip install -U pip
python -m pip install -e "$ROOT"
echo
echo "FoldScan installed."
echo "  source $ROOT/.venv/bin/activate"
echo "  foldscan scan ~"
echo "  foldscan serve ~"
