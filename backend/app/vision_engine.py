"""Lazy, local-only YOLO inference. Model download is an explicit setup step."""
from pathlib import Path
import importlib.util
import os
from .vision_postprocess import tile_origins, merge_detections

ROOT = Path(__file__).resolve().parents[2]
MODEL_FILE = Path(os.getenv('DETECTION_MODEL', str(ROOT / 'models' / 'yolo11n.pt')))
os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / '.vision-config'))


def readiness():
    dependencies = all(importlib.util.find_spec(name) is not None for name in ('ultralytics', 'cv2', 'torch'))
    return {'ready': dependencies and MODEL_FILE.is_file(), 'dependencies_installed': dependencies,
            'weights_installed': MODEL_FILE.is_file(), 'model': MODEL_FILE.name,
            'message': '模型可用，首次任务需加载模型。' if dependencies and MODEL_FILE.is_file()
            else '请先运行识别环境安装脚本并重启后端。',
            'classes': ['person', 'bicycle', 'motorcycle'],
            'classification_note': 'motorcycle 仅作为电动两轮车/摩托车候选，尚非专用电动车分类。',
            'inference_mode': 'full_frame_and_overlapping_tiles',
            'device': os.getenv('DETECTION_DEVICE', 'cpu')}


class VisionEngine:
    def __init__(self):
        self.model = None

    def infer(self, frame, confidence):
        if self.model is None:
            if not readiness()['ready']:
                raise RuntimeError('检测环境或模型权重尚未安装。')
            from ultralytics import YOLO
            model = YOLO(str(MODEL_FILE))
            names = model.names
            mapping = names if isinstance(names, dict) else dict(enumerate(names))
            class_ids = {idx: name for idx, name in mapping.items() if name in ('person', 'bicycle', 'motorcycle')}
            if set(class_ids.values()) != {'person', 'bicycle', 'motorcycle'}:
                raise RuntimeError('模型必须包含 person、bicycle 和 motorcycle 类别。')
            self.model, self.class_ids = model, class_ids
        height, width = frame.shape[:2]
        detections = []
        def predict(image, x=0, y=0, tiled=False):
            result = self.model.predict(source=image, classes=list(self.class_ids), conf=confidence,
                                        device=os.getenv('DETECTION_DEVICE', 'cpu'), imgsz=1024,
                                        max_det=1000, verbose=False)[0]
            tile_h, tile_w = image.shape[:2]
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                # Avoid counting fragments cut by internal tile boundaries.
                if tiled and ((x > 0 and x1 < 4) or (y > 0 and y1 < 4)
                              or (x + tile_w < width and x2 > tile_w - 4)
                              or (y + tile_h < height and y2 > tile_h - 4)):
                    continue
                detections.append({'label': self.class_ids[int(box.cls[0])],
                                   'confidence': round(float(box.conf[0]), 4),
                                   'box': [(x1+x)/width, (y1+y)/height, (x2+x)/width, (y2+y)/height]})
        predict(frame)
        if max(height, width) > 1280:
            # Keep original pixels in every tile, including images above 4096px.
            # The accepted image/video pixel limits bound the number of tiles.
            for y in tile_origins(height):
                for x in tile_origins(width):
                    predict(frame[y:y+1024, x:x+1024], x, y, True)
        detections = merge_detections(detections)
        import cv2
        preview = frame.copy()
        colors = {'person': (230,130,40), 'bicycle': (40,180,40), 'motorcycle': (0,150,250)}
        for item in detections:
            item['box'] = [round(value, 5) for value in item['box']]
            x1,y1,x2,y2 = [round(value * (width if index%2==0 else height)) for index,value in enumerate(item['box'])]
            color = colors[item['label']]
            cv2.rectangle(preview, (x1,y1), (x2,y2), color, max(2,round(width/1400)))
            cv2.putText(preview, f"{item['label']} {item['confidence']:.2f}", (x1,max(18,y1-6)),
                        cv2.FONT_HERSHEY_SIMPLEX, max(.45,width/5500), color, 2)
        return detections, preview


def analyze_media(path, kind, engine, confidence, interval_seconds, progress):
    import cv2
    import numpy as np
    if kind == 'image':
        frame = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError('图片无法解码，请使用有效的 JPG、PNG 或 WebP 文件。')
        if frame.shape[0] * frame.shape[1] > 40_000_000:
            raise ValueError('图片超过 4000 万像素，请缩小后重试。')
        detections, annotated = engine.infer(frame, confidence)
        progress(1, 1)
        yield 0.0, detections, annotated
        return
    capture = cv2.VideoCapture(str(path))
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if not capture.isOpened() or not np.isfinite(fps) or fps <= 0 or count <= 0:
            raise ValueError('视频无法解码或缺少有效帧率，请转换为 MP4 后重试。')
        duration = count / fps
        if duration > 120:
            raise ValueError('测试视频最长 120 秒，请截取片段后上传。')
        stride = max(1, round(fps * interval_seconds))
        expected = min(240, int((count - 1) // stride) + 1)
        # Sequential decoding avoids inaccurate seeking for variable/key-frame video.
        index, processed = 0, 0
        while processed < 240:
            ok, frame = capture.read()
            if not ok:
                break
            if index % stride == 0:
                if frame.shape[0] * frame.shape[1] > 16_000_000:
                    raise ValueError('视频分辨率过大，请缩小到 4K 以内。')
                detections, annotated = engine.infer(frame, confidence)
                processed += 1
                progress(processed, expected)
                yield round(index / fps, 3), detections, annotated
            index += 1
    finally:
        capture.release()
