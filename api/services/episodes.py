"""Conversation episode persistence helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ..db.models import Episode


def compose_episode_text(user_text: str, assistant_text: str) -> str:
    """Create a stable raw-log transcript for a single turn."""
    user_line = (user_text or "").strip()
    assistant_line = (assistant_text or "").strip()
    return f"User: {user_line}\nRecoMate: {assistant_line}".strip()


def build_episode_tags(
    *,
    topic_family: Optional[str] = None,
    emotion_label: Optional[str] = None,
    mood_state: Optional[str] = None,
    extra_tags: Optional[Iterable[str]] = None,
) -> List[str]:
    """Build a compact tag list for a persisted episode."""
    tags: List[str] = []
    if topic_family:
        tags.append(f"topic:{topic_family}")
    if emotion_label:
        tags.append(f"emotion:{emotion_label}")
    if mood_state:
        tags.append(f"mood:{mood_state}")
    for tag in extra_tags or []:
        cleaned = str(tag).strip()
        if cleaned and cleaned not in tags:
            tags.append(cleaned)
    return tags[:8]


def record_episode(
    session: Session,
    *,
    user_id: UUID,
    user_text: str,
    assistant_text: str,
    mood_user: Optional[str] = None,
    mood_ai: Optional[str] = None,
    tags: Optional[Iterable[str]] = None,
) -> Episode:
    """Persist one chat turn as an episode row."""
    episode = Episode(
        user_id=user_id,
        ts=datetime.now(timezone.utc),
        text=compose_episode_text(user_text, assistant_text),
        mood_user=mood_user,
        mood_ai=mood_ai,
        tags=list(tags or []),
    )
    session.add(episode)
    session.commit()
    session.refresh(episode)
    return episode
