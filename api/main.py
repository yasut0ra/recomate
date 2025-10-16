import asyncio
import io
import json
import logging
import os
import queue
import random
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple, Literal
from uuid import UUID

import numpy as np
import soundfile as sf
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel, Field, ConfigDict
import uvicorn

logger = logging.getLogger(__name__)
SYSTEM_PROMPT = (
    "You are RecoMate, a cheerful Japanese virtual companion who responds with empathy and warmth. "
    "Always reply in natural, friendly Japanese (ja-JP), acknowledge the user's feelings, "
    "include a helpful detail about the topic when possible, finish with a gentle follow-up question when it fits, "
    "and keep the entire reply within two short sentences (120 Japanese characters or fewer)."
)
OPTIONAL_IMPORT_ERRORS: List[Tuple[str, Exception]] = []
_OPTIONAL_IMPORTS_REPORTED = False

try:
    import pygame  # type: ignore
except Exception as exc:
    pygame = None  # type: ignore[assignment]
    OPTIONAL_IMPORT_ERRORS.append(("pygame", exc))
try:
    import sounddevice as sd  # type: ignore
except Exception as exc:
    sd = None  # type: ignore[assignment]
    OPTIONAL_IMPORT_ERRORS.append(("sounddevice", exc))
try:
    import speech_recognition as sr  # type: ignore
except Exception as exc:
    sr = None  # type: ignore[assignment]
    OPTIONAL_IMPORT_ERRORS.append(("speech_recognition", exc))
try:
    from .text_to_speech import TextToSpeech  # type: ignore
except Exception as exc:
    TextToSpeech = None  # type: ignore[assignment]
    OPTIONAL_IMPORT_ERRORS.append(("text_to_speech", exc))
try:
    from .vtuber_model import VtuberModel  # type: ignore
except Exception as exc:
    VtuberModel = None  # type: ignore[assignment]
    OPTIONAL_IMPORT_ERRORS.append(("vtuber_model", exc))
from .emotion_analyzer import EmotionAnalyzer
from .dependencies import SessionDep
from .services.agent_requests import acknowledge_agent_request, generate_agent_request
from .services.album import generate_weekly_album
from .services.consent import get_consent_setting, update_consent_setting
from .services.memory import commit_memory, search_memories
from .services.rituals import get_morning_ritual, get_night_ritual
from .topic_bandit import TopicBandit


vtuber = None

@asynccontextmanager
async def lifespan(app: FastAPI):

    global vtuber
    try:
        vtuber = VtuberAI()

        await asyncio.sleep(2)  # 
        print("VTuberAI initialized successfully")
        yield
    finally:

        if vtuber:
            vtuber.cleanup()
            print("VTuberAI cleaned up")

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
class TextInput(BaseModel):
    text: str
    api_key: Optional[str] = None

class AudioInput(BaseModel):
    audio_data: List[float]
    sample_rate: int = Field(..., gt=0)
    api_key: Optional[str] = None


class TranscriptionResponse(BaseModel):
    text: str
    confidence: Optional[float] = None


class RitualEventModel(BaseModel):
    event: str
    value: str


class RitualResponseModel(BaseModel):
    period: Literal["morning", "night"]
    mood: str
    script: str
    events: List[RitualEventModel]
    source: Literal["default", "custom"]


class MemoryResponseModel(BaseModel):
    id: UUID
    user_id: UUID
    summary_md: str
    keywords: List[str]
    pinned: bool
    created_at: datetime
    last_ref: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class MemoryCommitRequest(BaseModel):
    episode_id: UUID
    summary: Optional[str] = None
    keywords: Optional[List[str]] = None
    pinned: bool = False


class ConsentResponseModel(BaseModel):
    user_id: UUID
    night_mode: bool
    push_intensity: str
    private_topics: List[str]
    learning_paused: bool

    model_config = ConfigDict(from_attributes=True)


class ConsentUpdateRequest(BaseModel):
    night_mode: Optional[bool] = None
    push_intensity: Optional[str] = None
    private_topics: Optional[List[str]] = None
    learning_paused: Optional[bool] = None


class AlbumGenerateRequest(BaseModel):
    user_id: UUID
    week_id: Optional[str] = None
    regenerate: bool = False


class AlbumWeeklyResponseModel(BaseModel):
    week_id: str
    user_id: UUID
    highlights: Dict[str, Any] = Field(alias="highlights_json")
    wins: Dict[str, Any] = Field(alias="wins_json")
    photos: Dict[str, Any]
    quote_best: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AgentRequestResponseModel(BaseModel):
    id: UUID
    user_id: UUID
    kind: str
    payload: Dict[str, Any] | None
    ts: datetime
    accepted: Optional[bool]

    model_config = ConfigDict(from_attributes=True)


class AgentRequestGenerateBody(BaseModel):
    user_id: UUID
    force: bool = False


class AgentRequestAcknowledgeBody(BaseModel):
    request_id: UUID
    accepted: bool
    reason: Optional[str] = None

@app.get("/")
async def root():
    return {"message": "Recomate API Server is running"}

@app.get("/health")
async def health_check():
    if vtuber is None:
        raise HTTPException(status_code=503, detail="VTuberAI is not initialized")
    return {"status": "healthy", "vtuber_status": "initialized"}


@app.get("/api/topics/stats")
async def topic_stats():
    if vtuber is None:
        raise HTTPException(status_code=503, detail="VTuberAI is not initialized")
    try:
        return vtuber.bandit.get_summary()
    except Exception as exc:
        logger.exception("Failed to collect topic stats: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/rituals/morning", response_model=RitualResponseModel)
def fetch_morning_ritual(
    session: SessionDep,
    mood: str = Query("穏やか", description="Desired mood variant for the ritual script."),
    user_id: Optional[UUID] = Query(None, description="User ID for personalised rituals."),
):
    plan = get_morning_ritual(session=session, mood=mood, user_id=user_id)
    return RitualResponseModel(**asdict(plan))


@app.get("/api/rituals/night", response_model=RitualResponseModel)
def fetch_night_ritual(
    session: SessionDep,
    mood: str = Query("穏やか", description="Desired mood variant for the ritual script."),
    user_id: Optional[UUID] = Query(None, description="User ID for personalised rituals."),
):
    plan = get_night_ritual(session=session, mood=mood, user_id=user_id)
    return RitualResponseModel(**asdict(plan))


@app.post("/api/memory/commit", response_model=MemoryResponseModel)
def memory_commit(payload: MemoryCommitRequest, session: SessionDep):
    try:
        memory = commit_memory(
            session=session,
            episode_id=payload.episode_id,
            summary_override=payload.summary,
            keywords_override=payload.keywords,
            pinned=payload.pinned,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to commit memory: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to commit memory")
    return MemoryResponseModel.model_validate(memory)


@app.get("/api/memory/search", response_model=List[MemoryResponseModel])
def memory_search(
    session: SessionDep,
    q: Optional[str] = Query(None, description="Free text query to match summary or keywords."),
    user_id: Optional[UUID] = Query(None, description="Restrict results to a specific user."),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of memories to return."),
):
    try:
        memories = search_memories(session=session, user_id=user_id, query=q, limit=limit)
    except Exception as exc:
        logger.exception("Failed to search memories: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to search memories")
    return [MemoryResponseModel.model_validate(item) for item in memories]


@app.get("/api/consent", response_model=ConsentResponseModel)
def get_consent(
    session: SessionDep,
    user_id: UUID = Query(..., description="User ID whose consent settings should be retrieved."),
):
    try:
        record = get_consent_setting(session=session, user_id=user_id)
    except Exception as exc:
        logger.exception("Failed to fetch consent settings: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch consent settings")
    return ConsentResponseModel.model_validate(record)


@app.patch("/api/consent", response_model=ConsentResponseModel)
def patch_consent(
    payload: ConsentUpdateRequest,
    session: SessionDep,
    user_id: UUID = Query(..., description="User ID whose consent settings should be updated."),
):
    try:
        record = update_consent_setting(session=session, user_id=user_id, updates=payload.model_dump(exclude_unset=True))
    except Exception as exc:
        logger.exception("Failed to update consent settings: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update consent settings")
    return ConsentResponseModel.model_validate(record)


@app.post("/api/album/weekly/generate", response_model=AlbumWeeklyResponseModel)
def generate_weekly_album_endpoint(payload: AlbumGenerateRequest, session: SessionDep):
    try:
        record = generate_weekly_album(
            session=session,
            user_id=payload.user_id,
            week_id=payload.week_id,
            regenerate=payload.regenerate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to generate weekly album: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate weekly album")
    return AlbumWeeklyResponseModel.model_validate(record)


@app.post("/api/agent/request", response_model=AgentRequestResponseModel)
def agent_request(payload: AgentRequestGenerateBody, session: SessionDep):
    try:
        record = generate_agent_request(
            session=session,
            user_id=payload.user_id,
            force=payload.force,
        )
    except Exception as exc:
        logger.exception("Failed to generate agent request: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate agent request")
    return AgentRequestResponseModel.model_validate(record)


@app.post("/api/agent/ack", response_model=AgentRequestResponseModel)
def agent_acknowledge(payload: AgentRequestAcknowledgeBody, session: SessionDep):
    try:
        record = acknowledge_agent_request(
            session=session,
            request_id=payload.request_id,
            accepted=payload.accepted,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to acknowledge agent request: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to acknowledge agent request")
    return AgentRequestResponseModel.model_validate(record)
@app.post("/api/chat")
async def chat(input_data: TextInput):
    if vtuber is None:
        raise HTTPException(status_code=503, detail="VTuberAI is not initialized")
    
    try:
        vtuber.update_api_key(input_data.api_key)

        emotion = vtuber._analyze_emotion(input_data.text)
        

        response = vtuber._generate_response(input_data.text, emotion)
        
        return {
            "response": response,
            "emotion": emotion,
            "conversation_history": vtuber.get_serialised_history()
        }
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/api/analyze-emotion")
async def analyze_emotion(input_data: TextInput):
    if vtuber is None:
        raise HTTPException(status_code=503, detail="VTuberAI is not initialized")
    
    try:
        emotion = vtuber._analyze_emotion(input_data.text)
        return {"emotion": emotion}
    except Exception as e:
        print(f"Error in analyze-emotion endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/api/text-to-speech")
async def text_to_speech(input_data: TextInput):
    if vtuber is None:
        raise HTTPException(status_code=503, detail="VTuberAI is not initialized")
    text = (input_data.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text input is required for TTS")
    try:
        vtuber.update_api_key(input_data.api_key)
        audio_bytes = vtuber.synthesize_speech(text)
        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type="audio/wav",
            headers={"Content-Disposition": "inline; filename=tts.wav"},
        )
    except RuntimeError as exc:
        logger.warning("TTS request failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        logger.warning("Invalid TTS input: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error during TTS generation")
        raise HTTPException(status_code=500, detail=str(exc))
@app.post("/api/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(input_data: AudioInput):
    if vtuber is None:
        raise HTTPException(status_code=503, detail="VTuberAI is not initialized")
    try:
        vtuber.update_api_key(input_data.api_key)
        result = vtuber.transcribe_audio(input_data.audio_data, input_data.sample_rate)
        return result
    except ValueError as exc:
        logger.warning("Invalid audio input: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        logger.warning("Transcription unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error during transcription")
        raise HTTPException(status_code=500, detail=str(exc))
@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    if vtuber is None:
        await websocket.close(code=1008, reason="VTuberAI is not initialized")
        return

    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            input_data = json.loads(data)
            if 'apiKey' in input_data or 'api_key' in input_data:
                api_key = input_data.get('apiKey') or input_data.get('api_key')
                vtuber.update_api_key(api_key)
            try:

                emotion = vtuber._analyze_emotion(input_data["text"])
                

                response = vtuber._generate_response(input_data["text"], emotion)
                

                await websocket.send_json({
                    "response": response,
                    "emotion": emotion,
                    "conversation_history": vtuber.get_serialised_history()
                })
            except Exception as e:
                print(f"Error in websocket chat: {str(e)}")
                await websocket.send_json({
                    "error": str(e)
                })
    except Exception as e:
        print(f"WebSocket error: {str(e)}")
    finally:
        await websocket.close()
class VtuberAI:
    def __init__(self, enable_tts: Optional[bool] = None):
        load_dotenv()
        self._default_api_key = os.getenv('OPENAI_API_KEY')
        self.api_key = self._default_api_key
        self.openai_client = self._create_client(self.api_key)
        self.system_prompt = os.getenv('OPENAI_SYSTEM_PROMPT', SYSTEM_PROMPT)
        primary_model = (os.getenv('OPENAI_CHAT_MODEL') or '').strip()
        fallback_model = (os.getenv('OPENAI_FALLBACK_CHAT_MODEL') or '').strip()
        self.chat_model = primary_model or 'gpt-4.1-mini'
        self.chat_fallback_model = fallback_model or 'gpt-4o-mini'


        self.tts = None
        self.model = None
        self.recognizer = sr.Recognizer() if sr else None
        self.audio_queue = queue.Queue()
        self.recognition_thread = None
        self.animation_thread = None
        self.is_listening = False
        self.is_running = False
        self.audio_stream = None
        self.sample_rate = 16000
        if enable_tts is None:
            enable_tts = os.getenv('ENABLE_TTS', 'false').lower() in {'1', 'true', 'yes', 'on'}

        if enable_tts:
            try:
                self.tts = TextToSpeech()
            except Exception as e:
                print(f"Failed to initialise text-to-speech: {e}")
        

        self.conversation_history = []
        

        self.emotion_analyzer = EmotionAnalyzer(client=self.openai_client)
        self.emotion_history = []
        

        self.TOPICS = [
            "travel", "food", "hobbies", "music", "movies",
            "technology", "wellness", "art", "learning", "relationships"
        ]


        self.bandit = TopicBandit(self.TOPICS, client=self.openai_client)
        self.current_topic = None


        self.response_patterns = {
            'greeting': [
                "Hello! I'm glad you're here today.",
                "Hi there! How are you feeling right now?",
                "Welcome back! Let's relax and talk together."
            ],
            'question': [
                "That sounds interesting. Could you share a little more?",
                "I hear you. What would feel helpful to do next?",
                "Is there something you'd like to try or explore together?"
            ],
            'emotion': {
                'happy': [
                    "Your excitement makes me smile too. Want to keep that good energy going?",
                    "I love how positive that sounds. Tell me a little more about it.",
                    "That's wonderful! How would you like to celebrate this feeling?"
                ],
                'sad': [
                    "That sounds tough. I'm here with you. Want to talk it through together?",
                    "Thank you for trusting me with that. What might help you feel a bit lighter?",
                    "I'm listening. Would taking a small step forward feel okay?"
                ],
                'angry': [
                    "I can tell this is frustrating. What part is bothering you the most right now?",
                    "Your feelings make sense. Want to unpack them together at your pace?",
                    "Let's pause for a breath. How can I support you while things cool down?"
                ],
                'surprised': [
                    "Wow, that was unexpected! What surprised you the most?",
                    "Sounds like quite a twist. How are you feeling about it now?",
                    "Life keeps us on our toes. Want to imagine what might happen next?"
                ]
            }
        }

    def _create_client(self, api_key: Optional[str]) -> Optional[OpenAI]:
        if not api_key:
            logger.warning("OpenAI API key is not configured; LLM features will remain disabled until a key is provided.")
            return None

        try:
            return OpenAI(api_key=api_key)
        except Exception as exc:
            logger.error("Failed to initialise OpenAI client: %s", exc)
            OPTIONAL_IMPORT_ERRORS.append(("openai_client", exc))
            return None

    def update_api_key(self, api_key: Optional[str]):
        new_key = api_key or self._default_api_key
        if new_key == self.api_key and self.openai_client is not None:
            return

        self.api_key = new_key
        self.openai_client = self._create_client(self.api_key)
        if self.openai_client is not None:
            self.emotion_analyzer.set_client(self.openai_client)
            self.bandit.set_client(self.openai_client)
        else:
            self.emotion_analyzer.set_client(None)
            self.bandit.set_client(None)
    def _append_conversation_entry(self, user_input, response, emotion_data=None):
        try:
            entry = {
                'user_input': user_input,
                'response': response,
                'emotion': emotion_data,
                'timestamp': time.time(),
            }
        except Exception:
            entry = {'user_input': user_input, 'response': response}
        self.conversation_history.append(entry)
        if len(self.conversation_history) > 50:
            self.conversation_history = self.conversation_history[-50:]

    def get_serialised_history(self):
        history = []
        for item in self.conversation_history[-50:]:
            if isinstance(item, dict):
                if 'user_input' in item and 'response' in item:
                    history.append({
                        'user_input': item.get('user_input'),
                        'response': item.get('response'),
                        'emotion': item.get('emotion'),
                        'timestamp': item.get('timestamp'),
                    })
                elif item.get('role') and item.get('content'):
                    history.append({
                        'role': item.get('role'),
                        'content': item.get('content'),
                        'timestamp': item.get('timestamp'),
                    })
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                history.append({
                    'user_input': item[0],
                    'response': item[1],
                })
        return history

    @staticmethod
    def _json_default(value: Any):
        if isinstance(value, (np.floating, np.float32, np.float64)):
            return float(value)
        if isinstance(value, (np.integer, np.int32, np.int64)):
            return int(value)
        return str(value)
    def _build_message_history(self, limit: int = 3) -> List[Dict[str, str]]:
        history_messages: List[Dict[str, str]] = []
        recent_pairs = getattr(self.bandit, 'conversation_history', [])[-limit:]
        for entry in recent_pairs:
            user_text = entry.get('user_input') if isinstance(entry, dict) else None
            assistant_text = entry.get('response') if isinstance(entry, dict) else None
            if user_text:
                history_messages.append({'role': 'user', 'content': str(user_text)})
            if assistant_text:
                history_messages.append({'role': 'assistant', 'content': str(assistant_text)})
        return history_messages

    def _prepare_user_prompt(self, user_text: str, selected_topic: str, subtopics: List[str], emotion_payload: Dict[str, Any]) -> str:
        payload = {
            'user_input': user_text,
            'selected_topic': selected_topic,
            'recommended_subtopics': subtopics,
            'detected_emotion': emotion_payload,
            'response_guidelines': [
                'Acknowledge the user\'s feelings in the first sentence (<=40 Japanese characters).',
                'Use at most one additional sentence to share a helpful detail or suggestion (total <=120 Japanese characters).',
                'Include a gentle follow-up question only if it fits naturally and stays within those two sentences.',
                'Avoid filler phrases; deliver no more than two sentences overall.'
            ]
        }
        payload_text = json.dumps(payload, ensure_ascii=False, default=self._json_default)
        return (
            'Generate one friendly Japanese response for RecoMate. '
            'Follow the style guide and use the structured context below as the sole source of truth.\n'
            + payload_text
        )
    def _call_language_model(self, messages: List[Dict[str, str]]) -> str:
        if self.openai_client is None:
            raise RuntimeError('OpenAI client is not configured')
        if not messages:
            raise ValueError('No messages provided to the language model')
        client = self.openai_client
        if hasattr(client, 'responses') and self.chat_model:
            try:
                structured_input = [
                    {
                        'role': message['role'],
                        'content': [{'type': 'text', 'text': message['content']}],
                    }
                    for message in messages
                ]
                response = client.responses.create(
                    model=self.chat_model,
                    input=structured_input,
                )
                output_text = getattr(response, 'output_text', None)
                if output_text:
                    return output_text.strip()
                choices = getattr(response, 'choices', None)
                if choices:
                    message = getattr(choices[0], 'message', None)
                    content = getattr(message, 'content', None) if message else None
                    if isinstance(content, list):
                        joined = ''.join(part.get('text', '') for part in content if isinstance(part, dict))
                        if joined.strip():
                            return joined.strip()
            except Exception as exc:
                logger.debug('Responses API call failed, falling back to chat completions: %s', exc)
        chat_model = self.chat_fallback_model or self.chat_model or 'gpt-4o-mini'
        completion = client.chat.completions.create(
            model=chat_model,
            messages=messages,
        )
        content = completion.choices[0].message.content or ''
        return content.strip()
    def _fallback_response(self, user_input: str, emotion: str, emotion_data: Optional[Dict] = None, topic: Optional[str] = None) -> str:
        """Provide a graceful canned response when the LLM is unavailable."""
        patterns: List[str] = []
        if emotion and isinstance(self.response_patterns.get('emotion'), dict):
            patterns = self.response_patterns['emotion'].get(emotion, [])
        if not patterns:
            patterns = self.response_patterns.get('question', [])
        if not patterns:
            patterns = self.response_patterns.get('greeting', [])
        default_patterns = [
            'Gomen ne, chotto kotae ga matomaranakatta mitai. Mou sukoshi kimochi wo oshiete kureru to ureshii na.',
            'Sukoshi kangaekonde shimatta kamoshiranai kedo, kimi no kimochi ni yorisoi tai kara mou ichido yukkuri hanasou.',
            'Konran shichatta kamo. Demo daijoubu, itsumo soba ni iru kara. Kono ato dou shitai kana?',
        ]
        candidate_pool = patterns or default_patterns
        response_text = random.choice(candidate_pool) if candidate_pool else default_patterns[0]
        if topic:
            response_text += f"\n(Ima {topic} no hanashi to shite kangaete iru yo)"
        self._append_conversation_entry(user_input, response_text, emotion_data)
        if topic:
            try:
                self.bandit.add_to_history(user_input, response_text, topic)
            except Exception as exc:
                logger.debug('Failed to record fallback response in bandit history: %s', exc)
        if emotion_data is not None:
            try:
                expression = self.emotion_analyzer.get_emotion_expression(emotion_data)
                if hasattr(self, 'model') and getattr(self, 'model') is not None:
                    self.model.update_expression(expression)  # type: ignore[attr-defined]
            except Exception as exc:
                logger.debug('Failed to update model expression during fallback: %s', exc)
        return response_text





    def synthesize_speech(self, text: str) -> bytes:
        if not text:
            raise ValueError("Text must not be empty")
        if self.tts is None:
            raise RuntimeError("Text-to-speech is not enabled")
        return self.tts.synthesise(text)

    def transcribe_audio(self, audio_data: List[float], sample_rate: int) -> TranscriptionResponse:
        if sr is None or self.recognizer is None:
            raise RuntimeError("Speech recognition is not available")
        if sample_rate <= 0:
            raise ValueError("Sample rate must be a positive integer")
        if not audio_data:
            raise ValueError("Audio data is empty")
        audio_array = np.array(audio_data, dtype=np.float32)
        if not np.isfinite(audio_array).all():
            raise ValueError("Audio data contains invalid values")
        temp_file: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                temp_file = tmp.name
                sf.write(tmp.name, audio_array, sample_rate, subtype='PCM_16')
            with sr.AudioFile(temp_file) as source:
                audio = self.recognizer.record(source)
            result = self.recognizer.recognize_google(audio, language='ja-JP', show_all=True)
            transcript = ''
            confidence: Optional[float] = None

            if isinstance(result, dict):
                alternatives = result.get('alternative') or []
                if alternatives:
                    primary = alternatives[0]
                    transcript = primary.get('transcript', '')
                    confidence = primary.get('confidence')
            if not transcript:
                transcript = self.recognizer.recognize_google(audio, language='ja-JP')
            return TranscriptionResponse(text=transcript, confidence=confidence)
        except sr.UnknownValueError as exc:
            raise RuntimeError("Speech recognition could not understand the audio input") from exc
        except sr.RequestError as exc:
            raise RuntimeError(f"Speech recognition service request failed: {exc}") from exc
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    logger.debug("Temporary audio file cleanup failed", exc_info=True)



    def cleanup(self):
        """Release background resources held by the VTuber instance."""
        self.is_listening = False
        self.is_running = False
        if getattr(self, 'audio_stream', None) is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception:
                logger.debug('Audio stream cleanup failed', exc_info=True)
            finally:
                self.audio_stream = None
        if self.recognition_thread and self.recognition_thread.is_alive():
            self.recognition_thread.join(timeout=1)
        if self.animation_thread and self.animation_thread.is_alive():
            self.animation_thread.join(timeout=1)

    def _analyze_emotion(self, text: str) -> str:
        """Lightweight keyword-based fallback emotion analysis."""
        if not text:
            return 'neutral'
        lowered = text.lower()
        happy_keywords = {'happy', 'glad', 'great', 'awesome', 'joy'}
        sad_keywords = {'sad', 'down', 'tired', 'lonely', 'blue'}
        angry_keywords = {'angry', 'mad', 'upset', 'frustrated', 'annoyed'}
        surprised_keywords = {'surprised', 'wow', 'shocked', 'unexpected'}
        if any(word in lowered for word in happy_keywords):
            return 'happy'
        if any(word in lowered for word in sad_keywords):
            return 'sad'
        if any(word in lowered for word in angry_keywords):
            return 'angry'
        if any(word in lowered for word in surprised_keywords):
            return 'surprised'
        return 'neutral'

    def _generate_response(self, text, emotion):


        """Generate a conversational response using the configured language model."""
        emotion_data = self.emotion_analyzer.analyze_emotion(text)
        conversation_context = self._get_conversation_context()
        bandit_features = {
            'context_text': conversation_context,
            'emotion': emotion_data,
            'user_input': text,
        }
        topic_idx, selected_topic = self.bandit.select_topic(context=conversation_context, features=bandit_features)
        self.current_topic = selected_topic
        subtopics = self.bandit.generate_subtopics(selected_topic)
        bandit_features['subtopics'] = subtopics
        messages: List[Dict[str, str]] = [{'role': 'system', 'content': self.system_prompt}]
        messages.extend(self._build_message_history())
        user_message = self._prepare_user_prompt(text, selected_topic, subtopics, emotion_data)
        messages.append({'role': 'user', 'content': user_message})
        if self.openai_client is None:
            logger.warning('VtuberAI: OpenAI client is unavailable; using fallback response.')
            return self._fallback_response(text, emotion, emotion_data, selected_topic)
        try:
            response_text = self._call_language_model(messages)
        except Exception as exc:
            logger.error('LLM response generation failed: %s', exc)
            return self._fallback_response(text, emotion, emotion_data, selected_topic)
        if not response_text:
            logger.warning('Received empty response from language model; using fallback.')
            return self._fallback_response(text, emotion, emotion_data, selected_topic)
        reward = self.bandit.evaluate_response(response_text, text)
        logger.debug('Bandit reward: %.2f', reward)
        try:
            self.bandit.update(topic_idx, reward, features=bandit_features)
        except Exception as exc:
            logger.debug('Failed to update bandit parameters: %s', exc)
        try:
            self.bandit.add_to_history(text, response_text, selected_topic)
        except Exception as exc:
            logger.debug('Failed to append to bandit history: %s', exc)
        try:
            emotion_expression = self.emotion_analyzer.get_emotion_expression(emotion_data)
            if hasattr(self, 'model') and getattr(self, 'model') is not None:
                self.model.update_expression(emotion_expression)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.debug('Failed to update model expression: %s', exc)
        self._append_conversation_entry(text, response_text, emotion_data)
        return response_text
    def _get_conversation_context(self):
        """Return a lightweight text summary of recent dialog turns."""
        recent_history = getattr(self.bandit, 'conversation_history', [])[-3:]
        if not recent_history:
            return ''
        lines: List[str] = []
        for entry in recent_history:
            if not isinstance(entry, dict):
                continue
            user_text = entry.get('user_input')
            assistant_text = entry.get('response')
            if user_text:
                lines.append(f'User: {user_text}')
            if assistant_text:
                lines.append(f'RecoMate: {assistant_text}')
        return '\n'.join(lines)
if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
