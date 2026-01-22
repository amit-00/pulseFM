from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter

from app.api.requests import router as requests_router
from app.api.queue import router as queue_router
from app.api.stream import router as stream_router
from app.core.scheduler import get_scheduler
from app.core.playback import get_playback_engine
from app.core.broadcaster import StreamBroadcaster
from app.services.db import get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage scheduler and playback engine lifecycle with FastAPI app."""
    # Startup
    db = await get_db()
    scheduler = get_scheduler(db)
    await scheduler.start()
    
    # Create and start broadcaster
    broadcaster = StreamBroadcaster()
    await broadcaster.start()
    
    # Store broadcaster in app state for endpoint access
    app.state.broadcaster = broadcaster
    
    # Start playback engine with broadcaster
    playback_engine = get_playback_engine(scheduler, broadcaster)
    await playback_engine.start()
    
    yield
    
    # Shutdown
    await playback_engine.stop()
    await broadcaster.stop()
    await scheduler.stop()


app = FastAPI(title="PulseFM Backend", version="1.0.0", lifespan=lifespan)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(requests_router)
api_router.include_router(queue_router)
api_router.include_router(stream_router)
app.include_router(api_router)


@app.get("/")
async def root():
    return {"message": "Welcome to PulseFM Backend API"}


@app.get("/health")
async def health():
    return {"status": "healthy"}

