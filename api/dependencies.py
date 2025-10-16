"""Shared FastAPI dependency helpers."""

from __future__ import annotations

from typing import Annotated, Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from .db.session import get_session


def db_session_dependency() -> Iterator[Session]:
    """Yield a managed SQLAlchemy session for request scope."""
    session = get_session()
    try:
        yield session
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(db_session_dependency)]

