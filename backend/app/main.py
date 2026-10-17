from contextlib import asynccontextmanager
from fastapi import FastAPI
from .data import load_parking, DEFAULT_FILE
from .traffic_store import Store
from .network_api import router as network_router
from .parking import router as parking_router
from .mobility import router as mobility_router
from .vision import router as vision_router
from .vision_service import VisionService
from .annotations import router as annotation_router
from .navigation import router as navigation_router
from .parking_editor import router as parking_editor_router, merge_import_batch, replace_import_batch
from .transit import router as transit_router
from .area_surveys import router as survey_router
from .parking_identity import migrate_hongyuan
from .simulation import router as simulation_router
from .road_corrections import correct_xiuyuan_roundabout, connect_owner_cycleway
from pathlib import Path
import os


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = Store()
    seed = os.getenv('CAMPUS_NETWORK_FILE', str(Path(os.getenv('PARKING_DATA_FILE', str(DEFAULT_FILE))).parent / 'network.osm.json'))
    app.state.store.seed_campus(seed)
    if os.getenv('CAMPUS_ACCEPT_ROADS', '1') == '1': app.state.store.accept_current_roads()
    correct_xiuyuan_roundabout(app.state.store)
    connect_owner_cycleway(app.state.store)
    default_parking=load_parking()
    storage = os.getenv('DETECTION_STORAGE', str(Path(__file__).resolve().parents[1] / 'storage'))
    migrate_hongyuan(app.state.store, default_parking, storage)
    for batch in ('mingyuan-20261016','hongyuan-20261016','canteen-20261017'):
        parking=merge_import_batch(app.state.store,default_parking,batch)
    parking=replace_import_batch(app.state.store,default_parking,'xiuyuan-v2-20261016')
    app.state.parking = app.state.store.parking(parking['collection'])
    app.state.vision = VisionService(storage)
    app.state.vision.store = app.state.store
    for path in app.state.vision.storage.glob("*/job.json"):
        job = app.state.vision.get(path.parent.name)
        if job and job["status"] == "completed": app.state.store.record_vision(job)
    yield
    app.state.vision.close()


app = FastAPI(title='CampusFlow 校园停车与出行', version='0.2.0', lifespan=lifespan)
app.include_router(simulation_router, prefix='/api')
app.include_router(network_router, prefix='/api')
app.include_router(annotation_router, prefix='/api')
app.include_router(navigation_router, prefix='/api')
app.include_router(parking_editor_router, prefix='/api')
app.include_router(parking_router, prefix='/api')
app.include_router(mobility_router, prefix='/api')
app.include_router(vision_router, prefix='/api')
app.include_router(transit_router, prefix='/api')
app.include_router(survey_router, prefix='/api')


@app.get('/api/health')
def health():
    return {'status': 'ok', 'parking_mode': 'simulated'}
