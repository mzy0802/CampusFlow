"""Local manual frame annotations. Uploading here never invokes a model API."""
import json
import math
import uuid
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from .vision_service import utc_now

router = APIRouter(prefix='/annotations', tags=['manual-annotations'])
EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.mp4', '.mov', '.webm', '.avi'}

class Polygon(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    label: Literal['allowed']
    note: str = Field('', max_length=500)
    time_seconds: float = Field(0, ge=0, allow_inf_nan=False)
    points: list[tuple[float, float]] = Field(min_length=3, max_length=200)

    @model_validator(mode='after')
    def geometry(self):
        p = self.points
        if any(not math.isfinite(v) or not 0 <= v <= 1 for xy in p for v in xy):
            raise ValueError('坐标必须是 0～1 的有限值')
        if len(set(p)) != len(p): raise ValueError('顶点不能重复')
        if abs(sum(p[i][0]*p[(i+1)%len(p)][1]-p[(i+1)%len(p)][0]*p[i][1] for i in range(len(p)))) < 1e-8:
            raise ValueError('区域面积不能为零')
        def orient(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        def on(a,b,c): return min(a[0],b[0])<=c[0]<=max(a[0],b[0]) and min(a[1],b[1])<=c[1]<=max(a[1],b[1])
        for i in range(len(p)):
            a,b=p[i],p[(i+1)%len(p)]
            for j in range(i+1,len(p)):
                if j==i+1 or (i==0 and j==len(p)-1): continue
                c,d=p[j],p[(j+1)%len(p)]
                o1,o2,o3,o4=orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b)
                if (o1*o2<0 and o3*o4<0) or any(abs(o)<1e-12 and on(x,y,z) for o,x,y,z in [(o1,a,b,c),(o2,a,b,d),(o3,c,d,a),(o4,c,d,b)]):
                    raise ValueError('区域边界不能自相交')
        return self

class AnnotationSet(BaseModel):
    revision: int = Field(ge=0)
    reviewed_frames: list[float] = Field(default_factory=list, max_length=1000)
    polygons: list[Polygon] = Field(default_factory=list, max_length=1000)
    @model_validator(mode='after')
    def unique(self):
        if any(not math.isfinite(t) or t<0 for t in self.reviewed_frames): raise ValueError('帧时间不合法')
        if len({p.id for p in self.polygons}) != len(self.polygons): raise ValueError('标注 ID 重复')
        return self

def storage(request):
    store=request.app.state.store
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS annotation_media(id TEXT PRIMARY KEY, metadata TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL)')
    root=request.app.state.vision.storage/'annotations'
    root.mkdir(parents=True,exist_ok=True)
    return store,root

def record(request,mid):
    if len(mid)!=32 or any(c not in '0123456789abcdef' for c in mid): raise HTTPException(404,'素材不存在')
    store,root=storage(request)
    with store.connect() as db: row=db.execute('SELECT * FROM annotation_media WHERE id=?',(mid,)).fetchone()
    if not row: raise HTTPException(404,'素材不存在')
    return store,root,dict(row)

@router.get('/media')
def listing(request:Request):
    store,_=storage(request)
    with store.connect() as db: rows=db.execute('SELECT metadata,revision FROM annotation_media ORDER BY rowid DESC').fetchall()
    return {'items':[{**json.loads(r['metadata']),'revision':r['revision']} for r in rows]}

@router.post('/media',status_code=201)
async def upload(request:Request,filename:str=Query(min_length=1,max_length=200)):
    ext=Path(filename).suffix.lower()
    if ext not in EXTENSIONS: raise HTTPException(415,'不支持此文件类型')
    store,root=storage(request); mid=uuid.uuid4().hex
    folder=root/mid;folder.mkdir();path=folder/('original'+ext)
    try:
        size=0
        with path.open('wb') as out:
            async for chunk in request.stream():
                size+=len(chunk)
                if size>100*1024*1024: raise HTTPException(413,'单个素材最大 100 MB，请截取视频片段')
                out.write(chunk)
        if not size: raise HTTPException(400,'文件为空')
        import cv2
        import numpy as np
        kind='image' if ext in {'.jpg','.jpeg','.png','.webp'} else 'video'
        duration=0
        if kind=='image':
            frame=cv2.imdecode(np.fromfile(path,dtype=np.uint8),cv2.IMREAD_COLOR)
            if frame is None: raise HTTPException(422,'图片无法解码')
            height,width=frame.shape[:2]
            if width*height>40_000_000: raise HTTPException(422,'图片最多 4000 万像素')
            (folder/'preview.png').write_bytes(cv2.imencode('.png',frame)[1].tobytes())
        else:
            cap=cv2.VideoCapture(str(path))
            try:
                width,height=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps=cap.get(cv2.CAP_PROP_FPS);frames=cap.get(cv2.CAP_PROP_FRAME_COUNT)
                if not cap.isOpened() or fps<=0 or frames<=0: raise HTTPException(422,'视频无法解码')
                duration=frames/fps
                if not math.isfinite(duration) or duration>1800: raise HTTPException(422,'视频最长 30 分钟')
            finally: cap.release()
        if width<=0 or height<=0: raise HTTPException(422,'无有效画面尺寸')
        meta={'id':mid,'filename':filename,'kind':kind,'width':width,'height':height,'duration_seconds':duration,'created_at':utc_now(),'extension':ext,'url':f'/api/annotations/media/{mid}/content','source':'manual_annotation'}
        with store.connect() as db: db.execute('INSERT INTO annotation_media VALUES(?,?,0,?)',(mid,json.dumps(meta,ensure_ascii=False),'[]'))
        return meta
    except BaseException:
        for file in folder.iterdir(): file.unlink()
        folder.rmdir()
        raise

@router.get('/media/{mid}/content')
def content(mid:str,request:Request):
    _,root,row=record(request,mid);meta=json.loads(row['metadata'])
    path=root/mid/('preview.png' if meta['kind']=='image' else 'original'+meta['extension'])
    return FileResponse(path)

@router.get('/media/{mid}')
def get(mid:str,request:Request):
    _,_,row=record(request,mid)
    payload=json.loads(row['payload'])
    if isinstance(payload,list): payload={'polygons':payload,'reviewed_frames':[]}
    return {'media':json.loads(row['metadata']),'revision':row['revision'],**payload,'coordinate_system':'normalized_image_xy','scope':'single_frame','source':'manual_annotation','outside_policy':'forbidden_in_reviewed_frame','unreviewed_policy':'unknown'}

@router.put('/media/{mid}')
def save(mid:str,body:AnnotationSet,request:Request):
    store,_,row=record(request,mid);meta=json.loads(row['metadata'])
    if any(t>meta['duration_seconds'] for t in body.reviewed_frames): raise HTTPException(422,'审核帧时间超出素材范围')
    if any(p.time_seconds>meta['duration_seconds'] or (meta['kind']=='image' and p.time_seconds!=0) for p in body.polygons): raise HTTPException(422,'标注时间超出素材范围')
    with store.connect() as db:
        changed=db.execute('UPDATE annotation_media SET revision=revision+1,payload=? WHERE id=? AND revision=?',(json.dumps({'polygons':[p.model_dump() for p in body.polygons],'reviewed_frames':sorted(set(body.reviewed_frames+[p.time_seconds for p in body.polygons]))},ensure_ascii=False),mid,body.revision)).rowcount
        if not changed: raise HTTPException(409,'其他页面已修改，请导出草稿后重新加载')
    return get(mid,request)
