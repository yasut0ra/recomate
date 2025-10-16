"""Mood state machine helpers."""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from typing import Dict, Tuple
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from ..db.models import AgentState, MoodLog

logger = logging.getLogger(__name__)

DEFAULT_STATE = "穏やか"

TRIGGERS = {
    "greet": "陽気",
    "success": "陽気",
    "relax": "穏やか",
    "concern": "心配",
    "tease": "ツン",
    "philosophy": "哲学",
    "mischief": "いたずら",
}

STATE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "穏やか": {"calm": 0.8, "cheer": 0.6},
    "陽気": {"calm": 0.6, "cheer": 0.9},
    "ツン": {"calm": 0.4, "cheer": 0.5},
    "いたずら": {"calm": 0.5, "cheer": 0.7},
    "哲学": {"calm": 0.7, "cheer": 0.5},
    "心配": {"calm": 0.3, "cheer": 0.2},
}

AVAILABLE_STATES = list(STATE_WEIGHTS.keys())


def _ensure_agent_state(session: Session, user_id: UUID) -> AgentState:
    state = session.get(AgentState, user_id)
    if state is None:
        state = AgentState(user_id=user_id)
        session.add(state)
        session.commit()
        session.refresh(state)
    return state


def _pick_state(trigger: str | None, previous: str) -> str:
    if trigger:
        mapped = TRIGGERS.get(trigger)
        if mapped:
            return mapped
    fallback_candidates = [s for s in AVAILABLE_STATES if s != previous]
    return random.choice(fallback_candidates) if fallback_candidates else previous


def transition_mood(session: Session, user_id: UUID, trigger: str | None = None) -> MoodLog:
    state_row = _ensure_agent_state(session, user_id)

    last_mood = (
        session.execute(
            sa.select(MoodLog).where(MoodLog.user_id == user_id).order_by(MoodLog.ts.desc())
        )
        .scalars()
        .first()
    )

    previous_state = last_mood.state if last_mood else DEFAULT_STATE
    new_state = _pick_state(trigger, previous_state)

    weights = STATE_WEIGHTS.get(new_state, {"calm": 0.5, "cheer": 0.5})

    # Update agent state heuristically
    state_row.curiosity = max(0.0, min(1.0, state_row.curiosity + random.uniform(-0.05, 0.1)))
    state_row.rest = max(0.0, min(1.0, state_row.rest + (0.1 if new_state == "穏やか" else -0.05)))
    state_row.orderliness = max(0.0, min(1.0, state_row.orderliness + random.uniform(-0.03, 0.05)))
    state_row.closeness = max(0.0, min(1.0, state_row.closeness + (0.08 if new_state in {"陽気", "心配"} else -0.02)))

    log_entry = MoodLog(
        user_id=user_id,
        ts=datetime.now(timezone.utc),
        state=new_state,
        trigger=trigger,
        weight_map_json=weights,
    )

    session.add(log_entry)
    session.add(state_row)
    session.commit()
    session.refresh(log_entry)

    logger.debug(
        "Mood transition for %s: %s -> %s via %s",
        user_id,
        previous_state,
        new_state,
        trigger,
    )

    return log_entry


def get_recent_moods(session: Session, user_id: UUID, limit: int = 10) -> Tuple[str, list[MoodLog]]:
    rows = (
        session.execute(
            sa.select(MoodLog)
            .where(MoodLog.user_id == user_id)
            .order_by(MoodLog.ts.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    current_state = rows[0].state if rows else DEFAULT_STATE
    return current_state, rows

