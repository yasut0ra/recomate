"""Helpers for resolving the local/default user profile."""

from __future__ import annotations

import os
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from ..db.models import User

DEFAULT_LOCAL_USER_ID = UUID(os.getenv("RECOMATE_DEFAULT_USER_ID", "11111111-1111-1111-1111-111111111111"))
DEFAULT_LOCAL_USER_NAME = os.getenv("RECOMATE_DEFAULT_USER_NAME", "Local User")


def resolve_local_user(session: Session, user_id: UUID | None = None) -> User:
    """Return the requested user, or a stable local default user."""
    if user_id is not None:
        existing = session.get(User, user_id)
        if existing is not None:
            return existing
        created = User(id=user_id, display_name=DEFAULT_LOCAL_USER_NAME)
        session.add(created)
        session.commit()
        session.refresh(created)
        return created

    existing_default = session.get(User, DEFAULT_LOCAL_USER_ID)
    if existing_default is not None:
        return existing_default

    first_user = session.execute(sa.select(User).order_by(User.created_at.asc()).limit(1)).scalar_one_or_none()
    if first_user is not None:
        return first_user

    created = User(id=DEFAULT_LOCAL_USER_ID, display_name=DEFAULT_LOCAL_USER_NAME)
    session.add(created)
    session.commit()
    session.refresh(created)
    return created
