import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter

from pulsefm_backend.api.requests import router as requests_router
from pulsefm_backend.api.stream import router as stream_router
from pulsefm_backend.api.tracks import router as tracks_router
from pulsefm_backend.core.station import Station
from pulsefm_backend.services.db import get_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage scheduler and playback engine lifecycle with FastAPI app."""
    # Startup
    db = await get_db()
    station = Station(db)
    await station.start()
    app.state.station = station
    
    yield
    
    # Shutdown
    await station.stop()


app = FastAPI(title="PulseFM Backend", version="1.0.0", lifespan=lifespan)

api_router = APIRouter(prefix="/api")

api_router.include_router(requests_router)
api_router.include_router(stream_router)
api_router.include_router(tracks_router)
app.include_router(api_router)


@app.get("/")
async def root():
    return {"message": "Welcome to PulseFM Backend API"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
