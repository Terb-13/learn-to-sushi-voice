"""
Learn to Sushi - Voice + SMS Backend (Fly.io)
Handles phone calls and text messaging with the same personality as web chat.
"""

import sys
import os


def _ensure_packages_import_path() -> None:
    # In Docker, main.py is /app/main.py — two dirnames yields "/", not /app. Walk up
    # until we find packages/ (also works for local apps/voice-sms layout).
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        if os.path.isdir(os.path.join(d, "packages")):
            if d not in sys.path:
                sys.path.insert(0, d)
            return
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent


_ensure_packages_import_path()

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
)

from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import Response
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Learn to Sushi - Voice & SMS Agent")

# Import route handlers (top-level modules for uvicorn main:app)
from voice_webhook import router as voice_router
from voice_stream import router as stream_router
from sms_webhook import router as sms_router

app.include_router(voice_router, prefix="/voice", tags=["voice"])
app.include_router(stream_router, prefix="/voice-stream", tags=["voice"])
app.include_router(sms_router, prefix="/sms", tags=["sms"])


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "learn-to-sushi-voice-sms",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))