import os
import json
import requests
import pygame
import hashlib
import tempfile
from pathlib import Path

class TextToSpeech:
    def __init__(self, voice_id=1, cache_dir="voice_cache"):
        self.voice_id = voice_id
        self.base_url = "http://localhost:50021"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # pygameの初期化
        pygame.mixer.init()
        
        # 音声の品質設定
        self.speed_scale = 1.0
        self.volume_scale = 1.0
        self.pre_phoneme_length = 0.1
        self.post_phoneme_length = 0.1
        
        # VOICEVOXの状態確認
        self._check_voicevox_status()

    def _check_voicevox_status(self):
        """VOICEVOXの状態を確認"""
        try:
            response = requests.get(f"{self.base_url}/version")
            if response.status_code == 200:
                version = response.text  # バージョンは直接テキストとして返される
                print(f"VOICEVOX version: {version}")
            else:
                raise Exception("VOICEVOXサーバーが応答しません")
        except requests.exceptions.ConnectionError:
            raise Exception("VOICEVOXサーバーに接続できません。VOICEVOXが起動しているか確認してください。")

    def _get_cache_path(self, text):
        """テキストに対応するキャッシュファイルのパスを取得"""
        # テキストと設定からハッシュを生成
        cache_key = f"{text}_{self.voice_id}_{self.speed_scale}_{self.volume_scale}"
        hash_value = hashlib.md5(cache_key.encode()).hexdigest()
        return self.cache_dir / f"{hash_value}.wav"

    def _generate_audio(self, text):
        """音声を生成"""
        try:
            # 音声合成用のパラメータを設定
            params = {
                "text": text,
                "speaker": self.voice_id,
                "speed_scale": self.speed_scale,
                "volume_scale": self.volume_scale,
                "pre_phoneme_length": self.pre_phoneme_length,
                "post_phoneme_length": self.post_phoneme_length
            }
            
            # 音声合成のリクエスト
            response = requests.post(f"{self.base_url}/audio_query", params=params)
            if response.status_code != 200:
                raise Exception(f"音声合成のリクエストに失敗: {response.status_code}")
            
            # 音声を生成
            response = requests.post(f"{self.base_url}/synthesis", 
                                  params=params,
                                  data=json.dumps(response.json()))
            if response.status_code != 200:
                raise Exception(f"音声の生成に失敗: {response.status_code}")
            
            return response.content
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"VOICEVOXとの通信でエラーが発生: {str(e)}")

    def speak(self, text):
        """テキストを音声に変換して再生"""
        try:
            # キャッシュを確認
            cache_path = self._get_cache_path(text)
            if cache_path.exists():
                print("キャッシュから音声を読み込みます")
                audio_data = cache_path.read_bytes()
            else:
                print("新しい音声を生成します")
                audio_data = self._generate_audio(text)
                # キャッシュに保存
                cache_path.write_bytes(audio_data)
            
            # 一時ファイルを作成
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_filename = temp_file.name
                temp_file.write(audio_data)
            
            try:
                # 音声を再生
                pygame.mixer.music.load(temp_filename)
                pygame.mixer.music.play()
                
                # 再生が終わるまで待機
                while pygame.mixer.music.get_busy():
                    pygame.time.Clock().tick(10)
            finally:
                # 再生が終わったら一時ファイルを削除
                try:
                    os.unlink(temp_filename)
                except Exception as e:
                    print(f"一時ファイルの削除でエラーが発生: {str(e)}")
            
        except Exception as e:
            print(f"音声生成でエラーが発生: {str(e)}")
            raise

    def set_voice_parameters(self, speed_scale=None, volume_scale=None, 
                           pre_phoneme_length=None, post_phoneme_length=None):
        """音声パラメータを設定"""
        if speed_scale is not None:
            self.speed_scale = speed_scale
        if volume_scale is not None:
            self.volume_scale = volume_scale
        if pre_phoneme_length is not None:
            self.pre_phoneme_length = pre_phoneme_length
        if post_phoneme_length is not None:
            self.post_phoneme_length = post_phoneme_length

if __name__ == "__main__":
    # テスト用
    tts = TextToSpeech()
    tts.speak("こんにちは、私はAI Vtuberです。") 