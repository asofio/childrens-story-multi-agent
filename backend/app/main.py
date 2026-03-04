"""
main.py — FastAPI application entry point.

Endpoints:
  GET  /api/health              — health check
  POST /api/generate-story      — runs the story workflow; streams SSE progress events
"""

import io
import json
import logging
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from .config import settings
from .models import StoryRequest, StoryResponse
from .workflow import build_story_workflow
from .events import ProgressDetailEvent

try:
    from agent_framework import (
        ExecutorInvokedEvent,
        ExecutorCompletedEvent,
        WorkflowOutputEvent,
    )
    try:
        from agent_framework import WorkflowFailedEvent
    except ImportError:
        WorkflowFailedEvent = None  # type: ignore[misc,assignment]
except ImportError as _ie:
    raise RuntimeError(f"agent_framework event classes unavailable: {_ie}") from _ie

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Executor display metadata ────────────────────────────────────────────────

_EXECUTOR_LABELS: dict[str, str] = {
    "orchestrator":       "Orchestrator",
    "story_architect":    "Story Architect",
    "art_director":       "Art Director",
    "story_reviewer":     "Story Reviewer",
    "decision":           "Decision",
    "approval_gateway":   "Approval Gateway",
    "look_and_find":      "Look & Find",
    "character_glossary": "Character Glossary",
    "final_assembly":     "Final Assembly",
}

_EXECUTOR_MESSAGES: dict[str, str] = {
    "orchestrator":       "Creating the story outline...",
    "story_architect":    "Writing the story pages...",
    "art_director":       "Generating illustrations for each page...",
    "story_reviewer":     "Reviewing story for quality & consistency...",
    "decision":           "Making final decisions...",
    "approval_gateway":   "Routing approved story...",
    "look_and_find":      "Creating the Look & Find activity page...",
    "character_glossary": "Writing the Character Glossary...",
    "final_assembly":     "Assembling the final story...",
}

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

# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "service": "children-story-multi-agent"}


# ─── Story generation (SSE) ───────────────────────────────────────────────────

def _sse_event(event_type: str, data: dict) -> dict:
    """Format a Server-Sent Event payload."""
    return {"event": event_type, "data": json.dumps(data)}


async def _story_event_generator(
    request: StoryRequest,
) -> AsyncGenerator[dict, None]:
    """
    Run the story workflow and translate WorkflowEvents into SSE messages.

    SSE event types emitted to the frontend:
      - "progress"   — executor started / completed
      - "detail"     — granular sub-step detail (prompt, response, page content, image progress)
      - "revision"   — a revision loop has been triggered
      - "complete"   — final StoryResponse (story is done)
      - "error"      — workflow failed
    """
    try:
        revision_count = 0
        active_executor: str | None = None

        # Build a fresh workflow for this request — the graph topology depends on
        # which bonus agents the user requested.
        workflow = build_story_workflow(
            include_look_and_find=request.include_look_and_find,
            include_character_glossary=request.include_character_glossary,
        )

        async for event in workflow.run_stream(request):

            if isinstance(event, ExecutorInvokedEvent):
                executor_id: str = event.executor_id or ""
                active_executor = executor_id
                label = _EXECUTOR_LABELS.get(executor_id, executor_id)
                message = _EXECUTOR_MESSAGES.get(executor_id, f"{label} is working...")

                # Detect revision loops: orchestrator re-invoked after the first pass.
                # We can't easily read revision_count from the event, so we track locally.
                is_revision = executor_id == "orchestrator" and revision_count > 0

                if is_revision:
                    yield _sse_event(
                        "revision",
                        {
                            "executor_id": executor_id,
                            "revision_round": revision_count,
                            "message": f"Story Reviewer requested changes — starting revision {revision_count}...",
                        },
                    )
                else:
                    yield _sse_event(
                        "progress",
                        {
                            "executor_id": executor_id,
                            "status": "started",
                            "label": label,
                            "message": message,
                        },
                    )

            elif isinstance(event, ExecutorCompletedEvent):
                executor_id = event.executor_id or (active_executor or "")
                label = _EXECUTOR_LABELS.get(executor_id, executor_id)
                if executor_id == "decision":
                    # Increment our local revision counter each time decision completes
                    # without yielding output (proxy: orchestrator will fire again).
                    revision_count += 1
                yield _sse_event(
                    "progress",
                    {
                        "executor_id": executor_id,
                        "status": "completed",
                        "label": label,
                        "message": f"{label} finished.",
                    },
                )

            elif isinstance(event, ProgressDetailEvent):
                yield _sse_event("detail", {
                    "executor_id": event.executor_id,
                    "detail_type": event.detail_type,
                    "data": event.detail_data,
                })

            elif isinstance(event, WorkflowOutputEvent):
                output_data = event.data
                if output_data is not None:
                    if isinstance(output_data, StoryResponse):
                        story_dict = output_data.model_dump()
                    elif hasattr(output_data, "model_dump"):
                        story_dict = output_data.model_dump()
                    elif isinstance(output_data, dict):
                        story_dict = output_data
                    else:
                        story_dict = json.loads(str(output_data))

                    # Reset revision counter for clean final event
                    revision_count = 0
                    yield _sse_event("complete", {"story": story_dict})

            elif WorkflowFailedEvent is not None and isinstance(event, WorkflowFailedEvent):
                details = getattr(event, "details", None)
                if details is not None:
                    error_msg = getattr(details, "message", None) or str(details)
                    executor = getattr(details, "executor_id", None)
                    tb = getattr(details, "traceback", None)
                    logger.error(
                        "[Workflow] Workflow failed in executor=%s: %s\n%s",
                        executor, error_msg, tb or "",
                    )
                else:
                    error_msg = "The story workflow encountered an error."
                    logger.error("[Workflow] Workflow failed (no details)")
                yield _sse_event("error", {"message": error_msg or "The story workflow encountered an error."})
                return

    except Exception as exc:
        logger.exception("[Workflow] Unhandled error in story event generator")
        yield _sse_event("error", {"message": f"Internal error: {exc}"})


# ─── Text-to-Speech (TTS) ─────────────────────────────────────────────────────

try:
    import azure.cognitiveservices.speech as speechsdk
    _SPEECH_SDK_AVAILABLE = True
except ImportError:
    _SPEECH_SDK_AVAILABLE = False

from azure.identity import DefaultAzureCredential
_credential = DefaultAzureCredential()

SPEECH_REGION      = settings.azure_speech_region
SPEECH_RESOURCE_ID = settings.azure_speech_resource_id
SPEECH_ENDPOINT    = settings.azure_speech_endpoint

TTS_VOICE = "en-US-Ava:DragonHDLatestNeural"


def _get_auth_token() -> str:
    """
    Fetch an AAD access token and format it for the Speech SDK.
    The SDK expects:  aad#<resource_id>#<token>
    """
    token = _credential.get_token("https://cognitiveservices.azure.com/.default")
    return f"aad#{SPEECH_RESOURCE_ID}#{token.token}"


def _make_speech_config() -> "speechsdk.SpeechConfig":
    """Build a SpeechConfig using AAD token auth."""
    if SPEECH_ENDPOINT:
        config = speechsdk.SpeechConfig(endpoint=SPEECH_ENDPOINT)
    else:
        config = speechsdk.SpeechConfig(
            host=f"wss://{SPEECH_REGION}.tts.speech.microsoft.com"
        )
    config.authorization_token = _get_auth_token()
    return config


class TTSRequest(BaseModel):
    text: str


@app.post("/api/tts")
async def text_to_speech(req: TTSRequest):
    """
    Synthesize speech from text using Azure AI Speech Service with
    DefaultAzureCredential AAD token auth and the en-US-Ava:DragonHDLatestNeural voice.
    Returns audio/mpeg.
    """
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Text is required.")

    if not SPEECH_REGION and not SPEECH_ENDPOINT:
        raise HTTPException(
            status_code=503,
            detail="Azure Speech Service is not configured. Set AZURE_SPEECH_REGION or AZURE_SPEECH_ENDPOINT.",
        )

    if not SPEECH_RESOURCE_ID:
        raise HTTPException(
            status_code=503,
            detail="Azure Speech Service is not configured. Set AZURE_SPEECH_RESOURCE_ID.",
        )

    if not _SPEECH_SDK_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="azure-cognitiveservices-speech package is not installed.",
        )

    speech_config = _make_speech_config()
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3
    )
    speech_config.speech_synthesis_voice_name = TTS_VOICE

    # Synthesize to in-memory bytes (audio_config=None suppresses speaker output)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
    result = synthesizer.speak_text_async(req.text.strip()).get()

    if result.reason == speechsdk.ResultReason.Canceled:
        cancellation = result.cancellation_details
        logger.error(
            "[TTS] Synthesis canceled: %s — %s",
            cancellation.reason,
            cancellation.error_details,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Speech synthesis failed: {cancellation.error_details}",
        )

    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        raise HTTPException(status_code=502, detail="Speech synthesis did not complete.")

    audio_data = result.audio_data
    logger.info(
        "[TTS] Synthesized %d bytes for: '%s…'",
        len(audio_data),
        req.text[:60],
    )

    return StreamingResponse(
        io.BytesIO(audio_data),
        media_type="audio/mpeg",
        headers={
            "Content-Length": str(len(audio_data)),
            "Cache-Control": "public, max-age=3600",
        },
    )


@app.post("/api/generate-story")
async def generate_story(request: StoryRequest) -> EventSourceResponse:
    """
    Accepts story parameters and streams back SSE events as the multi-agent
    workflow progresses.  The final event (type: 'complete') contains the
    full illustrated StoryResponse.
    """
    logger.info(
        "[API] New story generation request — main character: '%s'",
        request.main_character,
    )
    return EventSourceResponse(
        _story_event_generator(request),
        media_type="text/event-stream",
    )
