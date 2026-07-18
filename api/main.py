"""FastAPI application wiring for RecoMate.

Routes are thin: chat orchestration lives in ChatEngine, audio in
SpeechService, and feature endpoints in routers/services. Chat endpoints are
plain ``def`` functions so FastAPI runs them in its threadpool and a slow LLM
call cannot stall the event loop.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional
from uuid import UUID

import sqlalchemy as sa
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import uvicorn

from .chat_engine import ChatEngine, ChatTurnResult
from .db.session import get_session
from .routers.features import router as features_router
from .schemas import AudioInput, TextInput, TranscriptionResponse
from .services.chat_payloads import build_chat_response_payload
from .services.speech import SpeechService

logger = logging.getLogger(__name__)

engine: Optional[ChatEngine] = None
speech: Optional[SpeechService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine, speech
    engine = ChatEngine()
    speech = SpeechService()
    logger.info("RecoMate chat engine initialised")
    try:
        yield
    finally:
        engine = None
        speech = None


app = FastAPI(lifespan=lifespan)

default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:4173",   # Vite preview
    "http://127.0.0.1:4173",
]

environment_origins = os.getenv("ALLOW_ORIGINS")
if environment_origins:
    allowed_origins = [origin.strip() for origin in environment_origins.split(",") if origin.strip()]
else:
    allowed_origins = default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(features_router)


def _require_engine() -> ChatEngine:
    if engine is None:
        raise HTTPException(status_code=503, detail="Chat engine is not initialised")
    return engine


def _require_speech() -> SpeechService:
    if speech is None:
        raise HTTPException(status_code=503, detail="Speech service is not initialised")
    return speech


def _turn_payload(result: ChatTurnResult) -> Dict[str, Any]:
    return build_chat_response_payload(
        response=result.response,
        user_emotion=result.user_emotion,
        assistant_emotion=result.assistant_emotion,
        reward=result.reward,
        conversation_history=result.history,
        turn_metadata=result.turn_metadata,
    )


def _database_connected() -> bool:
    session = None
    try:
        session = get_session()
        session.execute(sa.text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        if session is not None:
            session.close()


@app.get("/")
async def root():
    return {"message": "Recomate API Server is running"}


@app.get("/health")
def health_check():
    active_engine = _require_engine()
    active_speech = _require_speech()
    return {
        "status": "healthy",
        "llm_configured": active_engine.llm_configured,
        "database_connected": _database_connected(),
        "tts_enabled": active_speech.tts_enabled,
        "transcription_available": active_speech.transcription_available,
    }


@app.get("/api/topics/stats")
def topic_stats():
    active_engine = _require_engine()
    try:
        return active_engine.topic_summary()
    except Exception:
        logger.exception("Failed to collect topic stats")
        raise HTTPException(status_code=500, detail="Failed to collect topic stats")


@app.post("/api/chat")
def chat(input_data: TextInput):
    active_engine = _require_engine()
    try:
        result = active_engine.handle_turn(
            input_data.text,
            user_id=input_data.user_id,
            api_key=input_data.api_key,
        )
    except Exception:
        logger.exception("Chat turn failed")
        raise HTTPException(status_code=500, detail="Failed to generate a response")
    return _turn_payload(result)


@app.post("/api/analyze-emotion")
def analyze_emotion(input_data: TextInput):
    active_engine = _require_engine()
    try:
        return {"emotion": active_engine.analyze_emotion_label(input_data.text)}
    except Exception:
        logger.exception("Emotion analysis failed")
        raise HTTPException(status_code=500, detail="Failed to analyze emotion")


@app.post("/api/text-to-speech")
def text_to_speech(input_data: TextInput):
    active_speech = _require_speech()
    text = (input_data.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text input is required for TTS")
    try:
        audio_bytes = active_speech.synthesize(text)
    except RuntimeError as exc:
        logger.warning("TTS request failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        logger.warning("Invalid TTS input: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Unexpected error during TTS generation")
        raise HTTPException(status_code=500, detail="Failed to synthesize speech")
    return StreamingResponse(
        io.BytesIO(audio_bytes),
        media_type="audio/wav",
        headers={"Content-Disposition": "inline; filename=tts.wav"},
    )


@app.post("/api/transcribe", response_model=TranscriptionResponse)
def transcribe_audio(input_data: AudioInput):
    active_speech = _require_speech()
    try:
        transcript, confidence = active_speech.transcribe(input_data.audio_data, input_data.sample_rate)
        return TranscriptionResponse(text=transcript, confidence=confidence)
    except ValueError as exc:
        logger.warning("Invalid audio input: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        logger.warning("Transcription unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        logger.exception("Unexpected error during transcription")
        raise HTTPException(status_code=500, detail="Failed to transcribe audio")


def _parse_ws_user_id(raw: Any) -> Optional[UUID]:
    if isinstance(raw, str) and raw.strip():
        try:
            return UUID(raw)
        except ValueError:
            logger.debug("Ignoring invalid websocket user id: %s", raw)
    return None


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    if engine is None:
        await websocket.close(code=1008, reason="Chat engine is not initialised")
        return

    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON payload"})
                continue

            text = data.get("text") if isinstance(data, dict) else None
            if not isinstance(text, str) or not text.strip():
                await websocket.send_json({"error": "Field 'text' is required"})
                continue

            api_key = data.get("apiKey") or data.get("api_key")
            user_id = _parse_ws_user_id(data.get("userId") or data.get("user_id"))
            try:
                result = await asyncio.to_thread(engine.handle_turn, text, user_id, api_key)
                await websocket.send_json(_turn_payload(result))
            except Exception:
                logger.exception("WebSocket chat turn failed")
                await websocket.send_json({"error": "Failed to generate a response"})
    except WebSocketDisconnect:
        logger.debug("WebSocket client disconnected")
    except Exception:
        logger.exception("WebSocket session failed")
        try:
            await websocket.close(code=1011)
        except Exception:
            logger.debug("WebSocket close after failure raised", exc_info=True)


if __name__ == "__main__":
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
