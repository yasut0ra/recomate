"""Consent (boundary) service helpers."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ..db.models import ConsentSetting


def _ensure_setting(session: Session, user_id: UUID) -> ConsentSetting:
    record = session.get(ConsentSetting, user_id)
    if record is None:
        record = ConsentSetting(user_id=user_id)
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def get_consent_setting(session: Session, user_id: UUID) -> ConsentSetting:
    """Fetch existing consent settings, creating a default row if missing."""
    return _ensure_setting(session, user_id)


def update_consent_setting(session: Session, user_id: UUID, updates: Dict[str, Any]) -> ConsentSetting:
    """Apply partial updates to consent settings."""
    record = _ensure_setting(session, user_id)

    allowed_fields = {"night_mode", "push_intensity", "private_topics", "learning_paused"}
    changed = False
    for key, value in updates.items():
        if key in allowed_fields and value is not None:
            setattr(record, key, value)
            changed = True

    if changed:
        session.add(record)
        session.commit()
        session.refresh(record)

    return record

