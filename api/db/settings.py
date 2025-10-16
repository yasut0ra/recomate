"""Helpers for configuring database connectivity."""

from __future__ import annotations

import os
from typing import Final

_DEFAULT_DB_URL: Final[str] = "postgresql+psycopg://postgres:postgres@localhost:5432/recomate"


def get_database_url() -> str:
    """Return the database URL used by SQLAlchemy and Alembic."""
    from_env = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
    if from_env:
        return from_env
    return _DEFAULT_DB_URL

