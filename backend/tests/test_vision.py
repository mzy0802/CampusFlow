"""Service/HTTP-handler tests use explicit fake inference; never a product fallback."""
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest
from fastapi import HTTPException
from app.vision_metrics import congestion, summarize
from app.vision_service import VisionService
from app import vision, vision_service


@pytest.mark.parametrize('count,capacity,percent,level', [
    (0, 100, 0, 'clear'), (50, 100, 50, 'moderate'), (80, 100, 80, 'crowded'),
    (100, 100, 100, 'crowded'), (120, 100, 120, 'overloaded'), (400, 100, 400, 'overloaded')])
def test_unclamped_congestion(count, capacity, percent, level):
    assert congestion(count, capacity) == {'count': count, 'capacity': capacity, 'percent': percent, 'level': level}


def test_video_counts_are_not_added_and_peak_is_separate():
    result = summarize([{'bicycle': 120, 'person': 5}, {'bicycle': 80, 'person': 10}], 100, 5)
    assert result['bicycle']['latest']['count'] == 80
    assert result['bicycle']['peak']['percent'] == 120
    assert result['person']['latest']['percent'] == 200
    assert result['person']['peak']['count'] == 10
    with pytest.raises(ValueError): summarize([], 100, 50)
    with pytest.raises(ValueError): congestion(2, 0)


def test_processing_persistence_and_area_observation(tmp_path, monkeypatch):
    def fake_media(*args):
        args[-1](1, 1)
        yield 0, {'bicycle': 120, 'motorcycle': 0, 'uncertain_type': 0, 'two_wheeler': 120, 'person': 6, 'detections': []}, object()
    monkeypatch.setattr(vision_service, 'analyze_media', fake_media)
    monkeypatch.setitem(sys.modules, 'cv2', SimpleNamespace(imencode=lambda *args: (True, SimpleNamespace(tobytes=lambda: b'test-preview'))))
    service = VisionService(tmp_path)
    try:
        assert service.slots.acquire(False)
        job = service.new('test.jpg', 'image', 'X4001', 100, 5, .35, 1)
        source = tmp_path / job['id'] / 'input.jpg'; source.write_bytes(b'test-input')
        service.process(job, source)
        saved = service.get(job['id'])
        assert saved['status'] == 'completed'
        assert saved['result']['bicycle']['latest']['percent'] == 120
        assert saved['result']['person']['latest']['percent'] == 120
        assert not source.exists()
        assert service.get('../../secret') is None
        assert service.observations()[0]['bicycle']['percent'] == 120
        assert (tmp_path / job['id'] / 'preview.jpg').read_bytes() == b'test-preview'
    finally: service.close()
    restarted = VisionService(tmp_path)
    assert restarted.get(job['id'])['status'] == 'completed'
    restarted.close()


def test_decode_failure_has_no_false_result_and_releases_slot(tmp_path, monkeypatch):
    def broken(*args): raise ValueError('Bad media')
    monkeypatch.setattr(vision_service, 'analyze_media', broken)
    service = VisionService(tmp_path)
    try:
        service.slots.acquire(False)
        job = service.new('bad.mp4', 'video', None, 100, 50, .35, 1)
        source = tmp_path / job['id'] / 'input.mp4'; source.write_bytes(b'broken')
        service.process(job, source)
        saved = service.get(job['id'])
        assert saved['status'] == 'failed' and saved['result'] is None
        assert not source.exists()
        assert all(service.slots.acquire(False) for _ in range(4))
        assert not service.slots.acquire(False)
    finally: service.close()


def test_restart_marks_abandoned_job_failed(tmp_path):
    service = VisionService(tmp_path)
    job = service.new('image.jpg', 'image', None, 100, 50, .35, 1)
    source = tmp_path / job['id'] / 'input.jpg'
    source.write_bytes(b'interrupted-upload')
    service.close()
    restarted = VisionService(tmp_path)
    assert restarted.get(job['id'])['status'] == 'failed'
    assert not source.exists()
    restarted.close()


def immediate(coroutine):
    """The handler's fake stream is synchronous; needs no sockets/event loop."""
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError('Unexpected asynchronous I/O in fake request')


class FakeRequest:
    def __init__(self, service, chunks):
        self.app = SimpleNamespace(state=SimpleNamespace(vision=service, parking={
            'features': [{'properties': {'id': 'X4001'}}]}))
        self.chunks = chunks
    async def stream(self):
        for chunk in self.chunks: yield chunk


def call_upload(request, filename='sample.jpg', area_id='X4001'):
    return immediate(vision.upload(request, filename, area_id, 100, 50, .35, 1))


def test_upload_validation_and_queue(tmp_path, monkeypatch):
    service = VisionService(tmp_path)
    tasks = []
    monkeypatch.setattr(service.executor, 'submit', lambda *args: tasks.append(args))
    request = FakeRequest(service, [b'file-bytes'])
    try:
        monkeypatch.setattr(vision, 'readiness', lambda: {'ready': False, 'message': 'model missing'})
        with pytest.raises(HTTPException) as exc: call_upload(request)
        assert exc.value.status_code == 503
        monkeypatch.setattr(vision, 'readiness', lambda: {'ready': True})
        with pytest.raises(HTTPException) as exc: call_upload(request, 'payload.exe')
        assert exc.value.status_code == 415
        with pytest.raises(HTTPException) as exc: call_upload(request, area_id='missing')
        assert exc.value.status_code == 404
        job = call_upload(request, '../../sample.jpg')
        assert service.get(job['id'])['status'] == 'queued'
        assert (tmp_path / job['id'] / 'input.jpg').read_bytes() == b'file-bytes'
        for _ in range(3): call_upload(request)
        with pytest.raises(HTTPException) as exc: call_upload(request)
        assert exc.value.status_code == 429
        assert len(tasks) == 4
    finally: service.close()


@pytest.mark.parametrize('chunks,status', [([], 400), ([b'0123456789'], 413)])
def test_upload_empty_and_oversize_cleanup(tmp_path, monkeypatch, chunks, status):
    monkeypatch.setattr(vision, 'readiness', lambda: {'ready': True})
    monkeypatch.setattr(vision, 'MAX_BYTES', 4)
    service = VisionService(tmp_path)
    try:
        with pytest.raises(HTTPException) as exc: call_upload(FakeRequest(service, chunks))
        assert exc.value.status_code == status
        assert not list(tmp_path.glob('*/input.*'))
        assert all(service.slots.acquire(False) for _ in range(4))
    finally: service.close()
