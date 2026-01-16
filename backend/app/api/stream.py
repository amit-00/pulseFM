from fastapi import APIRouter

router = APIRouter(prefix="/stream", tags=["stream"])

@router.get("/")
async def get_stream():
    return {"message": "Hello, World!"}