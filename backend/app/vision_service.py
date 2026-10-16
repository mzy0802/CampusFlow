from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import BoundedSemaphore, Lock
from uuid import uuid4
import json
import logging
import re

from .qwen_vision import VisionEngine, analyze_media, config
from .vision_metrics import summarize


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class VisionService:
    def __init__(self, storage):
        self.storage = Path(storage)
        self.storage.mkdir(parents=True, exist_ok=True)
        self.lock = Lock()
        self.slots = BoundedSemaphore(4)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='vision')
        self.engine = VisionEngine()
        self.store = None
        # Previous process cannot finish its in-flight jobs after a restart.
        for path in self.storage.glob('*/job.json'):
            job = json.loads(path.read_text(encoding='utf-8'))
            if job['status'] in ('queued', 'processing', 'uploading'):
                job.update(status='failed', error='后端已重启，请重新提交任务。', updated_at=utc_now())
                self.save(job)
                for original in path.parent.glob('input.*'):
                    original.unlink(missing_ok=True)

    def save(self, job):
        with self.lock:
            directory = self.storage / job['id']
            directory.mkdir(exist_ok=True)
            temp = directory / 'job.tmp'
            temp.write_text(json.dumps(job, ensure_ascii=False), encoding='utf-8')
            temp.replace(directory / 'job.json')

    def get(self, job_id):
        if not re.fullmatch(r'[a-f0-9]{32}', job_id):
            return None
        with self.lock:
            path = self.storage / job_id / 'job.json'
            return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None

    def new(self, filename, kind, area_id, bicycle_capacity, person_capacity, confidence, interval):
        job = {'id': uuid4().hex, 'filename': filename, 'kind': kind, 'area_id': area_id,
               'bicycle_capacity': bicycle_capacity, 'person_capacity': person_capacity,
               'confidence': confidence, 'interval_seconds': interval, 'status': 'uploading',
               'engine_revision': 'qwen-cloud-count-v1',
               'model': config().get('QWEN_VISION_MODEL', 'qwen3-vl-plus'),
               'created_at': utc_now(), 'updated_at': utc_now(), 'progress': 0,
               'result': None, 'error': None, 'preview_url': None}
        self.save(job)
        return job

    def submit(self, job, source):
        job.update(status='queued', updated_at=utc_now())
        self.save(job)
        self.executor.submit(self.process, job, source)

    def process(self, job, source):
        try:
            job.update(status='processing', updated_at=utc_now())
            self.save(job)
            samples = []
            def progress(done, total):
                job.update(progress=min(99, round(done / max(total, 1) * 100)), updated_at=utc_now())
                self.save(job)
            for timestamp, detections, annotated in analyze_media(
                    source, job['kind'], self.engine, job['confidence'], job['interval_seconds'], progress):
                sample = {'time_seconds': timestamp, **detections}
                samples.append(sample)
                # Only the latest annotated sample is retained as a preview.
                import cv2
                ok, encoded = cv2.imencode('.jpg', annotated)
                if not ok:
                    raise ValueError('无法生成识别预览。')
                directory = self.storage / job['id']
                preview = directory / 'preview.tmp'
                preview.write_bytes(encoded.tobytes())
                preview.replace(directory / 'preview.jpg')
            result = summarize(samples, job['bicycle_capacity'], job['person_capacity'])
            result.update(quality_status='unvalidated_qwen_visual_count', classification_note='Qwen 视觉估算：自行车、电动两轮车候选及类型不确定车辆；总数包含类型不确定车辆。', warning='云端计数未人工核验，可能漏计或重复计数；低估算占用不代表空闲。', preview_kind='original_no_boxes')
            result['samples'] = samples
            job.update(status='completed', progress=100, result=result, updated_at=utc_now(),
                       preview_url=f"/api/vision/jobs/{job['id']}/preview")
            self.save(job)
            if self.store: self.store.record_vision(job)
        except Exception as exc:
            logging.exception('Vision job %s failed', job['id'])
            job.update(status='failed', error=str(exc), updated_at=utc_now())
            self.save(job)
        finally:
            source.unlink(missing_ok=True)
            self.slots.release()

    def observations(self):
        by_area = {}
        for path in self.storage.glob('*/job.json'):
            job = self.get(path.parent.name)
            if job and job['status'] == 'completed' and job['area_id']:
                old = by_area.get(job['area_id'])
                if old is None or job['created_at'] > old['created_at']:
                    by_area[job['area_id']] = job
        return [{'area_id': job['area_id'], 'job_id': job['id'], 'created_at': job['created_at'],
                 'updated_at': job['updated_at'], 'source': 'upload_test',
                 'bicycle': job['result']['bicycle']['latest'],
                 'motorcycle': job['result'].get('motorcycle', {}).get('latest'),
                 'two_wheeler': job['result'].get('two_wheeler', {}).get('latest'),
                 'engine_revision': job.get('engine_revision', 'legacy-bicycle-only'),
                 'person': job['result']['person']['latest']} for job in by_area.values()]

    def close(self):
        self.executor.shutdown(wait=True)
