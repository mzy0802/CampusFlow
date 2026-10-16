from contextlib import asynccontextmanager
from fastapi import FastAPI
from .data import load_parking, DEFAULT_FILE
from .traffic_store import Store
from .network_api import router as network_router
from .parking import router as parking_router
from .mobility import router as mobility_router
from .vision import router as vision_router
from .vision_service import VisionService
from pathlib import Path
import os


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = Store()
    seed = os.getenv('CAMPUS_NETWORK_FILE', str(Path(os.getenv('PARKING_DATA_FILE', str(DEFAULT_FILE))).parent / 'network.osm.json'))
    app.state.store.seed_campus(seed)
    app.state.parking = app.state.store.parking(load_parking())
    app.state.vision = VisionService(os.getenv('DETECTION_STORAGE', str(Path(__file__).resolve().parents[1] / 'storage')))
    app.state.vision.store = app.state.store
    for path in app.state.vision.storage.glob("*/job.json"):
        job = app.state.vision.get(path.parent.name)
        if job and job["status"] == "completed": app.state.store.record_vision(job)
    yield
    app.state.vision.close()


app = FastAPI(title='修远楼周边智能停车与出行 Demo', version='0.2.0', lifespan=lifespan)
app.include_router(network_router, prefix='/api')
app.include_router(parking_router, prefix='/api')
app.include_router(mobility_router, prefix='/api')
app.include_router(vision_router, prefix='/api')


@app.get('/api/health')
def health():
    return {'status': 'ok', 'parking_mode': 'simulated'}
