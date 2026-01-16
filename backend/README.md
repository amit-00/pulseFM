# PulseFM Backend

A FastAPI backend application.

## Setup

1. Activate the virtual environment:

   ```bash
   source venv/bin/activate  # On macOS/Linux
   # or
   venv\Scripts\activate  # On Windows
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:
   ```bash
   uvicorn main:app --reload
   ```

The API will be available at:

- http://localhost:8000
- API documentation: http://localhost:8000/docs
- Alternative docs: http://localhost:8000/redoc

## Endpoints

- `GET /` - Root endpoint
- `GET /health` - Health check endpoint
