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
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import soundfile as sf
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi import APIRouter
from openai import OpenAI
from pydantic import BaseModel, Field
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
from .topic_bandit import TopicBandit

# VTuberAI縺ｮ繧､繝ｳ繧ｹ繧ｿ繝ｳ繧ｹ
vtuber = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 襍ｷ蜍墓凾縺ｮ蜃ｦ逅・
    global vtuber
    try:
        vtuber = VtuberAI()
        # 蛻晄悄蛹悶ｒ蠕・ｩ・
        await asyncio.sleep(2)  # 蛻晄悄蛹悶・螳御ｺ・ｒ蠕・▽
        print("VTuberAI initialized successfully")
        yield
    finally:
        # 邨ゆｺ・凾縺ｮ蜃ｦ逅・
        if vtuber:
            vtuber.cleanup()
            print("VTuberAI cleaned up")
# FastAPI繧｢繝励Μ繧ｱ繝ｼ繧ｷ繝ｧ繝ｳ縺ｮ菴懈・
app = FastAPI(lifespan=lifespan)
# CORS縺ｮ險ｭ螳・
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
        # 諢滓ュ蛻・梵
        emotion = vtuber._analyze_emotion(input_data.text)
        
        # 蠢懃ｭ皮函謌・
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
                # 諢滓ュ蛻・梵
                emotion = vtuber._analyze_emotion(input_data["text"])
                
                # 蠢懃ｭ皮函謌・
                response = vtuber._generate_response(input_data["text"], emotion)
                
                # 繝ｬ繧ｹ繝昴Φ繧ｹ繧帝∽ｿ｡
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

        # 髻ｳ螢ｰ蜷域・縺ｮ蛻晄悄蛹厄ｼ医が繝励す繝ｧ繝ｳ・・
        self.tts = None
        self.model = None
        self.recognizer = sr.Recognizer() if sr else None
        self.audio_queue = queue.Queue()
        self.recognition_thread = None
        self.animation_thread = None
        self.is_listening = False
        self.is_running = False
        if enable_tts is None:
            enable_tts = os.getenv('ENABLE_TTS', 'false').lower() in {'1', 'true', 'yes', 'on'}

        if enable_tts:
            try:
                self.tts = TextToSpeech()
            except Exception as e:
                print(f"隴ｦ蜻・ 髻ｳ螢ｰ蜷域・縺ｮ蛻晄悄蛹悶↓螟ｱ謨励＠縺ｾ縺励◆: {str(e)}")
        
        # 莨夊ｩｱ螻･豁ｴ縺ｮ蛻晄悄蛹・
        self.conversation_history = []
        
        # 諢滓ュ蛻・梵縺ｮ蛻晄悄蛹・
        self.emotion_analyzer = EmotionAnalyzer(client=self.openai_client)
        self.emotion_history = []
        
        # 繝医ヴ繝・け縺ｮ螳夂ｾｩ
        self.TOPICS = [
            "travel", "food", "hobbies", "music", "movies",
            "technology", "wellness", "art", "learning", "relationships"
        ]

        # 繝舌Φ繝・ぅ繝・ヨ繧｢繝ｫ繧ｴ繝ｪ繧ｺ繝縺ｮ蛻晄悄蛹・
        self.bandit = TopicBandit(self.TOPICS, client=self.openai_client)
        self.current_topic = None

        # 蠢懃ｭ斐ヱ繧ｿ繝ｼ繝ｳ
        self.response_patterns = {
            'greeting': [
                'こんにちは！今日も会いに来てくれて嬉しいな。',
                'やっほー！今日はどんな気分？',
                'また会えたね。一緒にゆっくり話そう。'
            ],
            'question': [
                'その話、とても気になるな。もう少し聞かせてくれる？',
                'そっかぁ…今はどんな気持ちなのかな？',
                '次にやってみたいことって何か浮かんでる？'
            ],
            'emotion': {
                'happy': [
                    '嬉しさが伝わってきて私まで笑顔になっちゃうよ。',
                    'そのワクワク、大事にしたいね。もっと聞かせてほしいな。',
                    'いい感じ！その調子で楽しんでいこうね。'
                ],
                'sad': [
                    'そうだったんだね…そばにいるから、ゆっくり話しても大丈夫だよ。',
                    'つらかったね。今はどんなふうに寄り添えたら嬉しい？',
                    '気持ちを言葉にしてくれてありがとう。一緒に少しずつ軽くしよう。'
                ],
                'angry': [
                    'それはモヤモヤしちゃうよね…。気持ちの整理、手伝わせて。',
                    '怒りは大事なサインだよ。何がいちばん気になっている？',
                    '落ち着くまでゆっくりでいいよ。いつでも聞くからね。'
                ],
                'surprised': [
                    'わぁ！その驚き、どんなことがあったのか気になるな。',
                    'びっくりしたね！その瞬間、どう感じたか教えてくれる？',
                    '予想外の出来事って面白いかも。これからどうなると思う？'
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
            raise RuntimeError("髻ｳ螢ｰ繧定ｪ崎ｭ倥〒縺阪∪縺帙ｓ縺ｧ縺励◆") from exc
        except sr.RequestError as exc:
            raise RuntimeError(f"髻ｳ螢ｰ隱崎ｭ倥し繝ｼ繝薙せ縺ｧ繧ｨ繝ｩ繝ｼ縺檎匱逕溘＠縺ｾ縺励◆: {exc}") from exc
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    logger.debug("Temporary audio file cleanup failed", exc_info=True)

    def cleanup(self):
        """繝ｪ繧ｽ繝ｼ繧ｹ縺ｮ隗｣謾ｾ"""
        pass  # 蠢・ｦ√↑繧ｯ繝ｪ繝ｼ繝ｳ繧｢繝・・蜃ｦ逅・′縺ゅｌ縺ｰ霑ｽ蜉

    def setup_audio(self):
        try:
            default_device = sd.query_devices(kind='input')
            print(f"繝・ヵ繧ｩ繝ｫ繝医・蜈･蜉帙ョ繝舌う繧ｹ: {default_device['name']}")
            self.sample_rate = int(default_device['default_samplerate'])
            self.audio_stream = sd.InputStream(
                device=default_device['index'],
                channels=1,
                samplerate=self.sample_rate,
                blocksize=1024
            )
            self.audio_stream.start()
        except Exception as e:
            print(f"繧ｪ繝ｼ繝・ぅ繧ｪ繝・ヰ繧､繧ｹ縺ｮ蛻晄悄蛹悶お繝ｩ繝ｼ: {e}")
            self.audio_stream = None
            
    def setup_speech_recognition(self):
        self.recognizer = sr.Recognizer()
        self.audio_queue = queue.Queue()
        self.is_listening = False
        
    def speak(self, text):
        """繝・く繧ｹ繝医ｒ髻ｳ螢ｰ縺ｫ螟画鋤縺励※蜀咲函"""
        try:
            # 髻ｳ螢ｰ蜷域・縺梧怏蜉ｹ縺ｪ蝣ｴ蜷医・縺ｿ髻ｳ螢ｰ繧堤函謌・
            if self.tts:
                self.tts.speak(text)
            else:
                print(f"髻ｳ螢ｰ蜷域・縺檎┌蜉ｹ縺ｪ縺溘ａ縲√ユ繧ｭ繧ｹ繝医・縺ｿ繧定｡ｨ遉ｺ: {text}")
            
            # 莨夊ｩｱ螻･豁ｴ縺ｫ霑ｽ蜉
            self.conversation_history.append({"role": "assistant", "content": text})
            
            # 諢滓ュ蛻・梵
            emotion = self.emotion_analyzer.analyze(text)
            self.emotion_history.append(emotion)
            
            return {
                "text": text,
                "emotion": emotion
            }
            
        except Exception as e:
            print(f"髻ｳ螢ｰ逕滓・縺ｧ繧ｨ繝ｩ繝ｼ縺檎匱逕・ {str(e)}")
            return {
                "text": text,
                "emotion": "neutral"
            }
        
    def start_listening(self):
        if not self.is_listening:
            self.is_listening = True
            self.recognition_thread.start()
            print("髻ｳ螢ｰ隱崎ｭ倥ｒ髢句ｧ九＠縺ｾ縺励◆縲りｩｱ縺励°縺代※縺上□縺輔＞縲・)
            
    def stop_listening(self):
        if self.is_listening:
            self.is_listening = False
            if self.recognition_thread:
                self.recognition_thread.join()
            print("髻ｳ螢ｰ隱崎ｭ倥ｒ蛛懈ｭ｢縺励∪縺励◆縲・)
            
    def _recognition_loop(self):
        """髻ｳ螢ｰ隱崎ｭ倥Ν繝ｼ繝・""
        while self.is_running:
            try:
                with sr.Microphone() as source:
                    print("閨槭″蜿悶ｊ荳ｭ...")
                    audio = self.recognizer.listen(source)
                    
                    try:
                        text = self.recognizer.recognize_google(audio, language='ja-JP')
                        print(f"隱崎ｭ倡ｵ先棡: {text}")
                        
                        # 諢滓ュ繧貞・譫・
                        emotion = self._analyze_emotion(text)
                        self.model.update(emotion=emotion, is_speaking=True)
                        
                        # 蠢懃ｭ斐ｒ逕滓・
                        response = self._generate_response(text, emotion)
                        print(f"蠢懃ｭ・ {response}")
                        
                        # 髻ｳ螢ｰ蜷域・
                        self.tts.speak(response)
                        
                        # 莨夊ｩｱ螻･豁ｴ縺ｫ霑ｽ蜉
                        self.conversation_history.append((text, response))
                        
                    except sr.UnknownValueError:
                        print("髻ｳ螢ｰ繧定ｪ崎ｭ倥〒縺阪∪縺帙ｓ縺ｧ縺励◆")
                    except sr.RequestError as e:
                        print(f"髻ｳ螢ｰ隱崎ｭ倥し繝ｼ繝薙せ縺ｧ繧ｨ繝ｩ繝ｼ縺檎匱逕溘＠縺ｾ縺励◆: {e}")
                    
            except Exception as e:
                print(f"繧ｨ繝ｩ繝ｼ縺檎匱逕溘＠縺ｾ縺励◆: {e}")
                time.sleep(1)
    def _animation_loop(self):
        """繧｢繝九Γ繝ｼ繧ｷ繝ｧ繝ｳ繝ｫ繝ｼ繝・""
        while self.is_running:
            # 繝｢繝・Ν縺ｮ繧｢繝九Γ繝ｼ繧ｷ繝ｧ繝ｳ繧呈峩譁ｰ
            self.model.update()
            time.sleep(1/60)  # 60FPS

    def _analyze_emotion(self, text):
        """繝・く繧ｹ繝医°繧画─諠・ｒ蛻・梵"""
        text = text.lower()
        if "螫峨＠縺・ in text or "讌ｽ縺励＞" in text or "縺ゅｊ縺後→縺・ in text or "譛鬮・ in text:
            return "happy"
        elif "謔ｲ縺励＞" in text or "縺､繧峨＞" in text or "蟇ゅ＠縺・ in text or "霎帙＞" in text:
            return "sad"
        elif "諤・ in text or "閻ｹ遶・ in text or "繧､繝ｩ繧､繝ｩ" in text:
            return "angry"
        elif "鬩・ in text or "縺ｳ縺｣縺上ｊ" in text or "縺医▲" in text:
            return "surprised"
        return "neutral"

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


        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "縺ゅ↑縺溘・隕ｪ縺励∩繧・☆縺ХTuber縺ｧ縺吶ょｿ懃ｭ斐・縲祁Tuber:縲阪↑縺ｩ縺ｮ菴呵ｨ医↑譁・ｭ励ｒ蜷ｫ繧√↑縺・〒縺上□縺輔＞縲・},
                    {"role": "user", "content": prompt}
                ]
            )
            response_text = (response.choices[0].message.content or '').strip()
            # 菴呵ｨ医↑譁・ｭ励ｒ蜑企勁
            response_text = response_text.replace("VTuber:", "").strip()
            
            # 蠢懃ｭ斐・隧穂ｾ｡
            reward = self.bandit.evaluate_response(response_text, text)
            print(f"蠢懃ｭ碑ｩ穂ｾ｡繧ｹ繧ｳ繧｢: {reward:.2f}")
            self.bandit.update(topic_idx, reward, features=bandit_features)
            
            # 莨夊ｩｱ螻･豁ｴ縺ｫ霑ｽ蜉
            self.bandit.add_to_history(text, response_text, selected_topic)
            
            # 諢滓ュ陦ｨ迴ｾ繧帝←逕ｨ
            emotion_expression = self.emotion_analyzer.get_emotion_expression(emotion_data)
            if hasattr(self, 'model') and getattr(self, 'model') is not None:
                try:
                    self.model.update_expression(emotion_expression)  # type: ignore[attr-defined]
                except Exception as exc:
                    logger.debug("Failed to update model expression: %s", exc)
            self._append_conversation_entry(text, response_text, emotion_data)
            
            return response_text
            
        except Exception as e:
            logger.error("LLM response generation failed: %s", e)
            return self._fallback_response(text, emotion, emotion_data, selected_topic)
    def process_audio(self):
        if self.audio_stream is None:
            return np.zeros(1024)
        try:
            data, overflowed = self.audio_stream.read(1024)
            if overflowed:
                print("繧ｪ繝ｼ繝・ぅ繧ｪ繝舌ャ繝輔ぃ縺ｮ繧ｪ繝ｼ繝舌・繝輔Ο繝ｼ")
            # 髻ｳ螢ｰ縺ｮ蠑ｷ縺輔ｒ險育ｮ・
            volume = np.abs(data).mean()
            if volume > 0.01:  # 縺薙・髢ｾ蛟､縺ｯ迺ｰ蠅・↓蠢懊§縺ｦ隱ｿ謨ｴ縺励※縺上□縺輔＞
                print(f"髻ｳ螢ｰ蜈･蜉帶､懷・: {volume:.4f}")
            return data
        except Exception as e:
            print(f"髻ｳ螢ｰ蜃ｦ逅・お繝ｩ繝ｼ: {e}")
            return np.zeros(1024)
    def start(self):
        """Vtuber AI繧帝幕蟋・""
        print("Vtuber AI繧帝幕蟋九＠縺ｾ縺・..")
        
        # 繧ｹ繝ｬ繝・ラ繧帝幕蟋・
        self.recognition_thread.start()
        self.animation_thread.start()
        
        # 繝｡繧､繝ｳ繝ｫ繝ｼ繝・
        try:
            while self.is_running:
                # 繝｢繝・Ν縺ｮ謠冗判
                self.model.render()
                
                # 繧､繝吶Φ繝亥・逅・
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.is_running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            self.is_running = False
        finally:
            self.cleanup()
    def record_audio(self):
        """髻ｳ螢ｰ繧帝鹸髻ｳ縺励※繧ｭ繝･繝ｼ縺ｫ霑ｽ蜉"""
        def audio_callback(indata, frames, time, status):
            if status:
                print(f"骭ｲ髻ｳ繧ｨ繝ｩ繝ｼ: {status}")
            self.audio_queue.put(indata.copy())
        
        with sd.InputStream(samplerate=self.sample_rate, channels=1,
                          dtype=np.float32, callback=audio_callback):
            print("骭ｲ髻ｳ繧帝幕蟋九＠縺ｾ縺・..")
            while self.is_running:
                time.sleep(0.1)
    
    def process_audio_from_stream(self):
        """骭ｲ髻ｳ縺輔ｌ縺滄浹螢ｰ繧貞・逅・""
        while self.is_running:
            if not self.audio_queue.empty():
                audio_data = self.audio_queue.get()
                # 髻ｳ螢ｰ繝・・繧ｿ繧貞・逅・
                self.model.process_audio(audio_data)
    
    def generate_response(self, user_input):
        """繝ｦ繝ｼ繧ｶ繝ｼ縺ｮ蜈･蜉帙↓蟇ｾ縺吶ｋ蠢懃ｭ斐ｒ逕滓・"""
        # 諢滓ュ蛻・梵
        emotion_data = self.emotion_analyzer.analyze_emotion(user_input)
        self.emotion_history.append(emotion_data)
        
        # 諢滓ュ陦ｨ迴ｾ縺ｮ逕滓・
        emotion_expression = self.emotion_analyzer.get_emotion_expression(emotion_data)
        
        # 莨夊ｩｱ縺ｮ譁・ц繧貞叙蠕・
        context = self._get_conversation_context()
        bandit_features = {
            'context_text': context,
            'emotion': emotion_data,
            'user_input': user_input,
        }

        # 繝医ヴ繝・け繧帝∈謚・
        topic_idx, selected_topic = self.bandit.select_topic(context=context, features=bandit_features)
        self.current_topic = selected_topic

        # 繧ｵ繝悶ヨ繝斐ャ繧ｯ繧堤函謌・
        subtopics = self.bandit.generate_subtopics(selected_topic)
        bandit_features['subtopics'] = subtopics
        
        # 繝励Ο繝ｳ繝励ヨ縺ｮ菴懈・
        prompt = f"""
        繝医ヴ繝・け縲鶏selected_topic}縲阪↓縺､縺・※縲∽ｻ･荳九・繝ｦ繝ｼ繧ｶ繝ｼ縺ｮ逋ｺ險縺ｫ蟇ｾ縺励※蠢懃ｭ斐＠縺ｦ縺上□縺輔＞縲・
        
        繝ｦ繝ｼ繧ｶ繝ｼ縺ｮ諢滓ュ迥ｶ諷具ｼ・
        - 荳ｻ隕√↑諢滓ュ・嘴', '.join(emotion_data['primary_emotions'])}
        - 諢滓ュ縺ｮ蠑ｷ蠎ｦ・嘴emotion_data['intensity']}
        - 諢滓ュ縺ｮ邨・∩蜷医ｏ縺幢ｼ嘴emotion_data['emotion_combination']}
        - 諢滓ュ縺ｮ螟牙喧・嘴emotion_data['emotion_change']}
        
        髢｢騾｣縺吶ｋ繧ｵ繝悶ヨ繝斐ャ繧ｯ・・
        {', '.join(subtopics)}

        繝ｦ繝ｼ繧ｶ繝ｼ縺ｮ逋ｺ險・嘴user_input}

        莉･荳九・轤ｹ縺ｫ豕ｨ諢上＠縺ｦ蠢懃ｭ斐＠縺ｦ縺上□縺輔＞・・
        1. 繝ｦ繝ｼ繧ｶ繝ｼ縺ｮ諢滓ュ迥ｶ諷九↓蜈ｱ諢溘☆繧・
        2. 閾ｪ辟ｶ縺ｪ莨夊ｩｱ縺ｮ豬√ｌ繧堤ｶｭ謖√☆繧・
        3. 諢滓ュ陦ｨ迴ｾ繧定ｱ翫°縺ｫ菴ｿ逕ｨ縺吶ｋ
        4. 莨夊ｩｱ繧堤匱螻輔＆縺帙ｋ雉ｪ蝠上ｒ蜷ｫ繧√ｋ
        5. 繧ｵ繝悶ヨ繝斐ャ繧ｯ繧定・辟ｶ縺ｫ蜿悶ｊ蜈･繧後ｋ
        """

        if self.openai_client is None:
            logger.warning("VtuberAI: OpenAI client is unavailable; using fallback response.")
            return self._fallback_response(user_input, self._analyze_emotion(user_input), emotion_data, selected_topic)
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "縺ゅ↑縺溘・隕ｪ縺励∩繧・☆縺ХTuber縺ｧ縺吶・},
                    {"role": "user", "content": prompt}
                ]
            )
            response_text = response.choices[0].message.content or ''
            
            # 蠢懃ｭ斐・隧穂ｾ｡
            reward = self.bandit.evaluate_response(response_text, user_input)
            self.bandit.update(topic_idx, reward, features=bandit_features)
            
            # 莨夊ｩｱ螻･豁ｴ縺ｫ霑ｽ蜉
            self.bandit.add_to_history(user_input, response_text, selected_topic)
            
            # 諢滓ュ陦ｨ迴ｾ繧帝←逕ｨ
            if hasattr(self, 'model') and getattr(self, 'model') is not None:
                try:
                    self.model.update_expression(emotion_expression)  # type: ignore[attr-defined]
                except Exception as exc:
                    logger.debug("Failed to update model expression: %s", exc)
            
            self._append_conversation_entry(user_input, response_text, emotion_data)
            
            return response_text
            
        except Exception as e:
            print(f"繧ｨ繝ｩ繝ｼ縺檎匱逕溘＠縺ｾ縺励◆: {e}")
            logger.error("LLM response generation failed: %s", e)
            return self._fallback_response(user_input, self._analyze_emotion(user_input), emotion_data, selected_topic)
    
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
