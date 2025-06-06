import os
import pygame
import sounddevice as sd
import numpy as np
from dotenv import load_dotenv
import openai
import time
import speech_recognition as sr
import queue
import threading
from gtts import gTTS
import tempfile
from text_to_speech import TextToSpeech
from vtuber_model import VtuberModel
import random
import soundfile as sf
from topic_bandit import TopicBandit
from emotion_analyzer import EmotionAnalyzer
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
from typing import List, Dict, Any
import asyncio
from pydantic import BaseModel
from contextlib import asynccontextmanager

app = FastAPI(lifespan=lifespan)

# CORSの設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Viteのデフォルトポート
        "http://localhost:3000",  # 開発用ポート
        "http://localhost:8000",  # FastAPIサーバー
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# VTuberAIのインスタンス
vtuber = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時の処理
    global vtuber
    try:
        vtuber = VtuberAI()
        print("VTuberAI initialized successfully")
        yield
    finally:
        # 終了時の処理
        if vtuber:
            vtuber.cleanup()
            print("VTuberAI cleaned up")

class TextInput(BaseModel):
    text: str

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
        # 感情分析
        emotion = vtuber._analyze_emotion(input_data.text)
        
        # 応答生成
        response = vtuber._generate_response(input_data.text, emotion)
        
        return {
            "response": response,
            "emotion": emotion,
            "conversation_history": vtuber.conversation_history
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
            
            try:
                # 感情分析
                emotion = vtuber._analyze_emotion(input_data["text"])
                
                # 応答生成
                response = vtuber._generate_response(input_data["text"], emotion)
                
                # レスポンスを送信
                await websocket.send_json({
                    "response": response,
                    "emotion": emotion,
                    "conversation_history": vtuber.conversation_history
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
    def __init__(self):
        load_dotenv()
        openai.api_key = os.getenv('OPENAI_API_KEY')
        print("利用可能なオーディオデバイス:")
        print(sd.query_devices())
        self.setup_audio()
        self.setup_speech_recognition()
        
        # 音声合成の初期化
        self.tts = TextToSpeech()
        
        # 3Dモデルの初期化
        self.model = VtuberModel()
        
        # 会話履歴の初期化
        self.conversation_history = []
        
        # スレッドの制御用フラグ
        self.is_running = True
        
        # 音声認識スレッド
        self.recognition_thread = threading.Thread(target=self._recognition_loop)
        self.recognition_thread.daemon = True
        
        # アニメーションスレッド
        self.animation_thread = threading.Thread(target=self._animation_loop)
        self.animation_thread.daemon = True
        
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

        # トピックの定義
        self.TOPICS = [
            "趣味",
            "食べ物",
            "旅行",
            "音楽",
            "映画",
            "スポーツ",
            "テクノロジー",
            "ファッション",
            "ゲーム",
            "読書"
        ]

        # バンディットアルゴリズムの初期化
        self.bandit = TopicBandit(self.TOPICS)
        self.current_topic = None

        # 感情分析の初期化
        self.emotion_analyzer = EmotionAnalyzer()
        self.emotion_history = []

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
        
    def text_to_speech(self, text):
        """テキストを音声に変換して再生"""
        try:
            # 音声パラメータを設定（必要に応じて調整可能）
            self.tts.set_voice_parameters(
                speed_scale=1.0,      # 話速
                volume_scale=1.0,     # 音量
                pre_phoneme_length=0.1,  # 音の前の無音時間
                post_phoneme_length=0.1  # 音の後の無音時間
            )
            
            # 音声を生成して再生
            self.tts.speak(text)
            
        except Exception as e:
            print(f"音声生成でエラーが発生: {str(e)}")
            # エラーが発生しても会話は継続
            pass
        
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
        
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "あなたは親しみやすいVTuberです。応答は「VTuber:」などの余計な文字を含めないでください。"},
                    {"role": "user", "content": prompt}
                ]
            )
            
            response_text = response.choices[0].message.content.strip()
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

    def cleanup(self):
        self.stop_listening()
        if self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception as e:
                print(f"オーディオストリームのクリーンアップエラー: {e}")
        
        print("クリーンアップ完了")

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
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "あなたは親しみやすいVTuberです。"},
                    {"role": "user", "content": prompt}
                ]
            )
            
            response_text = response.choices[0].message.content
            
            # 応答の評価
            reward = self.bandit.evaluate_response(response_text, user_input)
            self.bandit.update(topic_idx, reward)
            
            # 会話履歴に追加
            self.bandit.add_to_history(user_input, response_text, selected_topic)
            
            # 感情表現を適用
            self.model.update_expression(emotion_expression)
            
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