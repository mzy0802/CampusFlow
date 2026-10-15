"""Run with .venv/bin/python scripts/check-mac.py after setup."""
from pathlib import Path
import importlib.util
import platform
import sys

root = Path(__file__).resolve().parents[1]
print('OS:', platform.platform())
print('Architecture:', platform.machine())
print('Python:', sys.version.split()[0])
for name in ('fastapi', 'uvicorn', 'ultralytics', 'cv2', 'torch'):
    print(f'{name}:', 'installed' if importlib.util.find_spec(name) else 'missing')
print('Model weights:', 'present' if (root/'models/yolo11n.pt').is_file() else 'missing')
if importlib.util.find_spec('torch'):
    import torch
    print('PyTorch:', torch.__version__)
    print('MPS built:', torch.backends.mps.is_built())
    print('MPS available:', torch.backends.mps.is_available())
