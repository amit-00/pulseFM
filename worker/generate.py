from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class GenerateRequest(BaseModel):
    request_id: str


@app.post("/generate")
def generate(payload: GenerateRequest):
    print(f"Generating for request {payload.request_id}")