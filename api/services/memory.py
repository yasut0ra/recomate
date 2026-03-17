"""Memory creation and retrieval helpers."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from ..db.models import Episode, Memory
from .episodes import parse_episode_text

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[A-Za-z0-9ぁ-んァ-ヶ一-龯ー']+")
_MEMORY_STOPWORDS = {"user", "recomate", "assistant", "ユーザー", "相棒", "会話", "こと", "もの"}
_AUTO_MEMORY_TOPICS = {"仕事・学び", "人間関係", "趣味・好きなもの", "体調・生活リズム", "悩み・気持ち整理", "将来・目標"}
_AUTO_MEMORY_SIGNALS = (
    "好き",
    "苦手",
    "大事",
    "大切",
    "誕生日",
    "家族",
    "友達",
    "恋人",
    "彼氏",
    "彼女",
    "上司",
    "同僚",
    "学校",
    "仕事",
    "進路",
    "引っ越し",
    "病院",
    "通院",
    "相談",
    "不安",
    "つらい",
    "辛い",
    "映画",
    "音楽",
    "旅行",
    "推し",
)


def _extract_memory_source_text(text: str) -> str:
    """Prefer the user-authored portion of a stored turn transcript."""
    parsed = parse_episode_text(text)
    user_text = parsed.get("user_text", "").strip()
    if user_text:
        return user_text
    assistant_text = parsed.get("assistant_text", "").strip()
    if assistant_text:
        return assistant_text
    return " ".join(line.strip() for line in (text or "").splitlines() if line.strip()).strip()


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
        if word in _MEMORY_STOPWORDS:
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

    source_text = _extract_memory_source_text(episode.text)
    summary = (summary_override or "").strip() or _generate_summary(source_text)
    keywords_list = list(keywords_override or []) or _extract_keywords(source_text)

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


def _memory_relevance_score(memory: Memory, query_terms: List[str], query_text: str) -> float:
    score = 2.0 if bool(memory.pinned) else 0.0
    summary = (memory.summary_md or "").lower()
    keywords = [str(keyword).lower() for keyword in (memory.keywords or [])]

    if query_text:
        if query_text in summary:
            score += 3.0
        if any(query_text in keyword for keyword in keywords):
            score += 2.0

    for term in query_terms:
        if term in summary:
            score += 1.2
        if any(term in keyword for keyword in keywords):
            score += 1.4

    return score


def _looks_like_duplicate_memory(existing_memories: List[Memory], summary: str, keywords: List[str]) -> bool:
    candidate_summary = summary.strip().lower()
    candidate_keywords = set(keyword.lower() for keyword in keywords if keyword)
    for memory in existing_memories:
        existing_summary = (memory.summary_md or "").strip().lower()
        existing_keywords = set(str(keyword).lower() for keyword in (memory.keywords or []))
        if candidate_summary and candidate_summary == existing_summary:
            return True
        if candidate_summary and existing_summary and candidate_summary[:48] == existing_summary[:48]:
            return True
        if candidate_keywords and len(candidate_keywords & existing_keywords) >= 3:
            return True
    return False


def should_promote_episode_to_memory(
    text: str,
    *,
    topic_family: Optional[str],
    emotion_payload: Optional[Dict[str, object]] = None,
) -> bool:
    """Heuristic gate for automatic memory creation."""
    source_text = _extract_memory_source_text(text)
    if len(source_text.strip()) < 12:
        return False

    keywords = _extract_keywords(source_text, limit=8)
    intensity = 0.5
    if isinstance(emotion_payload, dict):
        raw_intensity = emotion_payload.get("intensity")
        if isinstance(raw_intensity, (float, int)):
            intensity = max(0.0, min(1.0, float(raw_intensity)))

    if intensity >= 0.82:
        return True
    if any(signal in source_text for signal in _AUTO_MEMORY_SIGNALS):
        return True
    if topic_family in _AUTO_MEMORY_TOPICS and len(keywords) >= 3 and len(source_text) >= 22:
        return True
    if topic_family == "軽い雑談":
        return False
    return len(keywords) >= 4 and len(source_text) >= 30


def select_relevant_memories(memories: List[Memory], query: Optional[str], limit: int = 3) -> List[Memory]:
    """Rank memory rows for use inside the conversation prompt."""
    if not memories:
        return []

    query_text = (query or "").strip().lower()
    query_terms = _extract_keywords(query_text, limit=6) if query_text else []
    ranked = sorted(
        memories,
        key=lambda memory: (
            _memory_relevance_score(memory, query_terms, query_text),
            1 if bool(memory.pinned) else 0,
            memory.last_ref or memory.created_at,
            memory.created_at,
        ),
        reverse=True,
    )

    if query_text:
        positive = [memory for memory in ranked if _memory_relevance_score(memory, query_terms, query_text) > 0.0]
        if positive:
            return positive[:limit]

    return ranked[:limit]


def build_memory_context(session: Session, user_id: UUID, query: Optional[str], limit: int = 3) -> List[Dict[str, object]]:
    """Return small, prompt-safe memory snippets relevant to the current turn."""
    stmt = (
        sa.select(Memory)
        .where(Memory.user_id == user_id)
        .order_by(Memory.pinned.desc(), Memory.last_ref.desc().nullslast(), Memory.created_at.desc())
        .limit(max(limit * 8, 12))
    )
    memories = session.execute(stmt).scalars().all()
    selected = select_relevant_memories(memories, query=query, limit=limit)
    if not selected:
        return []

    now = datetime.now(timezone.utc)
    for memory in selected:
        memory.last_ref = now
        session.add(memory)
    session.commit()

    context: List[Dict[str, object]] = []
    for memory in selected:
        context.append(
            {
                "summary": memory.summary_md,
                "keywords": list(memory.keywords or [])[:5],
                "pinned": bool(memory.pinned),
                "created_at": memory.created_at.isoformat() if memory.created_at else None,
            }
        )
    return context


def promote_episode_to_memory_if_relevant(
    session: Session,
    episode: Episode,
    *,
    topic_family: Optional[str],
    emotion_payload: Optional[Dict[str, object]] = None,
    learning_paused: bool = False,
) -> Optional[Memory]:
    """Automatically create a memory for meaningful turns."""
    if learning_paused:
        return None
    if not should_promote_episode_to_memory(episode.text, topic_family=topic_family, emotion_payload=emotion_payload):
        return None

    source_text = _extract_memory_source_text(episode.text)
    summary = _generate_summary(source_text, max_length=160)
    keywords = _extract_keywords(source_text, limit=8)
    recent_memories = (
        session.execute(
            sa.select(Memory)
            .where(Memory.user_id == episode.user_id)
            .order_by(Memory.created_at.desc())
            .limit(8)
        )
        .scalars()
        .all()
    )
    if _looks_like_duplicate_memory(recent_memories, summary, keywords):
        return None

    memory = Memory(
        user_id=episode.user_id,
        summary_md=summary,
        keywords=keywords,
        last_ref=datetime.now(timezone.utc),
        pinned=False,
    )
    session.add(memory)
    session.commit()
    session.refresh(memory)
    return memory
