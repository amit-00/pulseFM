from typing import Optional, Tuple
import re

from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import Response
from google.cloud.exceptions import GoogleCloudError

from app.services.storage import get_storage_blob


router = APIRouter(prefix="/tracks", tags=["tracks"])


def parse_range_header(range_header: Optional[str], file_size: int) -> Optional[Tuple[int, int]]:
    if not range_header:
        return None
    
    match = re.match(r'bytes=(\d+)-(\d*)', range_header)
    if not match:
        return None
    
    start = int(match.group(1))
    end_str = match.group(2)
    
    if end_str:
        end = int(end_str)
    else:
        end = file_size - 1
    
    if start < 0 or end >= file_size or start > end:
        return None
    
    return (start, end)


@router.get("/{request_id}")
async def get_song(request_id: str, request: Request, range_header: Optional[str] = Header(None, alias="Range")):
    db = request.app.state.db
    doc_ref = db.collection("requests").document(document_id=request_id)
    doc = await doc_ref.get()
    
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Request not found")

    audio_url = doc.to_dict().get("audio_url")
    if not audio_url:
        raise HTTPException(status_code=404, detail="Audio URL not found")

    try:
        blob = get_storage_blob(audio_url)
        
        if not blob.exists():
            raise HTTPException(status_code=404, detail="Audio file not found in storage")
        
        blob.reload()
        file_size = blob.size
        
        content_type = blob.content_type or "audio/mpeg"

        if not range_header:
            chunk = blob.download_as_bytes()
            
            return Response(
                content=chunk,
                status_code=200,
                media_type=content_type,
                headers={
                    "Content-Length": str(file_size),
                    "Accept-Ranges": "bytes",
                }
            )
        

        range_tuple = parse_range_header(range_header, file_size)
        if not range_tuple:
            raise HTTPException(
                status_code=416,
                detail=f"Range not satisfiable. File size: {file_size}",
                headers={
                    "Content-Range": f"bytes */{file_size}",
                    "Accept-Ranges": "bytes",
                }
            )

        start, end = range_tuple

        chunk = blob.download_as_bytes(start=start, end=end)
        content_length = end - start + 1
        
        return Response(
            content=chunk,
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(content_length),
                "Accept-Ranges": "bytes",
            }
        )
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except GoogleCloudError as e:
        raise HTTPException(status_code=500, detail=f"Storage error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")