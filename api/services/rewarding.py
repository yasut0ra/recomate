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

# Signals in the user's *next* message about how the previous reply landed.
DISMISSAL_MARKERS = (
    "別の話",
    "話変え",
    "話を変え",
    "もういい",
    "どうでもいい",
    "つまらな",
    "興味ない",
    "そういうことじゃな",
    "そうじゃなくて",
    "違うって",
    "聞いてない",
)
ENGAGED_MARKERS = (
    "そうそう",
    "わかる",
    "分かる",
    "たしかに",
    "確かに",
    "それな",
    "なるほど",
    "ありがとう",
    "その続き",
    "それで",
    "そのあと",
    "ちなみに",
)
MINIMAL_REPLIES = {"うん", "へー", "へえ", "ふーん", "そう", "はい", "そっか", "ok", "了解", "りょ"}
_MINIMAL_TRAILING = "。.!！?？〜~ーｗw…"

# How much of a turn's learned reward comes from the user's reaction versus
# the self-assessed reply quality.
ENGAGEMENT_WEIGHT = 0.65


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


def calculate_engagement_reward(
    *,
    next_user_text: str,
    previous_user_emotion: Optional[Dict[str, Any]] = None,
    next_user_emotion: Optional[Dict[str, Any]] = None,
) -> float:
    """Estimate 0..1 from how the user reacted to the previous reply.

    This is the signal the topic bandit should really optimise: whether the
    user kept talking, pushed back, or felt better afterwards.
    """

    text = _normalise_text(next_user_text).strip()
    if not text:
        return 0.3

    reward = 0.5
    if any(marker in text for marker in DISMISSAL_MARKERS):
        reward -= 0.35
    if any(marker in text for marker in ENGAGED_MARKERS):
        reward += 0.2

    core = text.rstrip(_MINIMAL_TRAILING)
    if core in MINIMAL_REPLIES or len(core) <= 2:
        reward -= 0.15
    elif len(text) >= 20:
        reward += 0.1

    previous_label = _extract_primary_emotion(previous_user_emotion)
    next_label = _extract_primary_emotion(next_user_emotion)
    if previous_label in NEGATIVE_EMOTIONS and next_label not in NEGATIVE_EMOTIONS:
        reward += 0.1
    elif previous_label not in NEGATIVE_EMOTIONS and next_label in NEGATIVE_EMOTIONS:
        reward -= 0.1
    elif next_label in POSITIVE_EMOTIONS:
        reward += 0.05

    return round(max(0.0, min(1.0, reward)), 3)


def blend_turn_reward(response_reward: float, engagement_reward: float) -> float:
    """Combine reply quality and user reaction into one bandit reward."""
    blended = (1.0 - ENGAGEMENT_WEIGHT) * response_reward + ENGAGEMENT_WEIGHT * engagement_reward
    return round(max(0.0, min(1.0, blended)), 3)


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
