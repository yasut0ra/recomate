import asyncio
from datetime import datetime
import io
import json
import logging
import os
import queue
import random
import tempfile
import threading
import time
import wave
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
import uvicorn

logger = logging.getLogger(__name__)
SYSTEM_PROMPT = (
    "You are RecoMate, a personal Japanese companion AI. "
    "Reply in natural, warm Japanese (ja-JP), stay emotionally attuned, and avoid sounding pushy or generic. "
    "Start by acknowledging the user's feeling or situation, then add one useful or connective detail. "
    "Keep the reply within two short sentences and 120 Japanese characters or fewer."
)
OPTIONAL_IMPORT_ERRORS: List[Tuple[str, Exception]] = []
_OPTIONAL_IMPORTS_REPORTED = False

try:
    import pygame  # type: ignore
except Exception as exc:
    pygame = None  # type: ignore[assignment]
    OPTIONAL_IMPORT_ERRORS.append(("pygame", exc))
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
from .db.session import get_session
from .emotion_analyzer import EmotionAnalyzer
from .routers.features import router as features_router
from .schemas import AudioInput, TextInput, TranscriptionResponse
from .services.consent import get_consent_setting
from .services.conversation_planner import ConversationPlan, ConversationPlanner
from .services.memory import build_memory_context
from .services.mood import get_recent_moods
from .services.preferences import get_preference_profile
from .services.users import resolve_local_user
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
app.include_router(features_router)

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


@app.post("/api/chat")
async def chat(input_data: TextInput):
    if vtuber is None:
        raise HTTPException(status_code=503, detail="VTuberAI is not initialized")
    
    try:
        vtuber.update_api_key(input_data.api_key)
        emotion_data = vtuber.emotion_analyzer.analyze_emotion(input_data.text)
        emotion = vtuber._emotion_label_from_payload(emotion_data)
        runtime_context = vtuber._build_runtime_context(input_data.user_id, current_text=input_data.text)
        response = vtuber._generate_response(input_data.text, emotion, emotion_data, runtime_context)
        
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
                emotion_data = vtuber.emotion_analyzer.analyze_emotion(input_data["text"])
                emotion = vtuber._emotion_label_from_payload(emotion_data)
                raw_user_id = input_data.get("userId") or input_data.get("user_id")
                parsed_user_id = None
                if isinstance(raw_user_id, str) and raw_user_id.strip():
                    try:
                        parsed_user_id = UUID(raw_user_id)
                    except ValueError:
                        parsed_user_id = None
                runtime_context = vtuber._build_runtime_context(parsed_user_id, current_text=input_data["text"])
                response = vtuber._generate_response(input_data["text"], emotion, emotion_data, runtime_context)

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
        self.conversation_planner = ConversationPlanner()
        self.TOPICS = self.conversation_planner.topic_families
        self.bandit = TopicBandit(self.TOPICS, client=self.openai_client)
        self.current_topic = None


        self.response_patterns = {
            'greeting': [
                "来てくれてうれしいよ。今日はどんな気分？",
                "おかえり。今いちばん話したいことある？",
                "ここではゆっくり話していいよ。何から話そうか。"
            ],
            'question': [
                "もう少しだけ聞かせて。どのあたりが気になってる？",
                "その感じ、少し分かるよ。今いちばん引っかかってるのはどこ？",
                "一緒に整理してみようか。どこから話すと楽そう？"
            ],
            'emotion': {
                'happy': [
                    "それはうれしいね。どこが特によかったの？",
                    "いい流れだね。その気分、もう少し聞かせてほしいな。",
                    "それはにやけるやつだね。いちばん印象に残ったのは何？"
                ],
                'sad': [
                    "それはしんどかったね。無理のないところから話してみようか。",
                    "話してくれてありがとう。今いちばん重い部分はどこ？",
                    "ちゃんとつらかったよね。少しずつ整理していこう。"
                ],
                'angry': [
                    "それは腹が立つよね。何がいちばん引っかかった？",
                    "その怒りは自然だと思う。少しずつほどいてみようか。",
                    "かなりもやっとしたよね。まず状況を一緒に整理しよう。"
                ],
                'surprised': [
                    "それはびっくりするね。どこが一番予想外だった？",
                    "急な展開だったんだね。今はどう受け止めてる？",
                    "思ってない方向に動いたんだね。その後どうなったの？"
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

    def _prepare_user_prompt(
        self,
        user_text: str,
        plan: ConversationPlan,
        emotion_payload: Dict[str, Any],
        runtime_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        payload = {
            'user_input': user_text,
            'conversation_plan': plan.to_prompt_payload(),
            'detected_emotion': emotion_payload,
            'runtime_context': {
                'display_name': (runtime_context or {}).get('display_name'),
                'mood_state': (runtime_context or {}).get('mood_state'),
                'timezone': (runtime_context or {}).get('timezone'),
                'local_hour': (runtime_context or {}).get('local_hour'),
                'preferences': (runtime_context or {}).get('preferences'),
                'memory_context': (runtime_context or {}).get('memory_context'),
            },
            'response_guidelines': [
                '1文目で感情や状況を短く受け止める。',
                '2文目は会話プランに沿って深掘り・提案・共感のいずれかを自然に行う。',
                '質問は必要なときだけ1つ、二文以内に収める。',
                '話題ラベルをそのまま言わず、自然な会話として返す。',
                '関連する記憶があっても、不自然に引用せず会話に溶かす。',
                '好みの口調は反映するが、説明的なメタ発言はしない。'
            ]
        }
        payload_text = json.dumps(payload, ensure_ascii=False, default=self._json_default)
        return (
            'Generate one natural Japanese companion reply for RecoMate. '
            'Use the conversation plan to decide tone, continuity, and whether to ask a follow-up.\n'
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
            'うまく言葉をまとめきれなかったけど、もう少しだけ聞かせてくれる？',
            '少し考えこんじゃったけど、ちゃんと寄り添いたいからゆっくり話そう。',
            'いったん落ち着いて受け止めたいな。今の気持ちを少しだけ教えて。',
        ]
        candidate_pool = patterns or default_patterns
        response_text = random.choice(candidate_pool) if candidate_pool else default_patterns[0]
        self._append_conversation_entry(user_input, response_text, emotion_data)
        if topic:
            try:
                self.bandit.record_topic_selection(topic)
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
                pcm_audio = np.clip(audio_array, -1.0, 1.0)
                pcm_bytes = (pcm_audio * 32767).astype(np.int16).tobytes()
                with wave.open(tmp.name, 'wb') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(sample_rate)
                    wav_file.writeframes(pcm_bytes)
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
        """Return the primary emotion label used by the UI."""
        emotion_data = self.emotion_analyzer.analyze_emotion(text)
        return self._emotion_label_from_payload(emotion_data)

    def _emotion_label_from_payload(self, emotion_payload: Optional[Dict[str, Any]]) -> str:
        if not emotion_payload:
            return 'neutral'
        primary = emotion_payload.get('primary_emotions')
        if isinstance(primary, list) and primary:
            candidate = primary[0]
            if isinstance(candidate, str) and candidate:
                return candidate.lower()
        return 'neutral'

    def _resolve_local_hour(self, timezone_name: Optional[str]) -> int:
        resolved_timezone = timezone_name or 'Asia/Tokyo'
        try:
            return datetime.now(ZoneInfo(resolved_timezone)).hour
        except ZoneInfoNotFoundError:
            logger.debug('Unknown timezone %s; falling back to Asia/Tokyo', resolved_timezone)
        except Exception:
            logger.debug('Failed to resolve local hour for timezone %s', resolved_timezone, exc_info=True)
        return datetime.now(ZoneInfo('Asia/Tokyo')).hour

    def _build_runtime_context(self, user_id: Optional[UUID], current_text: str = '') -> Dict[str, Any]:
        default_context = {
            'user_id': str(user_id) if user_id else None,
            'display_name': 'Local User',
            'timezone': 'Asia/Tokyo',
            'local_hour': self._resolve_local_hour('Asia/Tokyo'),
            'mood_state': '穏やか',
            'consent': {
                'night_mode': True,
                'push_intensity': 'medium',
                'private_topics': ['個人特定情報'],
                'learning_paused': False,
            },
            'preferences': {
                'tone': 0.6,
                'humor': 0.5,
                'style_notes': {},
                'style_summary': {
                    'tone_style': '親しみやすく自然体',
                    'humor_style': '必要なときだけ軽くユーモアを混ぜる',
                    'length_style': '短く収める',
                    'metaphor_style': '比喩は必要なときだけ軽く使う',
                    'formality_style': 'フラットで自然な口調',
                },
                'tts_voice': 'voicevox:normal',
            },
            'memory_context': [],
        }
        session = get_session()
        try:
            user = resolve_local_user(session, user_id)
            mood_state, _ = get_recent_moods(session, user.id, limit=5)
            consent = get_consent_setting(session, user.id)
            preferences = get_preference_profile(session, user.id)
            memory_context = build_memory_context(session, user.id, query=current_text, limit=3)
            timezone_name = getattr(user, 'timezone', None) or 'Asia/Tokyo'
            return {
                'user_id': str(user.id),
                'display_name': user.display_name,
                'timezone': timezone_name,
                'local_hour': self._resolve_local_hour(timezone_name),
                'mood_state': mood_state,
                'consent': {
                    'night_mode': bool(consent.night_mode),
                    'push_intensity': consent.push_intensity,
                    'private_topics': list(consent.private_topics or []),
                    'learning_paused': bool(consent.learning_paused),
                },
                'preferences': preferences,
                'memory_context': memory_context,
            }
        except Exception as exc:
            logger.debug('Failed to build runtime context for chat; using defaults: %s', exc)
            return default_context
        finally:
            session.close()

    def _generate_response(
        self,
        text,
        emotion,
        emotion_data: Optional[Dict[str, Any]] = None,
        runtime_context: Optional[Dict[str, Any]] = None,
    ):
        """Generate a conversational response using the configured language model."""
        if emotion_data is None:
            emotion_data = self.emotion_analyzer.analyze_emotion(text)
        if runtime_context is None:
            runtime_context = self._build_runtime_context(None)
        recent_history = getattr(self.bandit, 'conversation_history', [])[-4:]
        plan = self.conversation_planner.plan(
            user_text=text,
            emotion_payload=emotion_data,
            recent_history=recent_history,
            mood_state=runtime_context.get('mood_state'),
            consent_profile=runtime_context.get('consent'),
            local_hour=runtime_context.get('local_hour'),
        )
        self.current_topic = plan.topic_family
        messages: List[Dict[str, str]] = [{'role': 'system', 'content': self.system_prompt}]
        messages.extend(self._build_message_history())
        user_message = self._prepare_user_prompt(text, plan, emotion_data, runtime_context)
        messages.append({'role': 'user', 'content': user_message})
        if self.openai_client is None:
            logger.warning('VtuberAI: OpenAI client is unavailable; using fallback response.')
            return self._fallback_response(text, emotion, emotion_data, plan.topic_family)
        try:
            response_text = self._call_language_model(messages)
        except Exception as exc:
            logger.error('LLM response generation failed: %s', exc)
            return self._fallback_response(text, emotion, emotion_data, plan.topic_family)
        if not response_text:
            logger.warning('Received empty response from language model; using fallback.')
            return self._fallback_response(text, emotion, emotion_data, plan.topic_family)
        try:
            self.bandit.record_topic_selection(plan.topic_family)
            self.bandit.add_to_history(text, response_text, plan.topic_family)
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
if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
