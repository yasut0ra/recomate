"""Session and engine factories for Recomate."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .settings import get_database_url

_SessionFactory: sessionmaker[Session] | None = None
_Engine: Engine | None = None


def get_engine(echo: bool = False) -> Engine:
    """Create (or reuse) the global synchronous SQLAlchemy engine."""
    global _Engine
    if _Engine is None:
        _Engine = create_engine(get_database_url(), echo=echo, future=True)
    return _Engine


def get_session_factory() -> sessionmaker[Session]:
    """Return a sessionmaker bound to the shared engine."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False, future=True)
    return _SessionFactory


def get_session() -> Session:
    """Convenience helper for acquiring a new session."""
    return get_session_factory()()

