"""Joint multi-angle snapshots; originals and saved annotations are immutable job inputs."""
import json
import logging
from pathlib import Path
from fastapi import APIRouter,Request,HTTPException
from pydantic import BaseModel,Field,model_validator
from .annotations import record
from .qwen_vision import readiness
from .vision_service import utc_now
from .vision_metrics import summarize

router=APIRouter(prefix='/vision',tags=['area-surveys'])

class View(BaseModel):
    media_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    time_seconds:float=Field(0,ge=0,allow_inf_nan=False)

class Survey(BaseModel):
    area_id:str=Field(min_length=1,max_length=80)
    capture_group:str=Field(min_length=1,max_length=100)
    views:list[View]=Field(min_length=1,max_length=6)
    @model_validator(mode='after')
    def unique(self):
        self.area_id=self.area_id.strip();self.capture_group=self.capture_group.strip()
        if not self.area_id or not self.capture_group:raise ValueError('请选择停车区并填写采集批次')
        if len({(v.media_id,v.time_seconds) for v in self.views})!=len(self.views):raise ValueError('不能重复选择同一帧')
        return self

def process(service,job,inputs):
    try:
        import cv2
        import numpy as np
        job.update(status='processing',updated_at=utc_now());service.save(job)
        views=[];preview=None;total_bytes=0
        for entry in inputs:
            meta=entry['media'];source=Path(entry['path'])
            if meta['kind']=='image':
                raw=source.read_bytes();mime={'.png':'image/png','.webp':'image/webp'}.get(meta['extension'],'image/jpeg')
                frame=cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
            else:
                cap=cv2.VideoCapture(str(source))
                try:cap.set(cv2.CAP_PROP_POS_MSEC,entry['time_seconds']*1000);ok,frame=cap.read()
                finally:cap.release()
                if not ok:raise ValueError('选定的视频帧无法解码')
                raw=cv2.imencode('.png',frame)[1].tobytes();mime='image/png'
            if frame is None or frame.shape[0]*frame.shape[1]>40_000_000:raise ValueError('画面无法解码或超过4000万像素')
            total_bytes+=len(raw)
            if total_bytes>24*1024*1024:raise ValueError('本组原始画面合计超过24MB，请拆组或减少视角；系统未缩图')
            if preview is None:preview=frame
            views.append({'raw':raw,'mime':mime,'name':entry['view_name'],'polygons':entry['polygons']})
        counts=service.engine.count_views(views)
        sample={'time_seconds':0,'bicycle':counts['bicycle'],'motorcycle':counts['powered_two_wheeler'],'uncertain_type':counts['uncertain_type'],'two_wheeler':counts['total'],'person':counts['person']}
        result=summarize([sample],job['bicycle_capacity'],job['person_capacity'])
        result.update({k:counts[k] for k in ('legal_count','illegal_count','unknown_location_count')})
        result.update(samples=[sample],usage=counts.get('usage',{}),view_count=len(views),
                      counting_method='joint_multiview_unique_estimate',quality_status='qwen_visual_estimate',
                      classification_note='同批次多角度联合估算；合法、违停与位置不明车辆均已包含在总数中。',
                      warning='上传画面估算，非实时监控。',note=str(counts.get('note',''))[:1000],preview_kind='original_no_boxes')
        (service.storage/job['id']/'preview.jpg').write_bytes(cv2.imencode('.jpg',preview)[1].tobytes())
        job.update(status='completed',progress=100,result=result,updated_at=utc_now(),preview_url=f"/api/vision/jobs/{job['id']}/preview")
        service.save(job)
        if service.store:service.store.record_vision(job)
    except Exception as exc:
        logging.exception('Multi-view survey failed')
        job.update(status='failed',error=str(exc),updated_at=utc_now());service.save(job)
    finally:service.slots.release()

@router.post('/surveys',status_code=202)
def submit(body:Survey,request:Request):
    collection=request.app.state.store.parking(request.app.state.parking)
    area=next((f['properties'] for f in collection['features'] if f['properties']['id']==body.area_id),None)
    if not area:raise HTTPException(404,'停车区不存在')
    inputs=[]
    for view in body.views:
        _,root,row=record(request,view.media_id);meta=json.loads(row['metadata']);payload=json.loads(row['payload'])
        if not isinstance(payload,dict) or (payload.get('area_id') or '').strip()!=body.area_id or payload.get('capture_group','').strip()!=body.capture_group:
            raise HTTPException(422,'所有视角必须保存为同一个地图停车区和同一采集批次')
        # Exact saved frame only: a neighbouring frame must not inherit polygons.
        frames=payload.get('reviewed_frames',[])+[p['time_seconds'] for p in payload.get('polygons',[])]
        matching=[t for t in frames if abs(t-view.time_seconds)<0.00001]
        if not matching:raise HTTPException(422,'请先保存所选帧的可停车范围')
        if view.time_seconds>meta['duration_seconds']:raise HTTPException(422,'视频帧超出时长')
        polygons=[p['points'] for p in payload['polygons'] if abs(p['time_seconds']-view.time_seconds)<0.00001]
        inputs.append({'media':meta,'view_name':payload.get('view_name',''),'time_seconds':view.time_seconds,
                       'polygons':polygons,'path':str(root/view.media_id/('original'+meta['extension']))})
    if not readiness()['ready']:raise HTTPException(503,'请先配置百炼Qwen接口')
    service=request.app.state.vision
    if not service.slots.acquire(False):raise HTTPException(429,'当前识别队列已满')
    job=None
    try:
        job=service.new(f"{area['name']} · {len(inputs)}个视角",'multiview',body.area_id,area['capacity'],50,.2,1)
        job.update(status='queued',capture_group=body.capture_group,views=[{k:v for k,v in e.items() if k!='path'} for e in inputs],engine_revision='qwen-multiview-area-v2')
        service.save(job);service.executor.submit(process,service,job,inputs)
        return {'id':job['id'],'status':'queued'}
    except Exception:
        if job:job.update(status='failed',error='任务提交失败',updated_at=utc_now());service.save(job)
        service.slots.release();raise
