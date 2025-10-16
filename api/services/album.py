"""Weekly album generation helpers."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from ..db.models import AlbumWeekly, Episode

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[A-Za-z0-9ぁ-んァ-ヶ一-龯ー']+")


def _extract_keywords(text: str, limit: int = 6) -> List[str]:
    candidates = _WORD_RE.findall(text.lower())
    seen: Dict[str, int] = {}
    for word in candidates:
        if len(word) < 2:
            continue
        seen[word] = seen.get(word, 0) + 1
    ranked = sorted(seen.items(), key=lambda item: item[1], reverse=True)
    return [word for word, _ in ranked[:limit]]


def _resolve_reference_datetime(week_id: Optional[str]) -> Tuple[str, datetime, datetime]:
    if week_id:
        try:
            year_part, week_part = week_id.split("-W")
            reference = datetime.fromisocalendar(int(year_part), int(week_part), 1).replace(tzinfo=timezone.utc)
            resolved_week_id = week_id
        except Exception as exc:  # noqa: BLE001
            raise ValueError("Invalid week_id format. Expected YYYY-Www.") from exc
    else:
        now = datetime.now(timezone.utc)
        iso = now.isocalendar()
        resolved_week_id = f"{iso.year}-W{iso.week:02d}"
        reference = datetime.fromisocalendar(iso.year, iso.week, 1).replace(tzinfo=timezone.utc)
    week_end = reference + timedelta(days=7)
    return resolved_week_id, reference, week_end


def _summarise_episodes(episodes: List[Episode]) -> Tuple[Dict[str, object], Dict[str, object], Dict[str, object], Optional[str]]:
    if not episodes:
        empty = {"count": 0, "entries": []}
        return empty, empty, {}, None

    texts = [ep.text.strip() for ep in episodes if ep.text.strip()]
    top_entries = texts[:3]

    keywords = _extract_keywords(" ".join(texts))

    highlights = {
        "count": len(texts),
        "entries": top_entries,
    }
    wins = {
        "keywords": keywords,
        "first_entry": texts[0] if texts else None,
        "last_entry": texts[-1] if texts else None,
    }
    photos = {"sources": []}
    quote_best = top_entries[0] if top_entries else None
    return highlights, wins, photos, quote_best


def generate_weekly_album(
    session: Session,
    user_id: UUID,
    week_id: Optional[str] = None,
    regenerate: bool = False,
) -> AlbumWeekly:
    resolved_week_id, week_start, week_end = _resolve_reference_datetime(week_id)

    existing = session.get(AlbumWeekly, (resolved_week_id, user_id))
    if existing and not regenerate:
        return existing

    stmt = (
        sa.select(Episode)
        .where(
            Episode.user_id == user_id,
            Episode.ts >= week_start,
            Episode.ts < week_end,
        )
        .order_by(Episode.ts.asc())
    )
    episodes = session.execute(stmt).scalars().all()

    highlights, wins, photos, quote_best = _summarise_episodes(episodes)

    if existing:
        record = existing
    else:
        record = AlbumWeekly(week_id=resolved_week_id, user_id=user_id)

    record.highlights_json = highlights
    record.wins_json = wins
    record.photos = photos
    record.quote_best = quote_best

    session.add(record)
    session.commit()
    session.refresh(record)

    logger.debug(
        "Generated weekly album for user %s week %s with %s entries",
        user_id,
        resolved_week_id,
        highlights.get("count"),
    )

    return record
