"""Shared API request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TextInput(BaseModel):
    text: str
    api_key: Optional[str] = None


class AudioInput(BaseModel):
    audio_data: List[float]
    sample_rate: int = Field(..., gt=0)
    api_key: Optional[str] = None


class TranscriptionResponse(BaseModel):
    text: str
    confidence: Optional[float] = None


class RitualEventModel(BaseModel):
    event: str
    value: str


class RitualResponseModel(BaseModel):
    period: Literal["morning", "night"]
    mood: str
    script: str
    events: List[RitualEventModel]
    source: Literal["default", "custom"]


class MemoryResponseModel(BaseModel):
    id: UUID
    user_id: UUID
    summary_md: str
    keywords: List[str]
    pinned: bool
    created_at: datetime
    last_ref: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class MemoryCommitRequest(BaseModel):
    episode_id: UUID
    summary: Optional[str] = None
    keywords: Optional[List[str]] = None
    pinned: bool = False


class ConsentResponseModel(BaseModel):
    user_id: UUID
    night_mode: bool
    push_intensity: str
    private_topics: List[str]
    learning_paused: bool

    model_config = ConfigDict(from_attributes=True)


class ConsentUpdateRequest(BaseModel):
    night_mode: Optional[bool] = None
    push_intensity: Optional[str] = None
    private_topics: Optional[List[str]] = None
    learning_paused: Optional[bool] = None


class AlbumGenerateRequest(BaseModel):
    user_id: UUID
    week_id: Optional[str] = None
    regenerate: bool = False


class AlbumWeeklyResponseModel(BaseModel):
    week_id: str
    user_id: UUID
    highlights: Dict[str, Any] = Field(alias="highlights_json")
    wins: Dict[str, Any] = Field(alias="wins_json")
    photos: Dict[str, Any]
    quote_best: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AgentRequestResponseModel(BaseModel):
    id: UUID
    user_id: UUID
    kind: str
    payload: Dict[str, Any] | None
    ts: datetime
    accepted: Optional[bool]

    model_config = ConfigDict(from_attributes=True)


class AgentRequestGenerateBody(BaseModel):
    user_id: UUID
    force: bool = False


class AgentRequestAcknowledgeBody(BaseModel):
    request_id: UUID
    accepted: bool
    reason: Optional[str] = None


class MoodTransitionRequest(BaseModel):
    user_id: UUID
    trigger: Optional[str] = None


class MoodStateResponse(BaseModel):
    user_id: UUID
    state: str
    previous_state: Optional[str] = None
    trigger: Optional[str] = None
    weights: Dict[str, Any]
    history: List[Dict[str, Any]]


class MoodHistoryResponse(BaseModel):
    user_id: UUID
    current_state: str
    history: List[Dict[str, Any]]
