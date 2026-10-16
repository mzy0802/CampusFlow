from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from .qwen_vision import readiness
from .vision_service import utc_now

router = APIRouter(prefix='/vision', tags=['vision'])
MAX_BYTES = 100 * 1024 * 1024
EXTENSIONS = {'.jpg': 'image', '.jpeg': 'image', '.png': 'image', '.webp': 'image',
              '.mp4': 'video', '.mov': 'video', '.avi': 'video', '.webm': 'video'}


@router.get('/health')
def health():
    return {**readiness(), 'max_upload_mb': 100, 'max_video_seconds': 120,
            'concurrency': 1, 'max_pending_jobs': 4}


@router.post('/jobs', status_code=202)
async def upload(request: Request, filename: str = Query(min_length=1, max_length=200),
                 area_id: str | None = None,
                 bicycle_capacity: int = Query(100, ge=1, le=100000),
                 person_capacity: int = Query(50, ge=1, le=100000),
                 confidence: float = Query(0.2, ge=0.05, le=0.95),
                 interval_seconds: float = Query(1.0, ge=0.5, le=10)):
    """Raw file body, not multipart: stream to disk with a hard byte limit."""
    suffix = Path(filename).suffix.lower()
    if suffix not in EXTENSIONS:
        raise HTTPException(415, '支持 JPG、PNG、WebP、MP4、MOV、AVI、WebM。')
    if area_id and area_id not in {f['properties']['id'] for f in request.app.state.parking['features']}:
        raise HTTPException(404, '停车区域不存在。')
    if area_id and hasattr(request.app.state, 'store'):
        collection=request.app.state.store.parking(request.app.state.parking)
        bicycle_capacity=next(f['properties']['capacity'] for f in collection['features'] if f['properties']['id']==area_id)
    if not readiness()['ready']:
        raise HTTPException(503, detail={'code': 'MODEL_NOT_READY', 'message': readiness()['message']})
    service = request.app.state.vision
    if not service.slots.acquire(blocking=False):
        raise HTTPException(429, '当前队列已满，请稍后重试。')
    job = None
    path = None
    try:
        # Untrusted filename is display-only; storage paths use generated UUIDs.
        job = service.new(filename, EXTENSIONS[suffix], area_id, bicycle_capacity,
                          person_capacity, confidence, interval_seconds)
        path = service.storage / job['id'] / f'input{suffix}'
        size = 0
        with path.open('wb') as target:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, '文件超过 100 MB。')
                target.write(chunk)
        if size == 0:
            raise HTTPException(400, '文件为空。')
        service.submit(job, path)
        return {'id': job['id'], 'status': 'queued'}
    except BaseException:
        if path:
            path.unlink(missing_ok=True)
        if job:
            job.update(status='failed', error='上传失败或被中断。', updated_at=utc_now())
            service.save(job)
        service.slots.release()
        raise


@router.get('/observations')
def observations(request: Request):
    items=request.app.state.vision.observations()
    capacities={f['properties']['id']:f['properties']['capacity'] for f in request.app.state.store.parking(request.app.state.parking)['features']}
    from .vision_metrics import congestion
    for item in items:
        if item['area_id'] in capacities:
            for key in ('bicycle','motorcycle','two_wheeler'):
                if item.get(key): item[key]=congestion(item[key]['count'],capacities[item['area_id']])
    return {'items': items,
            'source': 'upload_test', 'is_live': False}


@router.get('/jobs/{job_id}')
def job_status(job_id: str, request: Request):
    job = request.app.state.vision.get(job_id)
    if job is None:
        raise HTTPException(404, '识别任务不存在。')
    return job


@router.get('/jobs/{job_id}/preview')
def preview(job_id: str, request: Request):
    job = request.app.state.vision.get(job_id)
    if not job or job['status'] != 'completed':
        raise HTTPException(404, '识别预览尚未生成。')
    return FileResponse(request.app.state.vision.storage / job_id / 'preview.jpg', media_type='image/jpeg')
