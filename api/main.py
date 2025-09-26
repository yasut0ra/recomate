import asyncio
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
from openai import OpenAI
from pydantic import BaseModel
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
    from text_to_speech import TextToSpeech  # type: ignore
except Exception as exc:
    TextToSpeech = None  # type: ignore[assignment]
    OPTIONAL_IMPORT_ERRORS.append(("text_to_speech", exc))

try:
    from vtuber_model import VtuberModel  # type: ignore
except Exception as exc:
    VtuberModel = None  # type: ignore[assignment]
    OPTIONAL_IMPORT_ERRORS.append(("vtuber_model", exc))

from emotion_analyzer import EmotionAnalyzer
from topic_bandit import TopicBandit

class _NullVtuberModel:
    """Fallback avatar when graphical dependencies are unavailable."""

    def update(self, *args, **kwargs):
        return None

    def update_expression(self, *args, **kwargs):
        return None

    def render(self, *args, **kwargs):
        return None

    def process_audio(self, *args, **kwargs):
        return None


def _report_optional_imports_once() -> None:
    global _OPTIONAL_IMPORTS_REPORTED
    if _OPTIONAL_IMPORTS_REPORTED:
        return
    if not OPTIONAL_IMPORT_ERRORS:
        _OPTIONAL_IMPORTS_REPORTED = True
        return
    for name, exc in OPTIONAL_IMPORT_ERRORS:
        logger.warning("Optional dependency %s is unavailable (%s)", name, exc)
    _OPTIONAL_IMPORTS_REPORTED = True


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
        _report_optional_imports_once()

        self._default_api_key = os.getenv('OPENAI_API_KEY')
        self.api_key = self._default_api_key
        if not self._default_api_key:
            logger.info('OPENAI_API_KEY not found; awaiting runtime API key input')
        try:
            self.openai_client = self._create_client(self.api_key)
        except Exception as exc:
            logger.error('Failed to initialise OpenAI client: %s', exc)
            raise

        self.model = self._initialise_model()

        self.is_running = True
        self.audio_stream = None
        self.sample_rate = 16000
        self.recognition_thread = None
        self.animation_thread = None

        # 音声合成の初期化（オプション）
        self.tts = None
        if enable_tts is None:
            enable_tts = os.getenv('ENABLE_TTS', 'false').lower() in {'1', 'true', 'yes', 'on'}

        if enable_tts:
            if TextToSpeech is None:
                logger.warning('Text-to-speech dependency is unavailable; disabling TTS')
            else:
                try:
                    self.tts = TextToSpeech()
                except Exception as exc:
                    logger.warning('Text-to-speech initialisation failed: %s', exc)

        if sr is not None:
            try:
                self.setup_speech_recognition()
            except Exception as exc:
                logger.warning('Speech recognition initialisation failed: %s', exc)
                self.recognition_thread = None
        else:
            self.recognizer = None
            self.audio_queue = queue.Queue()
            self.is_listening = False

        if pygame is not None and not isinstance(self.model, _NullVtuberModel):
            self.animation_thread = threading.Thread(target=self._animation_loop, daemon=True)

        # 会話履歴の初期化
        self.conversation_history = []

        # 感情分析の初期化
        self.emotion_analyzer = EmotionAnalyzer(client=self.openai_client)
        self.emotion_history = []

        # トピックの定義
        self.TOPICS = [
            '趣味', '食べ物', '旅行', '音楽', '映画',
            'スポーツ', 'テクノロジー', 'ファッション', 'ゲーム', '読書'
        ]

        # バンディットアルゴリズムの初期化
        self.bandit = TopicBandit(self.TOPICS, client=self.openai_client)
        self.current_topic = None

        # 応答パターン
        self.response_patterns = {
            'greeting': [
                'こんにちは！元気ですか？',
                'やあ！今日はどう？',
                'こんにちは！お話ししましょう！'
            ],
            'question': [
                'そうなんだ！もっと詳しく教えて！',
                'なるほど！それでどう思ったの？',
                '面白いね！他にも何かある？'
            ],
            'emotion': {
                'happy': [
                    '私も嬉しい気持ちになります！',
                    '楽しい話を聞けて嬉しいです！',
                    'その気持ち、よく分かります！'
                ],
                'sad': [
                    '大丈夫？私も力になりたいです。',
                    '辛い気持ち、分かります。',
                    '一緒に考えましょう。'
                ],
                'angry': [
                    '落ち着いて、深呼吸してみましょう。',
                    'その気持ち、分かります。',
                    '一緒に解決策を考えましょう。'
                ],
                'surprised': [
                    '本当にびっくりしました！',
                    '驚きの出来事ですね！',
                    'それは意外でした！'
                ]
            }
        }

    def _initialise_model(self):
        if VtuberModel is None:
            logger.info('VtuberModel dependency not available; using null model')
            return _NullVtuberModel()
        try:
            return VtuberModel()
        except Exception as exc:
            logger.warning('Failed to initialise VtuberModel: %s', exc)
            return _NullVtuberModel()

    def _create_client(self, api_key: Optional[str]) -> OpenAI:
        if api_key:
            return OpenAI(api_key=api_key)
        return OpenAI()

    @staticmethod
    def _mask_key(value: Optional[str]) -> str:
        if not value:
            return '(empty)'
        if len(value) <= 6:
            return value[0] + '...' + value[-1]
        return value[:3] + '...' + value[-3:]

    def update_api_key(self, api_key: Optional[str]):
        new_key = api_key or self._default_api_key
        if not new_key:
            logger.warning('OpenAI API key is empty; authentication may fail')
        if new_key == self.api_key and self.openai_client is not None:
            return

        self.api_key = new_key
        try:
            self.openai_client = self._create_client(self.api_key)
        except Exception as exc:
            logger.error('Failed to refresh OpenAI client: %s', exc)
            raise

        self.emotion_analyzer.set_client(self.openai_client)
        self.bandit.set_client(self.openai_client)
        origin = 'UI override' if api_key else 'environment'
        logger.info('OpenAI API key updated (%s, %s)', origin, self._mask_key(self.api_key))

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



    def cleanup(self):
        """リソースの解放"""
        pass  # 必要なクリーンアップ処理があれば追加

    def setup_audio(self):
        if sd is None:
            logger.info('sounddevice dependency is unavailable; skipping audio setup')
            return
        try:
            default_device = sd.query_devices(kind='input')
            logger.info('Using audio input device: %s', default_device['name'])
            self.sample_rate = int(default_device['default_samplerate'])
            self.audio_stream = sd.InputStream(
                device=default_device['index'],
                channels=1,
                samplerate=self.sample_rate,
                blocksize=1024
            )
            self.audio_stream.start()
        except Exception as exc:
            logger.warning('Audio device initialisation failed: %s', exc)
            self.audio_stream = None
            
    def setup_speech_recognition(self):
        self.recognizer = sr.Recognizer()
        self.audio_queue = queue.Queue()
        self.is_listening = False
        
    def speak(self, text):
        """テキストを音声に変換して再生"""
        try:
            if self.tts:
                self.tts.speak(text)
            else:
                logger.debug('TTS disabled; text response: %s', text)

            self.conversation_history.append({"role": "assistant", "content": text})

            emotion = self.emotion_analyzer.analyze(text)
            self.emotion_history.append(emotion)

            return {
                "text": text,
                "emotion": emotion
            }
        except Exception as exc:
            logger.warning('Text-to-speech failed: %s', exc)
            return {
                "text": text,
                "emotion": "neutral"
            }
        
    def start_listening(self):
        if sr is None or getattr(self, 'recognizer', None) is None:
            logger.warning('Speech recognition is not available; cannot start listening')
            return
        if self.is_listening:
            return
        self.is_listening = True
        self.is_running = True
        if self.recognition_thread is None or not self.recognition_thread.is_alive():
            self.recognition_thread = threading.Thread(target=self._recognition_loop, daemon=True)
            self.recognition_thread.start()
            logger.info('Speech recognition started')

    def stop_listening(self):
        if not self.is_listening:
            return
        self.is_listening = False
        if self.recognition_thread and self.recognition_thread.is_alive():
            self.is_running = False
            self.recognition_thread.join(timeout=2)
            logger.info('Speech recognition stopped')
            
    def _recognition_loop(self):
        """音声認識ループ"""
        while self.is_running:
            try:
                with sr.Microphone() as source:
                    logger.debug('Listening for audio input')
                    audio = self.recognizer.listen(source)

                    try:
                        text = self.recognizer.recognize_google(audio, language='ja-JP')
                        logger.debug('Speech recognised: %s', text)

                        emotion = self._analyze_emotion(text)
                        self.model.update(emotion=emotion, is_speaking=True)

                        response = self._generate_response(text, emotion)
                        logger.debug('Generated response: %s', response)

                        if self.tts:
                            self.tts.speak(response)

                        self.conversation_history.append((text, response))

                    except sr.UnknownValueError:
                        logger.debug('Speech could not be recognised')
                    except sr.RequestError as exc:
                        logger.warning('Speech recognition service error: %s', exc)

            except Exception as exc:
                logger.warning('Speech recognition loop error: %s', exc)
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
            self.model.update_expression(emotion_expression)
            
            self._append_conversation_entry(text, response_text, emotion_data)
            
            return response_text
            
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            return "すみません、応答を生成できませんでした。"

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
        logger.info('Starting Vtuber AI loop')
        self.is_running = True

        if sr is not None:
            self.start_listening()

        if pygame is None or isinstance(self.model, _NullVtuberModel):
            logger.info('Rendering dependencies unavailable; skipping animation loop')
            return

        if self.animation_thread is None or not self.animation_thread.is_alive():
            self.animation_thread = threading.Thread(target=self._animation_loop, daemon=True)
            self.animation_thread.start()

        try:
            while self.is_running:
                self.model.render()

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.is_running = False
                    elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
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
            self.model.update_expression(emotion_expression)
            
            self._append_conversation_entry(user_input, response_text, emotion_data)
            
            return response_text
            
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            return "すみません、応答を生成できませんでした。"
    
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
