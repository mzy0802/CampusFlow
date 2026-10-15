"""Explicit local setup; no installation or weight download during requests."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
if __name__ == '__main__':
    print('Installing local detection dependencies. PyTorch may take several minutes.', flush=True)
    deps = ROOT / '.vision-deps'
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--upgrade', '--target', str(deps),
                           '-r', str(ROOT / 'backend/requirements-vision.txt')])
    environment = dict(os.environ)
    environment['PYTHONPATH'] = str(deps)
    environment['YOLO_CONFIG_DIR'] = str(ROOT / '.vision-config')
    subprocess.check_call([sys.executable, str(ROOT / 'backend/setup_vision.py')], cwd=ROOT, env=environment)
    print('Detection setup complete. Restart with: python run_backend.py', flush=True)
