"""Memory creation and retrieval helpers."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from ..db.models import Episode, Memory

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[A-Za-z0-9ぁ-んァ-ヶ一-龯ー']+")


def _generate_summary(text: str, max_length: int = 280) -> str:
    """Generate a simple markdown summary from an episode."""
    stripped = text.strip()
    if not stripped:
        return "_空のメッセージ_"
    if len(stripped) <= max_length:
        return stripped
    return stripped[: max_length - 1].rstrip() + "…"


def _extract_keywords(text: str, limit: int = 8) -> List[str]:
    """Extract simple keyword candidates from text."""
    candidates = _WORD_RE.findall(text.lower())
    seen: Dict[str, int] = {}
    for word in candidates:
        if len(word) < 2:
            continue
        seen[word] = seen.get(word, 0) + 1
    ranked = sorted(seen.items(), key=lambda item: item[1], reverse=True)
    return [word for word, _ in ranked[:limit]]


def commit_memory(
    session: Session,
    episode_id: UUID,
    summary_override: Optional[str] = None,
    keywords_override: Optional[Iterable[str]] = None,
    pinned: bool = False,
) -> Memory:
    """Persist a memory summarising the given episode."""
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise ValueError("Episode not found")

    summary = (summary_override or "").strip() or _generate_summary(episode.text)
    keywords_list = list(keywords_override or []) or _extract_keywords(episode.text)

    memory = Memory(
        user_id=episode.user_id,
        summary_md=summary,
        keywords=keywords_list,
        last_ref=datetime.now(timezone.utc),
        pinned=pinned,
    )
    session.add(memory)
    session.commit()
    session.refresh(memory)

    logger.debug("Committed memory %s for episode %s", memory.id, episode_id)
    return memory


def search_memories(
    session: Session,
    user_id: Optional[UUID],
    query: Optional[str],
    limit: int = 20,
) -> List[Memory]:
    """Search memories by user and free text query."""
    stmt = sa.select(Memory).order_by(Memory.created_at.desc()).limit(limit)
    if user_id:
        stmt = stmt.where(Memory.user_id == user_id)

    if query:
        pattern = f"%{query.strip()}%"
        stmt = stmt.where(
            sa.or_(
                Memory.summary_md.ilike(pattern),
                sa.func.array_to_string(Memory.keywords, " ").ilike(pattern),
            )
        )

    results = session.execute(stmt).scalars().all()
    return results

