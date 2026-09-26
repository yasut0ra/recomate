"""LLM-backed emotion and reaction analysis with a keyword fallback.

One small-model call per user turn classifies the user's emotion and, when a
previous reply is still awaiting feedback, how the user reacted to it. The
output keeps the keyword analyzer's payload shape so the planner, reward
scoring, bandit features, and UI need no changes. Any failure (no client,
timeout, malformed JSON) degrades to the local keyword heuristics.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .emotion_analyzer import EmotionAnalyzer
from .services.rewarding import calculate_engagement_reward

logger = logging.getLogger(__name__)

# Kept identical to the keyword analyzer / bandit one-hot labels.
EMOTION_LABELS = ("happy", "sad", "angry", "surprised", "neutral")
REACTION_LABELS = ("engaged", "neutral", "dismissive")

DEFAULT_ANALYSIS_MODEL = "gpt-4.1-nano"
ANALYSIS_TIMEOUT_SECONDS = 8.0
LLM_CONFIDENCE = 0.8

ANALYSIS_SYSTEM_PROMPT = (
    "You analyse messages in a Japanese companion chat app. Reply only with JSON matching the schema.\n"
    "Emotion: classify the feeling the speaker is expressing right now, not the topics they mention.\n"
    "- happy: joy, relief, excitement, gratitude, fun\n"
    "- sad: sadness, loneliness, fatigue, anxiety, fear, discouragement\n"
    "- angry: anger, frustration, irritation, resentment\n"
    "- surprised: shock or astonishment (good or bad)\n"
    "- neutral: no clear feeling, plain facts, greetings\n"
    "Handle negation (「別に悲しくない」), sarcasm, understatement, and mixed feelings: put the dominant "
    "feeling in `emotion` and a clearly present second one in `secondary_emotion`, else null. "
    "`intensity` is 0.0 (barely) to 1.0 (overwhelming). `reason` is a short Japanese phrase."
)

REACTION_INSTRUCTIONS = (
    "\nReaction: judge how the user's new message responds to the assistant's previous reply.\n"
    "- engaged: continues or elaborates, agrees, thanks, opens up more, asks a follow-up\n"
    "- neutral: brief acknowledgement, or a calm change of subject\n"
    "- dismissive: rejects the reply, says it missed the point, sounds let down or annoyed, "
    "asks to stop or change the subject because of the reply\n"
    "`score` is 0.0 (clearly a bad reaction) to 1.0 (clearly a good one); 0.5 is neutral. "
    "A new topic alone is not dismissive."
)


def _emotion_schema(include_reaction: bool) -> Dict[str, Any]:
    properties: Dict[str, Any] = {
        "emotion": {"type": "string", "enum": list(EMOTION_LABELS)},
        "secondary_emotion": {"type": ["string", "null"], "enum": [*EMOTION_LABELS, None]},
        "intensity": {"type": "number"},
        "reason": {"type": "string"},
    }
    if include_reaction:
        properties["reaction"] = {
            "type": "object",
            "additionalProperties": False,
            "required": ["label", "score", "reason"],
            "properties": {
                "label": {"type": "string", "enum": list(REACTION_LABELS)},
                "score": {"type": "number"},
                "reason": {"type": "string"},
            },
        }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties.keys()),
        "properties": properties,
    }


def _clamp01(value: Any, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return max(0.0, min(1.0, float(value)))


def expression_payload(label: str) -> Dict[str, Any]:
    """Emotion payload for an expression the reply generator chose itself."""
    return {
        "primary_emotions": [label],
        "intensity": 0.5,
        "emotion_combination": label,
        "emotion_change": "なし",
        "reason": "返答生成時に指定された表情",
        "confidence": LLM_CONFIDENCE,
        "source": "llm",
    }


@dataclass
class TurnAnalysis:
    """Emotion for the current message plus, optionally, a reaction score."""

    emotion: Dict[str, Any]
    reaction_score: Optional[float] = None
    reaction: Optional[Dict[str, Any]] = None


class TurnAnalyzer:
    def __init__(self, keyword_analyzer: Optional[EmotionAnalyzer] = None) -> None:
        self.keyword_analyzer = keyword_analyzer or EmotionAnalyzer()
        mode = (os.getenv("RECOMATE_EMOTION_ANALYZER") or "llm").strip().lower()
        self.llm_enabled = mode != "keyword"
        self.model = (os.getenv("OPENAI_ANALYSIS_MODEL") or "").strip() or DEFAULT_ANALYSIS_MODEL

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def analyze_text(self, client: Any, text: str) -> Dict[str, Any]:
        """Emotion payload for a single message."""
        return self.analyze_turn(client, user_text=text).emotion

    def analyze_turn(
        self,
        client: Any,
        *,
        user_text: str,
        previous_user_text: Optional[str] = None,
        previous_reply: Optional[str] = None,
    ) -> TurnAnalysis:
        """Classify ``user_text``; judge the reaction when a previous reply is given."""
        include_reaction = bool(previous_reply)
        if client is not None and self.llm_enabled and (user_text or "").strip():
            parsed = self._call_llm(client, user_text, previous_user_text, previous_reply, include_reaction)
            if parsed is not None:
                return parsed

        emotion = dict(self.keyword_analyzer.analyze_emotion(user_text), source="keyword")
        reaction_score = None
        if include_reaction:
            previous_emotion = (
                self.keyword_analyzer.analyze_emotion(previous_user_text) if previous_user_text else None
            )
            reaction_score = calculate_engagement_reward(
                next_user_text=user_text,
                previous_user_emotion=previous_emotion,
                next_user_emotion=emotion,
            )
        return TurnAnalysis(emotion=emotion, reaction_score=reaction_score)

    # ------------------------------------------------------------------
    # LLM path
    # ------------------------------------------------------------------
    def _call_llm(
        self,
        client: Any,
        user_text: str,
        previous_user_text: Optional[str],
        previous_reply: Optional[str],
        include_reaction: bool,
    ) -> Optional[TurnAnalysis]:
        system_prompt = ANALYSIS_SYSTEM_PROMPT + (REACTION_INSTRUCTIONS if include_reaction else "")
        payload: Dict[str, Any] = {"user_message": user_text}
        if include_reaction:
            payload = {
                "previous_user_message": previous_user_text or "",
                "previous_assistant_reply": previous_reply,
                "user_message": user_text,
            }
        try:
            completion = client.with_options(timeout=ANALYSIS_TIMEOUT_SECONDS, max_retries=0).chat.completions.create(
                model=self.model,
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "turn_analysis",
                        "strict": True,
                        "schema": _emotion_schema(include_reaction),
                    },
                },
            )
            content = completion.choices[0].message.content or ""
            return self._parse(json.loads(content), include_reaction)
        except Exception as exc:
            logger.warning("LLM emotion analysis failed on %s; using keyword fallback: %s", self.model, exc)
            return None

    def _parse(self, data: Any, include_reaction: bool) -> Optional[TurnAnalysis]:
        if not isinstance(data, dict):
            raise ValueError("analysis output is not an object")
        primary = data.get("emotion")
        if primary not in EMOTION_LABELS:
            raise ValueError(f"unknown emotion label: {primary!r}")
        secondary = data.get("secondary_emotion")
        primary_emotions = [primary]
        if secondary in EMOTION_LABELS and secondary != primary and secondary != "neutral":
            primary_emotions.append(secondary)

        reason = str(data.get("reason") or "").strip()
        emotion = {
            "primary_emotions": primary_emotions,
            "intensity": _clamp01(data.get("intensity"), 0.5),
            "emotion_combination": " / ".join(primary_emotions),
            "emotion_change": "揺れあり" if len(primary_emotions) > 1 else "なし",
            "reason": reason or "LLMによる判定",
            "confidence": LLM_CONFIDENCE,
            "source": "llm",
        }

        reaction_score = None
        reaction = None
        if include_reaction:
            raw = data.get("reaction")
            if not isinstance(raw, dict) or raw.get("label") not in REACTION_LABELS:
                raise ValueError("missing or invalid reaction")
            reaction_score = round(_clamp01(raw.get("score"), 0.5), 3)
            reaction = {
                "label": raw["label"],
                "score": reaction_score,
                "reason": str(raw.get("reason") or "").strip(),
            }
        return TurnAnalysis(emotion=emotion, reaction_score=reaction_score, reaction=reaction)
