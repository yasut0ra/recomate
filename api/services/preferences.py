"""Preference profile helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict
from uuid import UUID

from sqlalchemy.orm import Session

from ..db.models import Preference

DEFAULT_STYLE_NOTES: Dict[str, Any] = {
    "length_bias": 0.0,
    "metaphor_bias": 0.0,
    "formality_bias": 0.0,
    "feedback_count": 0,
}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def ensure_preference(session: Session, user_id: UUID) -> Preference:
    record = session.get(Preference, user_id)
    if record is None:
        record = Preference(user_id=user_id)
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def _normalise_style_notes(style_notes: Dict[str, Any] | None) -> Dict[str, Any]:
    normalised = deepcopy(DEFAULT_STYLE_NOTES)
    for key, value in (style_notes or {}).items():
        normalised[key] = value
    return normalised


def describe_preference_profile(record: Preference) -> Dict[str, Any]:
    """Convert a preference row into a prompt-friendly profile."""
    style_notes = _normalise_style_notes(record.style_notes)
    length_bias = float(style_notes.get("length_bias", 0.0) or 0.0)
    metaphor_bias = float(style_notes.get("metaphor_bias", 0.0) or 0.0)
    formality_bias = float(style_notes.get("formality_bias", 0.0) or 0.0)

    if record.tone >= 0.78:
        tone_style = "親密でやわらかい"
    elif record.tone <= 0.35:
        tone_style = "落ち着いて控えめ"
    else:
        tone_style = "親しみやすく自然体"

    if record.humor >= 0.7:
        humor_style = "軽いユーモアを混ぜてもよい"
    elif record.humor <= 0.3:
        humor_style = "冗談は控えめにする"
    else:
        humor_style = "必要なときだけ軽くユーモアを混ぜる"

    if length_bias >= 0.35:
        length_style = "やや説明を厚めにしてよい"
    elif length_bias <= -0.35:
        length_style = "かなりコンパクトに返す"
    else:
        length_style = "短く収める"

    if metaphor_bias >= 0.35:
        metaphor_style = "比喩を少し使ってよい"
    elif metaphor_bias <= -0.35:
        metaphor_style = "比喩はほぼ使わない"
    else:
        metaphor_style = "比喩は必要なときだけ軽く使う"

    if formality_bias >= 0.35:
        formality_style = "少し丁寧寄り"
    elif formality_bias <= -0.35:
        formality_style = "かなり砕けた口調"
    else:
        formality_style = "フラットで自然な口調"

    return {
        "tone": float(record.tone),
        "humor": float(record.humor),
        "tts_voice": record.tts_voice,
        "style_notes": style_notes,
        "style_summary": {
            "tone_style": tone_style,
            "humor_style": humor_style,
            "length_style": length_style,
            "metaphor_style": metaphor_style,
            "formality_style": formality_style,
        },
    }


def get_preference_profile(session: Session, user_id: UUID) -> Dict[str, Any]:
    """Return a stable prompt-friendly preference profile."""
    record = ensure_preference(session, user_id)
    return describe_preference_profile(record)


def _apply_feedback_snapshot(
    profile: Dict[str, Any],
    *,
    like: bool | None = None,
    tone_delta: float = 0.0,
    length_delta: float = 0.0,
    metaphor_delta: float = 0.0,
) -> Dict[str, Any]:
    updated = deepcopy(profile)
    updated["tone"] = _clamp(float(updated.get("tone", 0.6)) + tone_delta, 0.0, 1.0)

    humor_adjustment = 0.06 if like is True else -0.04 if like is False else 0.0
    updated["humor"] = _clamp(float(updated.get("humor", 0.5)) + humor_adjustment, 0.0, 1.0)

    style_notes = _normalise_style_notes(updated.get("style_notes"))
    style_notes["length_bias"] = _clamp(float(style_notes.get("length_bias", 0.0)) + length_delta, -1.0, 1.0)
    style_notes["metaphor_bias"] = _clamp(float(style_notes.get("metaphor_bias", 0.0)) + metaphor_delta, -1.0, 1.0)
    style_notes["feedback_count"] = int(style_notes.get("feedback_count", 0) or 0) + 1
    updated["style_notes"] = style_notes
    return updated


def apply_preference_feedback(
    session: Session,
    user_id: UUID,
    *,
    like: bool | None = None,
    tone_delta: float = 0.0,
    length_delta: float = 0.0,
    metaphor_delta: float = 0.0,
) -> Preference:
    """Apply lightweight style feedback to a user's preference profile."""
    record = ensure_preference(session, user_id)
    snapshot = describe_preference_profile(record)
    updated = _apply_feedback_snapshot(
        snapshot,
        like=like,
        tone_delta=tone_delta,
        length_delta=length_delta,
        metaphor_delta=metaphor_delta,
    )

    record.tone = float(updated["tone"])
    record.humor = float(updated["humor"])
    record.style_notes = updated["style_notes"]
    session.add(record)
    session.commit()
    session.refresh(record)
    return record
