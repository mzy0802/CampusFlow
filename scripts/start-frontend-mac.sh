#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"
if [[ ! -d node_modules ]]; then
  echo "Run: bash scripts/setup-mac.sh" >&2
  exit 1
fi
exec npm run dev -- --port 5173 --strictPort
