"""Run explicitly after installing requirements-vision.txt. Downloads official weights."""
from pathlib import Path
import os
from ultralytics import YOLO

target = Path(os.getenv('DETECTION_MODEL', str(Path(__file__).resolve().parents[1] / 'models/yolo11n.pt'))).resolve()
target.parent.mkdir(parents=True, exist_ok=True)
os.chdir(target.parent)
YOLO(target.name)
print(f'Model ready: {target}')
