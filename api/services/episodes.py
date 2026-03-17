"""Conversation episode persistence helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Dict, Iterable, List, Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from ..db.models import Episode

_WORD_RE = re.compile(r"[A-Za-z0-9ぁ-んァ-ヶ一-龯ー']+")


def compose_episode_text(user_text: str, assistant_text: str) -> str:
    """Create a stable raw-log transcript for a single turn."""
    user_line = (user_text or "").strip()
    assistant_line = (assistant_text or "").strip()
    return f"User: {user_line}\nRecoMate: {assistant_line}".strip()


def parse_episode_text(text: str) -> Dict[str, str]:
    """Parse a stored transcript into user/assistant turns."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    user_parts: List[str] = []
    assistant_parts: List[str] = []
    other_parts: List[str] = []

    for line in lines:
        lowered = line.lower()
        if lowered.startswith("user:") or line.startswith("ユーザー:"):
            user_parts.append(line.split(":", 1)[1].strip())
        elif lowered.startswith("recomate:") or lowered.startswith("assistant:") or line.startswith("RecoMate:"):
            assistant_parts.append(line.split(":", 1)[1].strip())
        else:
            other_parts.append(line)

    user_text = " ".join(part for part in user_parts if part).strip()
    assistant_text = " ".join(part for part in assistant_parts if part).strip()
    if not user_text and other_parts:
        user_text = " ".join(other_parts).strip()

    return {
        "user_text": user_text,
        "assistant_text": assistant_text,
    }


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


def _extract_topic_from_tags(tags: Iterable[str] | None) -> Optional[str]:
    for tag in tags or []:
        if isinstance(tag, str) and tag.startswith("topic:"):
            return tag.split(":", 1)[1]
    return None


def _extract_query_terms(query: str) -> List[str]:
    seen: Dict[str, int] = {}
    for term in _WORD_RE.findall((query or "").lower()):
        if len(term) < 2:
            continue
        seen[term] = seen.get(term, 0) + 1
    ranked = sorted(seen.items(), key=lambda item: item[1], reverse=True)
    return [term for term, _ in ranked[:6]]


def _episode_context_score(episode: Episode, query_terms: List[str], query_text: str, recency_index: int) -> float:
    parts = parse_episode_text(episode.text)
    user_text = parts["user_text"].lower()
    assistant_text = parts["assistant_text"].lower()
    topic = (_extract_topic_from_tags(episode.tags) or "").lower()
    score = max(0.0, 1.6 - recency_index * 0.2)

    if query_text:
        if query_text in user_text:
            score += 2.2
        if query_text in assistant_text:
            score += 0.7
        if query_text in topic:
            score += 1.1

    for term in query_terms:
        if term in user_text:
            score += 1.0
        if term in assistant_text:
            score += 0.4
        if term in topic:
            score += 0.8

    return score


def select_recent_episode_context(episodes: List[Episode], query: str, limit: int = 3) -> List[Dict[str, object]]:
    """Choose recent episode snippets for short-term continuity."""
    if not episodes:
        return []

    query_text = (query or "").strip().lower()
    query_terms = _extract_query_terms(query_text)
    ranked: List[tuple[float, int, Episode]] = []
    for index, episode in enumerate(episodes):
        ranked.append((_episode_context_score(episode, query_terms, query_text, index), index, episode))

    selected = sorted(ranked, key=lambda item: (item[0], -item[1]), reverse=True)[:limit]
    ordered = [item[2] for item in sorted(selected, key=lambda item: item[2].ts)]

    context: List[Dict[str, object]] = []
    for episode in ordered:
        parts = parse_episode_text(episode.text)
        context.append(
            {
                "user_text": parts["user_text"],
                "assistant_text": parts["assistant_text"],
                "topic": _extract_topic_from_tags(episode.tags),
                "ts": episode.ts.isoformat() if episode.ts else None,
            }
        )
    return context


def build_recent_episode_context(
    session: Session,
    user_id: UUID,
    query: str,
    limit: int = 3,
    search_window: int = 8,
) -> List[Dict[str, object]]:
    """Return short-term recent conversation context from persisted episodes."""
    episodes = (
        session.execute(
            sa.select(Episode)
            .where(Episode.user_id == user_id)
            .order_by(Episode.ts.desc())
            .limit(max(search_window, limit))
        )
        .scalars()
        .all()
    )
    return select_recent_episode_context(episodes, query=query, limit=limit)


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
