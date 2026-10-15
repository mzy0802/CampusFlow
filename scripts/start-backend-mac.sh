#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -x .venv/bin/python ]]; then
  echo "Run: bash scripts/setup-mac.sh" >&2
  exit 1
fi
export YOLO_CONFIG_DIR="$ROOT/.vision-config"
mkdir -p "$YOLO_CONFIG_DIR"
export DETECTION_DEVICE="${DETECTION_DEVICE:-cpu}"
exec .venv/bin/python run_backend.py
