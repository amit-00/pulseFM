from datetime import datetime, timedelta, timezone
import asyncio

from google.cloud.firestore import AsyncClient


STUBBED_VOTE_ID = "stubbed"


async def seed():
    db = AsyncClient(project="pulsefm-484500")
    
    stubbed_song_ref = db.collection("songs").document(STUBBED_VOTE_ID)
    stubbed_song = await stubbed_song_ref.get()
    stubbed_song_data = stubbed_song.to_dict() or {}
    stubbed_duration_ms = stubbed_song_data.get("durationMs")


    if not stubbed_duration_ms:
        raise ValueError("Stubbed song duration is not set")

    station_ref = db.collection("stations").document("main")
    now = datetime.now(timezone.utc)
    result = await station_ref.set({
        "voteId": STUBBED_VOTE_ID,
        "startAt": now,
        "endAt": now + timedelta(milliseconds=stubbed_duration_ms),
        "durationMs": stubbed_duration_ms,
        "next": {
            "voteId": STUBBED_VOTE_ID,
            "duration": stubbed_duration_ms,
        },
    })
    
    if not result:
        raise ValueError("Failed to seed stations/main")

    print("✅ Seeded stations/main")


if __name__ == "__main__":
    asyncio.run(seed())

