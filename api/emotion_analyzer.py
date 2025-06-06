import openai
from typing import Dict, List, Tuple
import numpy as np
from dotenv import load_dotenv
import os

class EmotionAnalyzer:
    def __init__(self):
        # 環境変数の読み込み
        load_dotenv()
        openai.api_key = os.getenv('OPENAI_API_KEY')
        
        # 基本感情の定義
        self.base_emotions = [
            "喜び", "悲しみ", "怒り", "驚き", "恐れ", "嫌悪", "期待", "信頼"
        ]
        
        # 感情の強度レベル
        self.intensity_levels = ["弱い", "中程度", "強い"]
        
        # 感情の組み合わせパターン
        self.emotion_combinations = [
            "喜びと期待",
            "悲しみと恐れ",
            "怒りと嫌悪",
            "驚きと喜び",
            "信頼と期待"
        ]
    
    def analyze_emotion(self, text: str) -> Dict:
        """テキストから感情を分析"""
        try:
            prompt = f"""
            以下のテキストから感情を分析してください：
            
            テキスト：{text}
            
            以下の形式で分析結果を返してください：
            1. 主要な感情（複数可）
            2. 感情の強度（0.0-1.0）
            3. 感情の組み合わせ
            4. 感情の変化（もしあれば）
            5. 感情の理由
            
            分析は以下の点に注意してください：
            - 文脈を考慮する
            - 暗黙的な感情も考慮する
            - 文化的な要素も考慮する
            - 感情の複雑さを捉える
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "あなたは感情分析の専門家です。"},
                    {"role": "user", "content": prompt}
                ]
            )
            
            analysis = response.choices[0].message.content
            
            # 分析結果を構造化
            return self._parse_analysis(analysis)
            
        except Exception as e:
            print(f"感情分析でエラーが発生: {e}")
            return self._get_default_emotion()
    
    def _parse_analysis(self, analysis: str) -> Dict:
        """分析結果を構造化された形式に変換"""
        try:
            # 分析結果を行ごとに分割
            lines = analysis.strip().split('\n')
            
            # 結果を格納する辞書
            result = {
                'primary_emotions': [],
                'intensity': 0.5,
                'emotion_combination': '中立',
                'emotion_change': 'なし',
                'reason': '',
                'confidence': 0.0
            }
            
            # 各行を解析
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                if '1.' in line or '主要な感情' in line:
                    emotions = line.split('：')[-1].strip()
                    result['primary_emotions'] = [e.strip() for e in emotions.split('、')]
                elif '2.' in line or '感情の強度' in line:
                    try:
                        intensity = line.split('：')[-1].strip()
                        result['intensity'] = float(intensity)
                    except:
                        result['intensity'] = 0.5
                elif '3.' in line or '感情の組み合わせ' in line:
                    result['emotion_combination'] = line.split('：')[-1].strip()
                elif '4.' in line or '感情の変化' in line:
                    result['emotion_change'] = line.split('：')[-1].strip()
                elif '5.' in line or '感情の理由' in line:
                    result['reason'] = line.split('：')[-1].strip()
            
            # 信頼度の計算（感情の数と強度に基づく）
            result['confidence'] = min(1.0, len(result['primary_emotions']) * 0.2 + result['intensity'] * 0.5)
            
            return result
            
        except Exception as e:
            print(f"分析結果の解析でエラーが発生: {e}")
            return self._get_default_emotion()
    
    def _get_default_emotion(self) -> Dict:
        """デフォルトの感情状態を返す"""
        return {
            'primary_emotions': ['中立'],
            'intensity': 0.5,
            'emotion_combination': '中立',
            'emotion_change': 'なし',
            'reason': '感情分析ができませんでした',
            'confidence': 0.0
        }
    
    def get_emotion_expression(self, emotion_data: Dict) -> str:
        """感情データに基づいて表現を生成"""
        try:
            prompt = f"""
            以下の感情データに基づいて、VTuberの表現を生成してください：
            
            主要な感情：{', '.join(emotion_data['primary_emotions'])}
            感情の強度：{emotion_data['intensity']}
            感情の組み合わせ：{emotion_data['emotion_combination']}
            感情の変化：{emotion_data['emotion_change']}
            
            以下の形式で表現を返してください：
            1. 表情の説明
            2. 声の調子
            3. 体の動き
            4. 感情表現の強さ（0.0-1.0）
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "あなたはVTuberの表現を生成する専門家です。"},
                    {"role": "user", "content": prompt}
                ]
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"感情表現の生成でエラーが発生: {e}")
            return "通常の表情"
    
    def get_emotion_history(self, text_history: List[str]) -> List[Dict]:
        """会話履歴から感情の変化を分析"""
        emotions = []
        for text in text_history:
            emotion = self.analyze_emotion(text)
            emotions.append(emotion)
        return emotions 