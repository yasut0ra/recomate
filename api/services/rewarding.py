"""Local-first heuristics for assistant turn reward scoring."""

from __future__ import annotations

from typing import Any, Dict, Optional
import unicodedata

NEGATIVE_EMOTIONS = {"sad", "angry", "fear", "disgust"}
POSITIVE_EMOTIONS = {"happy", "joy", "trust", "anticipation", "surprised"}

ADVICE_MARKERS = ("どうしたら", "どうすれば", "相談", "アドバイス", "助けて", "教えて")
EMPATHY_MARKERS = (
    "大丈夫",
    "無理",
    "しんど",
    "つら",
    "自然",
    "ありがとう",
    "受け止め",
    "そば",
    "力を抜",
)
POSITIVE_REPLY_MARKERS = (
    "うれしい",
    "よかった",
    "いい",
    "楽し",
    "明る",
    "にやけ",
    "最高",
)
COMPANION_MARKERS = ("一緒", "そば", "ゆっくり", "少し", "自然", "大丈夫")


def calculate_response_reward(
    *,
    user_text: str,
    response_text: str,
    user_emotion: Optional[Dict[str, Any]] = None,
    assistant_emotion: Optional[Dict[str, Any]] = None,
) -> float:
    """Estimate a stable 0..1 reward for a single assistant response."""

    response = (response_text or "").strip()
    if not response:
        return 0.0

    normalised_user = _normalise_text(user_text)
    normalised_response = _normalise_text(response)
    user_label = _extract_primary_emotion(user_emotion)
    assistant_label = _extract_primary_emotion(assistant_emotion)

    reward = 0.48
    response_length = len(response)
    question_count = response.count("?") + response.count("？")
    user_requests_help = (
        "?" in user_text
        or "？" in user_text
        or any(marker in normalised_user for marker in ADVICE_MARKERS)
    )
    ends_with_question = response.endswith("?") or response.endswith("？")

    if 16 <= response_length <= 120:
        reward += 0.12
    elif 8 <= response_length <= 160:
        reward += 0.05
    else:
        reward -= 0.08

    if question_count > 1:
        reward -= min(0.18, 0.08 * float(question_count - 1))
    elif question_count == 0 and not user_requests_help:
        reward += 0.05

    if ends_with_question and not user_requests_help:
        reward -= 0.08

    if user_label in NEGATIVE_EMOTIONS:
        if any(marker in normalised_response for marker in EMPATHY_MARKERS):
            reward += 0.16
        else:
            reward -= 0.05
        if assistant_label in {"sad", "neutral", "angry"}:
            reward += 0.06
    elif user_label in POSITIVE_EMOTIONS:
        if any(marker in normalised_response for marker in POSITIVE_REPLY_MARKERS):
            reward += 0.12
        if assistant_label in {"happy", "surprised"}:
            reward += 0.05
    elif any(marker in normalised_response for marker in COMPANION_MARKERS):
        reward += 0.04

    if response.count("\n") == 0:
        reward += 0.02

    return round(max(0.0, min(1.0, reward)), 3)


def _extract_primary_emotion(emotion_payload: Optional[Dict[str, Any]]) -> str:
    if not emotion_payload:
        return "neutral"
    primary = emotion_payload.get("primary_emotions")
    if isinstance(primary, list) and primary:
        candidate = primary[0]
        if isinstance(candidate, str) and candidate:
            return candidate.lower()
    raw = emotion_payload.get("emotion")
    if isinstance(raw, str) and raw:
        return raw.lower()
    return "neutral"


def _normalise_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").lower()
