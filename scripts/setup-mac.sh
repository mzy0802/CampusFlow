#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
MODE="${1:---vision}"
if [[ "$MODE" != "--vision" && "$MODE" != "--map-only" ]]; then
  echo "Usage: bash scripts/setup-mac.sh [--vision|--map-only]" >&2
  exit 1
fi
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This setup script is for macOS only." >&2
  exit 1
fi
if command -v python3.12 >/dev/null 2>&1; then
  PYTHON=python3.12
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
else
  echo "Install Python 3.12 (macOS universal2/arm64) first." >&2
  exit 1
fi
"$PYTHON" -c 'import sys,platform; assert (3,12)<=sys.version_info[:2]<(3,14), "Use Python 3.12 or 3.13"; assert platform.machine()=="arm64", "Use native arm64 Python and a Terminal without Rosetta"'
command -v node >/dev/null 2>&1 || { echo "Install Node.js 22.12+ arm64 with npm first." >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "npm is missing; reinstall Node.js with npm." >&2; exit 1; }
node -e 'const [a,b]=process.versions.node.split(".").map(Number); if(a<22||(a===22&&b<12)) throw Error("Node.js 22.12+ required"); if(process.arch!=="arm64") throw Error("Use arm64 Node.js")'
if [[ ! -x .venv/bin/python ]]; then
  "$PYTHON" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
if [[ "$MODE" == "--vision" ]]; then
  .venv/bin/python -m pip install -r backend/requirements-mac.txt
  export YOLO_CONFIG_DIR="$ROOT/.vision-config"
  mkdir -p "$YOLO_CONFIG_DIR"
  if [[ ! -f models/yolo11n.pt ]]; then
    .venv/bin/python backend/setup_vision.py
  fi
else
  .venv/bin/python -m pip install -r backend/requirements.txt
fi
(cd frontend && npm ci)
echo
echo "Installation complete. Start these in two Terminal windows:"
echo "  bash scripts/start-backend-mac.sh"
echo "  bash scripts/start-frontend-mac.sh"
echo "Then open http://127.0.0.1:5173/"
