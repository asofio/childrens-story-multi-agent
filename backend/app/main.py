"""
main.py — FastAPI application entry point.

Endpoints:
  GET  /api/health              — health check
  POST /api/generate-story      — runs the story workflow; streams SSE progress events
"""

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from .config import settings
from .models import StoryRequest
from .story_generator import StoryGenerator
from .tts import TTSService, TTSRequest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Children's Story Multi-Agent API",
    description=(
        "Multi-agent orchestration for generating illustrated children's stories "
        "using Microsoft Agent Framework."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin, "http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Service instances ────────────────────────────────────────────────────────

_story_generator = StoryGenerator()

# ─── Health check ─────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "service": "children-story-multi-agent"}


# ─── Story generation (SSE) ───────────────────────────────────────────────────


@app.post("/api/generate-story")
async def generate_story(request: StoryRequest) -> EventSourceResponse:
    """Accepts story parameters and streams back SSE events as the multi-agent
    workflow progresses.  The final event (type: 'complete') contains the
    full illustrated StoryResponse.
    """
    return _story_generator.event_source_response(request)


# ─── Text-to-Speech (TTS) ─────────────────────────────────────────────────────

_tts = TTSService()

@app.post("/api/tts")
async def text_to_speech(req: TTSRequest):
    """Synthesize speech and stream audio/mpeg chunks to the client."""
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Text is required.")
    _tts.validate_config()
    return _tts.streaming_response(req.text.strip())