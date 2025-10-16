"""SQLAlchemy models reflecting the Recomate Codex brief."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


UUID_PK = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base):
    """Core user profile."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = UUID_PK  # type: ignore[assignment]
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Tokyo")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa.func.now(), nullable=False)

    episodes: Mapped[List["Episode"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    memories: Mapped[List["Memory"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Episode(Base):
    """Raw conversation log entries."""

    __tablename__ = "episodes"

    id: Mapped[uuid.UUID] = UUID_PK  # type: ignore[assignment]
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    mood_user: Mapped[Optional[str]] = mapped_column(Text)
    mood_ai: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[List[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))

    user: Mapped[User] = relationship(back_populates="episodes")


class Memory(Base):
    """Compressed memory entries."""

    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = UUID_PK  # type: ignore[assignment]
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    summary_md: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[List[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    last_ref: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=sa.func.now())

    user: Mapped[User] = relationship(back_populates="memories")


class Preference(Base):
    """User tone/boundary preferences."""

    __tablename__ = "preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    tone: Mapped[float] = mapped_column(Float, nullable=False, server_default=sa.text("0.6"))
    humor: Mapped[float] = mapped_column(Float, nullable=False, server_default=sa.text("0.5"))
    style_notes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    tts_voice: Mapped[str] = mapped_column(String(128), nullable=False, server_default=sa.text("'voicevox:normal'"))
    boundaries_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text(
            "'{\"night_mode\": true, \"push_intensity\": \"soft\", \"private_topics\": [\"個人特定情報\"]}'::jsonb"
        ),
    )


class MoodLog(Base):
    """Mood state transitions."""

    __tablename__ = "mood_logs"

    id: Mapped[uuid.UUID] = UUID_PK  # type: ignore[assignment]
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    state: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger: Mapped[Optional[str]] = mapped_column(Text)
    weight_map_json: Mapped[Optional[dict]] = mapped_column(JSONB)


class Ritual(Base):
    """Morning/night ritual scripts."""

    __tablename__ = "rituals"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    morning_yaml: Mapped[Optional[str]] = mapped_column(Text)
    night_yaml: Mapped[Optional[str]] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("true"))


class AlbumWeekly(Base):
    """Weekly album highlight data."""

    __tablename__ = "album_weekly"
    __table_args__ = (sa.PrimaryKeyConstraint("week_id", "user_id", name="album_weekly_pkey"),)

    week_id: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    highlights_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    wins_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    photos: Mapped[Optional[dict]] = mapped_column(JSONB)
    quote_best: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=sa.func.now())


class ConsentSetting(Base):
    """Consent/boundary preferences."""

    __tablename__ = "consent_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    night_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("true"))
    push_intensity: Mapped[str] = mapped_column(String(32), nullable=False, server_default=sa.text("'soft'"))
    private_topics: Mapped[List[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    learning_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.text("false"))


class AgentState(Base):
    """Internal agent meters."""

    __tablename__ = "agent_state"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    curiosity: Mapped[float] = mapped_column(Float, nullable=False, server_default=sa.text("0.3"))
    rest: Mapped[float] = mapped_column(Float, nullable=False, server_default=sa.text("0.5"))
    orderliness: Mapped[float] = mapped_column(Float, nullable=False, server_default=sa.text("0.6"))
    closeness: Mapped[float] = mapped_column(Float, nullable=False, server_default=sa.text("0.5"))
    last_request_ts: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class AgentRequest(Base):
    """AI-originated requests back to the user."""

    __tablename__ = "agent_requests"

    id: Mapped[uuid.UUID] = UUID_PK  # type: ignore[assignment]
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    accepted: Mapped[Optional[bool]] = mapped_column(Boolean)

