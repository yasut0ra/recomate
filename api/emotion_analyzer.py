"""Local-first emotion analysis helpers."""

from __future__ import annotations

from typing import Dict, List, Optional
import logging
import unicodedata

from dotenv import load_dotenv
from openai import OpenAI

logger = logging.getLogger(__name__)

EMOTION_KEYWORDS: Dict[str, Dict[str, float]] = {
    "happy": {
        "うれしい": 1.8,
        "嬉しい": 1.8,
        "楽しい": 1.8,
        "たのしい": 1.8,
        "最高": 1.7,
        "よかった": 1.1,
        "助かった": 1.1,
        "安心": 1.0,
        "好き": 1.0,
        "楽しみ": 1.2,
        "happy": 1.5,
        "great": 1.2,
        "glad": 1.2,
    },
    "sad": {
        "悲しい": 2.0,
        "つらい": 1.8,
        "辛い": 1.8,
        "しんどい": 1.8,
        "疲れた": 1.4,
        "寂しい": 1.7,
        "落ち込": 1.6,
        "不安": 1.4,
        "こわい": 1.1,
        "怖い": 1.1,
        "sad": 1.6,
        "tired": 1.3,
        "lonely": 1.6,
    },
    "angry": {
        "むかつく": 2.0,
        "ムカつく": 2.0,
        "腹立つ": 2.0,
        "腹が立つ": 2.0,
        "イライラ": 1.8,
        "最悪": 1.3,
        "納得いか": 1.6,
        "怒": 1.5,
        "frustrated": 1.8,
        "angry": 1.8,
        "annoyed": 1.5,
    },
    "surprised": {
        "びっくり": 1.8,
        "驚": 1.8,
        "まさか": 1.4,
        "えっ": 1.1,
        "unexpected": 1.4,
        "wow": 1.1,
        "shocked": 1.4,
    },
}

INTENSIFIERS = ("すごく", "かなり", "めっちゃ", "本当に", "とても", "超", "ほんとに")


class EmotionAnalyzer:
    """Heuristic emotion analysis with a stable local fallback."""

    def __init__(self, client: Optional[OpenAI] = None):
        load_dotenv()
        self.client: Optional[OpenAI] = client

    def set_client(self, client: Optional[OpenAI]):
        """Keep API parity with the previous implementation."""
        self.client = client

    def analyze_emotion(self, text: str) -> Dict:
        """Return structured emotion data without relying on remote calls."""
        normalised = _normalise_text(text)
        if not normalised:
            return self._get_default_emotion()

        scores: Dict[str, float] = {}
        matched_keywords: Dict[str, List[str]] = {}
        for emotion, keywords in EMOTION_KEYWORDS.items():
            matches = [keyword for keyword in keywords if keyword.lower() in normalised]
            matched_keywords[emotion] = matches
            scores[emotion] = sum(keywords[keyword] for keyword in matches)

        primary_emotions = self._rank_emotions(scores)
        if not primary_emotions:
            return self._get_default_emotion()

        primary = primary_emotions[0]
        best_score = scores.get(primary, 0.0)
        intensity = 0.45 + min(best_score / 5.0, 0.4)
        if any(intensifier in normalised for intensifier in INTENSIFIERS):
            intensity += 0.1
        if "!" in text or "！" in text:
            intensity += 0.05
        intensity = max(0.0, min(1.0, intensity))

        emotion_combination = " / ".join(primary_emotions[:2]) if len(primary_emotions) > 1 else primary
        emotion_change = "揺れあり" if len(primary_emotions) > 1 and self._has_contrast(text) else "なし"
        keywords = matched_keywords.get(primary, [])
        confidence = min(0.95, 0.4 + best_score / 4.0)

        return {
            "primary_emotions": primary_emotions,
            "intensity": intensity,
            "emotion_combination": emotion_combination,
            "emotion_change": emotion_change,
            "reason": f"検出キーワード: {', '.join(keywords[:3])}" if keywords else "明確なキーワードなし",
            "confidence": confidence,
        }

    def _rank_emotions(self, scores: Dict[str, float]) -> List[str]:
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        if not ordered or ordered[0][1] <= 0.0:
            return ["neutral"]

        primary_emotions = [ordered[0][0]]
        if len(ordered) > 1 and ordered[1][1] >= max(ordered[0][1] * 0.6, 1.0):
            primary_emotions.append(ordered[1][0])
        return primary_emotions

    def _has_contrast(self, text: str) -> bool:
        normalised = _normalise_text(text)
        return any(marker in normalised for marker in ("でも", "けど", "なのに", "一方で"))

    def _get_default_emotion(self) -> Dict:
        return {
            "primary_emotions": ["neutral"],
            "intensity": 0.5,
            "emotion_combination": "neutral",
            "emotion_change": "なし",
            "reason": "感情は中立寄り",
            "confidence": 0.2,
        }

    def get_emotion_expression(self, emotion_data: Dict) -> str:
        """Return an expression string that the VTuber model can interpret."""
        primary = "neutral"
        raw_primary = emotion_data.get("primary_emotions") if isinstance(emotion_data, dict) else None
        if isinstance(raw_primary, list) and raw_primary:
            candidate = raw_primary[0]
            if isinstance(candidate, str):
                primary = candidate.lower()

        if primary == "happy":
            return "笑顔で明るい声"
        if primary == "sad":
            return "悲しい表情で少し低い声"
        if primary == "angry":
            return "怒りをにじませた表情でやや強い声"
        if primary == "surprised":
            return "驚きの表情で少し高い声"
        return "通常の表情で落ち着いた声"

    def get_emotion_history(self, text_history: List[str]) -> List[Dict]:
        return [self.analyze_emotion(text) for text in text_history]


def _normalise_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").lower()
