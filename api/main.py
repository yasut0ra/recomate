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
from openai import OpenAI
from pydantic import BaseModel, Field
import uvicorn

logger = logging.getLogger(__name__)

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

# VTuberAIのインスタンス
vtuber = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時の処理
    global vtuber
    try:
        vtuber = VtuberAI()
        # 初期化を待機
        await asyncio.sleep(2)  # 初期化の完了を待つ
        print("VTuberAI initialized successfully")
        yield
    finally:
        # 終了時の処理
        if vtuber:
            vtuber.cleanup()
            print("VTuberAI cleaned up")

# FastAPIアプリケーションの作成
app = FastAPI(lifespan=lifespan)

# CORSの設定
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

@app.post("/api/chat")
async def chat(input_data: TextInput):
    if vtuber is None:
        raise HTTPException(status_code=503, detail="VTuberAI is not initialized")
    
    try:
        vtuber.update_api_key(input_data.api_key)
        # 感情分析
        emotion = vtuber._analyze_emotion(input_data.text)
        
        # 応答生成
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
                # 感情分析
                emotion = vtuber._analyze_emotion(input_data["text"])
                
                # 応答生成
                response = vtuber._generate_response(input_data["text"], emotion)
                
                # レスポンスを送信
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

        # 音声合成の初期化（オプション）
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
                print(f"警告: 音声合成の初期化に失敗しました: {str(e)}")
        
        # 会話履歴の初期化
        self.conversation_history = []
        
        # 感情分析の初期化
        self.emotion_analyzer = EmotionAnalyzer(client=self.openai_client)
        self.emotion_history = []
        
        # トピックの定義
        self.TOPICS = [
            "趣味", "食べ物", "旅行", "音楽", "映画",
            "スポーツ", "テクノロジー", "ファッション", "ゲーム", "読書"
        ]

        # バンディットアルゴリズムの初期化
        self.bandit = TopicBandit(self.TOPICS, client=self.openai_client)
        self.current_topic = None

        # 応答パターン
        self.response_patterns = {
            'greeting': [
                "こんにちは！元気ですか？",
                "やあ！今日はどう？",
                "こんにちは！お話ししましょう！"
            ],
            'question': [
                "そうなんだ！もっと詳しく教えて！",
                "なるほど！それでどう思ったの？",
                "面白いね！他にも何かある？"
            ],
            'emotion': {
                'happy': [
                    "私も嬉しい気持ちになります！",
                    "楽しい話を聞けて嬉しいです！",
                    "その気持ち、よく分かります！"
                ],
                'sad': [
                    "大丈夫？私も力になりたいです。",
                    "辛い気持ち、分かります。",
                    "一緒に考えましょう。"
                ],
                'angry': [
                    "落ち着いて、深呼吸してみましょう。",
                    "その気持ち、分かります。",
                    "一緒に解決策を考えましょう。"
                ],
                'surprised': [
                    "本当にびっくりしました！",
                    "驚きの出来事ですね！",
                    "それは意外でした！"
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

    def _fallback_response(self, user_input: str, emotion: str, emotion_data: Optional[Dict] = None, topic: Optional[str] = None) -> str:
        """LLMが利用できない場合の代替応答を生成"""
        patterns: List[str] = []
        if emotion and isinstance(self.response_patterns.get('emotion'), dict):
            patterns = self.response_patterns['emotion'].get(emotion, [])

        if not patterns:
            patterns = self.response_patterns.get('question', [])

        if not patterns:
            patterns = self.response_patterns.get('greeting', [])

        response_text = random.choice(patterns) if patterns else "ごめんなさい、今はうまく応答できません。"
        self._append_conversation_entry(user_input, response_text, emotion_data)
        if topic:
            try:
                self.bandit.add_to_history(user_input, response_text, topic)
            except Exception as exc:
                logger.debug("Failed to record fallback response in bandit history: %s", exc)

        if emotion_data is not None:
            try:
                expression = self.emotion_analyzer.get_emotion_expression(emotion_data)
                if hasattr(self, 'model') and getattr(self, 'model') is not None:
                    self.model.update_expression(expression)  # type: ignore[attr-defined]
            except Exception as exc:
                logger.debug("Failed to update model expression during fallback: %s", exc)
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
            raise RuntimeError("音声を認識できませんでした") from exc
        except sr.RequestError as exc:
            raise RuntimeError(f"音声認識サービスでエラーが発生しました: {exc}") from exc
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    logger.debug("Temporary audio file cleanup failed", exc_info=True)


    def cleanup(self):
        """リソースの解放"""
        pass  # 必要なクリーンアップ処理があれば追加

    def setup_audio(self):
        try:
            default_device = sd.query_devices(kind='input')
            print(f"デフォルトの入力デバイス: {default_device['name']}")
            self.sample_rate = int(default_device['default_samplerate'])
            self.audio_stream = sd.InputStream(
                device=default_device['index'],
                channels=1,
                samplerate=self.sample_rate,
                blocksize=1024
            )
            self.audio_stream.start()
        except Exception as e:
            print(f"オーディオデバイスの初期化エラー: {e}")
            self.audio_stream = None
            
    def setup_speech_recognition(self):
        self.recognizer = sr.Recognizer()
        self.audio_queue = queue.Queue()
        self.is_listening = False
        
    def speak(self, text):
        """テキストを音声に変換して再生"""
        try:
            # 音声合成が有効な場合のみ音声を生成
            if self.tts:
                self.tts.speak(text)
            else:
                print(f"音声合成が無効なため、テキストのみを表示: {text}")
            
            # 会話履歴に追加
            self.conversation_history.append({"role": "assistant", "content": text})
            
            # 感情分析
            emotion = self.emotion_analyzer.analyze(text)
            self.emotion_history.append(emotion)
            
            return {
                "text": text,
                "emotion": emotion
            }
            
        except Exception as e:
            print(f"音声生成でエラーが発生: {str(e)}")
            return {
                "text": text,
                "emotion": "neutral"
            }
        
    def start_listening(self):
        if not self.is_listening:
            self.is_listening = True
            self.recognition_thread.start()
            print("音声認識を開始しました。話しかけてください。")
            
    def stop_listening(self):
        if self.is_listening:
            self.is_listening = False
            if self.recognition_thread:
                self.recognition_thread.join()
            print("音声認識を停止しました。")
            
    def _recognition_loop(self):
        """音声認識ループ"""
        while self.is_running:
            try:
                with sr.Microphone() as source:
                    print("聞き取り中...")
                    audio = self.recognizer.listen(source)
                    
                    try:
                        text = self.recognizer.recognize_google(audio, language='ja-JP')
                        print(f"認識結果: {text}")
                        
                        # 感情を分析
                        emotion = self._analyze_emotion(text)
                        self.model.update(emotion=emotion, is_speaking=True)
                        
                        # 応答を生成
                        response = self._generate_response(text, emotion)
                        print(f"応答: {response}")
                        
                        # 音声合成
                        self.tts.speak(response)
                        
                        # 会話履歴に追加
                        self.conversation_history.append((text, response))
                        
                    except sr.UnknownValueError:
                        print("音声を認識できませんでした")
                    except sr.RequestError as e:
                        print(f"音声認識サービスでエラーが発生しました: {e}")
                    
            except Exception as e:
                print(f"エラーが発生しました: {e}")
                time.sleep(1)

    def _animation_loop(self):
        """アニメーションループ"""
        while self.is_running:
            # モデルのアニメーションを更新
            self.model.update()
            time.sleep(1/60)  # 60FPS

    def _analyze_emotion(self, text):
        """テキストから感情を分析"""
        text = text.lower()
        if "嬉しい" in text or "楽しい" in text or "ありがとう" in text or "最高" in text:
            return "happy"
        elif "悲しい" in text or "つらい" in text or "寂しい" in text or "辛い" in text:
            return "sad"
        elif "怒" in text or "腹立" in text or "イライラ" in text:
            return "angry"
        elif "驚" in text or "びっくり" in text or "えっ" in text:
            return "surprised"
        return "neutral"

    def _generate_response(self, text, emotion):
        """テキストから応答を生成"""
        # 感情分析
        emotion_data = self.emotion_analyzer.analyze_emotion(text)
        
        # トピックを選択
        topic_idx, selected_topic = self.bandit.select_topic(context=self._get_conversation_context())
        self.current_topic = selected_topic
        
        # サブトピックを生成
        subtopics = self.bandit.generate_subtopics(selected_topic)

        # プロンプトの作成
        prompt = f"""
        トピック「{selected_topic}」について、以下のユーザーの発言に対して応答してください。
        
        ユーザーの感情状態：
        - 主要な感情：{', '.join(emotion_data['primary_emotions'])}
        - 感情の強度：{emotion_data['intensity']}
        - 感情の組み合わせ：{emotion_data['emotion_combination']}
        
        関連するサブトピック：
        {', '.join(subtopics)}
        
        ユーザーの発言：{text}
        
        以下の点に注意して応答してください：
        1. ユーザーの感情状態に共感する
        2. 自然な会話の流れを維持する
        3. 感情表現を豊かに使用する
        4. 会話を発展させる質問を含める
        5. サブトピックを自然に取り入れる
        
        応答は「VTuber:」などの余計な文字を含めないでください。
        """

        if self.openai_client is None:
            logger.warning("VtuberAI: OpenAI client is unavailable; using fallback response.")
            return self._fallback_response(text, emotion, emotion_data, selected_topic)

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "あなたは親しみやすいVTuberです。応答は「VTuber:」などの余計な文字を含めないでください。"},
                    {"role": "user", "content": prompt}
                ]
            )

            response_text = (response.choices[0].message.content or '').strip()
            # 余計な文字を削除
            response_text = response_text.replace("VTuber:", "").strip()
            
            # 応答の評価
            reward = self.bandit.evaluate_response(response_text, text)
            print(f"応答評価スコア: {reward:.2f}")
            self.bandit.update(topic_idx, reward)
            
            # 会話履歴に追加
            self.bandit.add_to_history(text, response_text, selected_topic)
            
            # 感情表現を適用
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
                print("オーディオバッファのオーバーフロー")
            # 音声の強さを計算
            volume = np.abs(data).mean()
            if volume > 0.01:  # この閾値は環境に応じて調整してください
                print(f"音声入力検出: {volume:.4f}")
            return data
        except Exception as e:
            print(f"音声処理エラー: {e}")
            return np.zeros(1024)

    def start(self):
        """Vtuber AIを開始"""
        print("Vtuber AIを開始します...")
        
        # スレッドを開始
        self.recognition_thread.start()
        self.animation_thread.start()
        
        # メインループ
        try:
            while self.is_running:
                # モデルの描画
                self.model.render()
                
                # イベント処理
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.is_running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            self.is_running = False
        finally:
            self.cleanup()

    def record_audio(self):
        """音声を録音してキューに追加"""
        def audio_callback(indata, frames, time, status):
            if status:
                print(f"録音エラー: {status}")
            self.audio_queue.put(indata.copy())
        
        with sd.InputStream(samplerate=self.sample_rate, channels=1,
                          dtype=np.float32, callback=audio_callback):
            print("録音を開始します...")
            while self.is_running:
                time.sleep(0.1)
    
    def process_audio_from_stream(self):
        """録音された音声を処理"""
        while self.is_running:
            if not self.audio_queue.empty():
                audio_data = self.audio_queue.get()
                # 音声データを処理
                self.model.process_audio(audio_data)
    
    def generate_response(self, user_input):
        """ユーザーの入力に対する応答を生成"""
        # 感情分析
        emotion_data = self.emotion_analyzer.analyze_emotion(user_input)
        self.emotion_history.append(emotion_data)
        
        # 感情表現の生成
        emotion_expression = self.emotion_analyzer.get_emotion_expression(emotion_data)
        
        # 会話の文脈を取得
        context = self._get_conversation_context()
        
        # トピックを選択
        topic_idx, selected_topic = self.bandit.select_topic(context=context)
        self.current_topic = selected_topic
        
        # サブトピックを生成
        subtopics = self.bandit.generate_subtopics(selected_topic)
        
        # プロンプトの作成
        prompt = f"""
        トピック「{selected_topic}」について、以下のユーザーの発言に対して応答してください。
        
        ユーザーの感情状態：
        - 主要な感情：{', '.join(emotion_data['primary_emotions'])}
        - 感情の強度：{emotion_data['intensity']}
        - 感情の組み合わせ：{emotion_data['emotion_combination']}
        - 感情の変化：{emotion_data['emotion_change']}
        
        関連するサブトピック：
        {', '.join(subtopics)}

        ユーザーの発言：{user_input}

        以下の点に注意して応答してください：
        1. ユーザーの感情状態に共感する
        2. 自然な会話の流れを維持する
        3. 感情表現を豊かに使用する
        4. 会話を発展させる質問を含める
        5. サブトピックを自然に取り入れる
        """

        if self.openai_client is None:
            logger.warning("VtuberAI: OpenAI client is unavailable; using fallback response.")
            return self._fallback_response(user_input, self._analyze_emotion(user_input), emotion_data, selected_topic)

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "あなたは親しみやすいVTuberです。"},
                    {"role": "user", "content": prompt}
                ]
            )

            response_text = response.choices[0].message.content or ''
            
            # 応答の評価
            reward = self.bandit.evaluate_response(response_text, user_input)
            self.bandit.update(topic_idx, reward)
            
            # 会話履歴に追加
            self.bandit.add_to_history(user_input, response_text, selected_topic)
            
            # 感情表現を適用
            if hasattr(self, 'model') and getattr(self, 'model') is not None:
                try:
                    self.model.update_expression(emotion_expression)  # type: ignore[attr-defined]
                except Exception as exc:
                    logger.debug("Failed to update model expression: %s", exc)
            
            self._append_conversation_entry(user_input, response_text, emotion_data)
            
            return response_text
            
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            logger.error("LLM response generation failed: %s", e)
            return self._fallback_response(user_input, self._analyze_emotion(user_input), emotion_data, selected_topic)
    
    def _get_conversation_context(self):
        """最近の会話履歴から文脈を取得"""
        recent_history = self.bandit.conversation_history[-3:]  # 直近3つの会話を取得
        if not recent_history:
            return ""
        
        context = "最近の会話：\n"
        for entry in recent_history:
            context += f"ユーザー: {entry['user_input']}\n"
            context += f"VTuber: {entry['response']}\n"
        return context

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
