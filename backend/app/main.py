from fastapi import FastAPI, APIRouter

from app.api.requests import router as requests_router
from app.api.queue import router as queue_router
from app.api.stream import router as stream_router

app = FastAPI(title="PulseFM Backend", version="1.0.0")

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

