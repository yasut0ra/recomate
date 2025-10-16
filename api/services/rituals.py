"""Ritual service helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import yaml
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..db.models import Ritual

logger = logging.getLogger(__name__)
RITUAL_EVENTS: Dict[str, Dict[str, List[Dict[str, str]]]] = {
    "morning": {
        "穏やか": [
            {"event": "face", "value": "smile_soft"},
            {"event": "eye", "value": "blink_normal"},
            {"event": "mouth", "value": "a_i_u"},
        ],
        "陽気": [
            {"event": "face", "value": "smile_big"},
            {"event": "eye", "value": "wink"},
            {"event": "mouth", "value": "open_wide"},
        ],
        "哲学": [
            {"event": "face", "value": "think"},
            {"event": "eye", "value": "up_left"},
            {"event": "mouth", "value": "hmm"},
        ],
    },
    "night": {
        "穏やか": [
            {"event": "face", "value": "smile_soft"},
            {"event": "eye", "value": "half"},
            {"event": "mouth", "value": "small"},
        ],
        "ツン": [
            {"event": "face", "value": "neutral_tsun"},
            {"event": "eye", "value": "blink_fast"},
            {"event": "mouth", "value": "small"},
        ],
        "心配": [
            {"event": "face", "value": "worry"},
            {"event": "eye", "value": "down_right"},
            {"event": "mouth", "value": "hmm"},
        ],
    },
}

DEFAULT_MORNING_SCRIPTS: Dict[str, str] = {
    "穏やか": "おはよう。水一杯から始めよっか。今日の一歩は？",
    "陽気": "おはよー！昨日の続き、光ってたよ。5分だけ振り返ろ？",
    "哲学": "今日のテーマは『小さい選択が未来を折る』。ひとつだけ選ぼう。",
}

DEFAULT_NIGHT_SCRIPTS: Dict[str, str] = {
    "穏やか": "3行だけ今日を貸して。私が要約するね。",
    "ツン": "未完は明日の証拠。歯磨き→整頓→おやすみ。",
    "心配": "眠り浅そう？予定を柔らかく組み直そう。",
}


@dataclass
class RitualPlan:
    """Resolved ritual script with animation cues."""

    period: str
    mood: str
    script: str
    events: List[Dict[str, str]]
    source: str  # "default" or "custom"


def _extract_script_mapping(raw_yaml: Optional[str]) -> Dict[str, str]:
    if not raw_yaml:
        return {}
    try:
        parsed = yaml.safe_load(raw_yaml)
    except yaml.YAMLError:
        return {}

    def flatten(value: object) -> Dict[str, str]:
        if isinstance(value, dict):
            result: Dict[str, str] = {}
            for key, item in value.items():
                if isinstance(item, str):
                    result[str(key)] = item
                elif isinstance(item, dict):
                    # flatten nested dictionaries (e.g., {"morning": {"穏やか": "..."} })
                    for inner_key, inner_val in flatten(item).items():
                        result[str(inner_key)] = inner_val
            return result
        return {}

    return flatten(parsed)


def _resolve_script(
    default_scripts: Dict[str, str], overrides: Dict[str, str], mood: str
) -> Tuple[str, str]:
    combined = {**default_scripts}
    combined.update(overrides)
    if mood in combined:
        return mood, combined[mood]
    if combined:
        fallback_mood, script = next(iter(combined.items()))
        return fallback_mood, script
    # fallback to provided mood even if no scripts exist
    return mood, ""


def _resolve_events(period: str, mood: str) -> List[Dict[str, str]]:
    period_events = RITUAL_EVENTS.get(period, {})
    if mood in period_events:
        return period_events[mood]
    default_events = period_events.get("穏やか") or next(iter(period_events.values()), [])
    return default_events


def _fetch_ritual(session: Session, user_id: Optional[UUID]) -> Optional[Ritual]:
    if not user_id:
        return None
    try:
        return session.get(Ritual, user_id)
    except SQLAlchemyError as exc:
        logger.debug("Failed to fetch ritual for user %s: %s", user_id, exc)
        return None


def get_morning_ritual(session: Session, mood: str, user_id: Optional[UUID]) -> RitualPlan:
    record = _fetch_ritual(session, user_id)
    overrides = _extract_script_mapping(record.morning_yaml) if record else {}
    resolved_mood, script = _resolve_script(DEFAULT_MORNING_SCRIPTS, overrides, mood)
    events = _resolve_events("morning", resolved_mood)
    source = "custom" if overrides else "default"
    return RitualPlan(period="morning", mood=resolved_mood, script=script, events=events, source=source)


def get_night_ritual(session: Session, mood: str, user_id: Optional[UUID]) -> RitualPlan:
    record = _fetch_ritual(session, user_id)
    overrides = _extract_script_mapping(record.night_yaml) if record else {}
    resolved_mood, script = _resolve_script(DEFAULT_NIGHT_SCRIPTS, overrides, mood)
    events = _resolve_events("night", resolved_mood)
    source = "custom" if overrides else "default"
    return RitualPlan(period="night", mood=resolved_mood, script=script, events=events, source=source)
