from google.cloud import firestore

db = firestore.AsyncClient()

async def get_db():
    return db