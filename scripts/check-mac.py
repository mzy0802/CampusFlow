"""Run with .venv/bin/python scripts/check-mac.py after setup."""
from pathlib import Path
import importlib.util
import platform
import sys

root = Path(__file__).resolve().parents[1]
print('OS:', platform.platform())
print('Architecture:', platform.machine())
print('Python:', sys.version.split()[0])
for name in ('fastapi', 'uvicorn', 'cv2', 'sqlite3'):
    print(f'{name}:', 'installed' if importlib.util.find_spec(name) else 'missing')
print('Default vision: Qwen cloud; local model weights are not required.')
if importlib.util.find_spec('torch'):
    import torch
    print('PyTorch:', torch.__version__)
    print('MPS built:', torch.backends.mps.is_built())
    print('MPS available:', torch.backends.mps.is_available())
