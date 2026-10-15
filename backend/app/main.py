from contextlib import asynccontextmanager
from fastapi import FastAPI
from .data import load_parking
from .parking import router as parking_router
from .mobility import router as mobility_router
from .vision import router as vision_router
from .vision_service import VisionService
from pathlib import Path
import os


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.parking = load_parking()
    app.state.vision = VisionService(os.getenv('DETECTION_STORAGE', str(Path(__file__).resolve().parents[1] / 'storage')))
    yield
    app.state.vision.close()


app = FastAPI(title='修远楼周边智能停车与出行 Demo', version='0.2.0', lifespan=lifespan)
app.include_router(parking_router, prefix='/api')
app.include_router(mobility_router, prefix='/api')
app.include_router(vision_router, prefix='/api')


@app.get('/api/health')
def health():
    return {'status': 'ok', 'parking_mode': 'simulated'}
