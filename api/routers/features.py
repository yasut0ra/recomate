"""Routers for service-backed REST endpoints."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import List, Optional
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException, Query

from ..db.models import MoodLog
from ..dependencies import SessionDep
from ..schemas import (
    AgentRequestAcknowledgeBody,
    AgentRequestGenerateBody,
    AgentRequestResponseModel,
    AlbumGenerateRequest,
    AlbumWeeklyResponseModel,
    ConsentResponseModel,
    ConsentUpdateRequest,
    MemoryCommitRequest,
    MemoryResponseModel,
    MoodHistoryResponse,
    MoodStateResponse,
    MoodTransitionRequest,
    RitualResponseModel,
)
from ..services.agent_requests import acknowledge_agent_request, generate_agent_request
from ..services.album import generate_weekly_album
from ..services.consent import get_consent_setting, update_consent_setting
from ..services.memory import commit_memory, search_memories
from ..services.mood import get_recent_moods, transition_mood
from ..services.rituals import get_morning_ritual, get_night_ritual

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/rituals/morning", response_model=RitualResponseModel)
def fetch_morning_ritual(
    session: SessionDep,
    mood: str = Query("穏やか", description="Desired mood variant for the ritual script."),
    user_id: Optional[UUID] = Query(None, description="User ID for personalised rituals."),
):
    plan = get_morning_ritual(session=session, mood=mood, user_id=user_id)
    return RitualResponseModel(**asdict(plan))


@router.get("/api/rituals/night", response_model=RitualResponseModel)
def fetch_night_ritual(
    session: SessionDep,
    mood: str = Query("穏やか", description="Desired mood variant for the ritual script."),
    user_id: Optional[UUID] = Query(None, description="User ID for personalised rituals."),
):
    plan = get_night_ritual(session=session, mood=mood, user_id=user_id)
    return RitualResponseModel(**asdict(plan))


@router.post("/api/memory/commit", response_model=MemoryResponseModel)
def memory_commit_endpoint(payload: MemoryCommitRequest, session: SessionDep):
    try:
        memory = commit_memory(
            session=session,
            episode_id=payload.episode_id,
            summary_override=payload.summary,
            keywords_override=payload.keywords,
            pinned=payload.pinned,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to commit memory: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to commit memory")
    return MemoryResponseModel.model_validate(memory)


@router.get("/api/memory/search", response_model=List[MemoryResponseModel])
def memory_search_endpoint(
    session: SessionDep,
    q: Optional[str] = Query(None, description="Free text query to match summary or keywords."),
    user_id: Optional[UUID] = Query(None, description="Restrict results to a specific user."),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of memories to return."),
):
    try:
        memories = search_memories(session=session, user_id=user_id, query=q, limit=limit)
    except Exception as exc:
        logger.exception("Failed to search memories: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to search memories")
    return [MemoryResponseModel.model_validate(item) for item in memories]


@router.get("/api/consent", response_model=ConsentResponseModel)
def get_consent_endpoint(
    session: SessionDep,
    user_id: UUID = Query(..., description="User ID whose consent settings should be retrieved."),
):
    try:
        record = get_consent_setting(session=session, user_id=user_id)
    except Exception as exc:
        logger.exception("Failed to fetch consent settings: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch consent settings")
    return ConsentResponseModel.model_validate(record)


@router.patch("/api/consent", response_model=ConsentResponseModel)
def patch_consent_endpoint(
    payload: ConsentUpdateRequest,
    session: SessionDep,
    user_id: UUID = Query(..., description="User ID whose consent settings should be updated."),
):
    try:
        record = update_consent_setting(session=session, user_id=user_id, updates=payload.model_dump(exclude_unset=True))
    except Exception as exc:
        logger.exception("Failed to update consent settings: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update consent settings")
    return ConsentResponseModel.model_validate(record)


@router.post("/api/album/weekly/generate", response_model=AlbumWeeklyResponseModel)
def generate_weekly_album_endpoint(payload: AlbumGenerateRequest, session: SessionDep):
    try:
        record = generate_weekly_album(
            session=session,
            user_id=payload.user_id,
            week_id=payload.week_id,
            regenerate=payload.regenerate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to generate weekly album: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate weekly album")
    return AlbumWeeklyResponseModel.model_validate(record)


@router.post("/api/agent/request", response_model=AgentRequestResponseModel)
def agent_request_endpoint(payload: AgentRequestGenerateBody, session: SessionDep):
    try:
        record = generate_agent_request(
            session=session,
            user_id=payload.user_id,
            force=payload.force,
        )
    except Exception as exc:
        logger.exception("Failed to generate agent request: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate agent request")
    return AgentRequestResponseModel.model_validate(record)


@router.post("/api/agent/ack", response_model=AgentRequestResponseModel)
def agent_acknowledge_endpoint(payload: AgentRequestAcknowledgeBody, session: SessionDep):
    try:
        record = acknowledge_agent_request(
            session=session,
            request_id=payload.request_id,
            accepted=payload.accepted,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to acknowledge agent request: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to acknowledge agent request")
    return AgentRequestResponseModel.model_validate(record)


@router.post("/api/mood/transition", response_model=MoodStateResponse)
def mood_transition_endpoint(payload: MoodTransitionRequest, session: SessionDep):
    try:
        log_entry = transition_mood(session=session, user_id=payload.user_id, trigger=payload.trigger)
        previous = (
            session.execute(
                sa.select(MoodLog)
                .where(MoodLog.user_id == payload.user_id, MoodLog.ts < log_entry.ts)
                .order_by(MoodLog.ts.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        history = [
            {
                "state": log_entry.state,
                "trigger": log_entry.trigger,
                "ts": log_entry.ts,
                "weights": log_entry.weight_map_json,
            }
        ]
        return MoodStateResponse(
            user_id=payload.user_id,
            state=log_entry.state,
            previous_state=previous.state if previous else None,
            trigger=payload.trigger,
            weights=log_entry.weight_map_json or {},
            history=history,
        )
    except Exception as exc:
        logger.exception("Failed to transition mood: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to transition mood")


@router.get("/api/mood/history", response_model=MoodHistoryResponse)
def mood_history_endpoint(
    session: SessionDep,
    user_id: UUID = Query(..., description="User ID whose mood logs should be fetched."),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of mood logs to return."),
):
    try:
        current_state, logs = get_recent_moods(session=session, user_id=user_id, limit=limit)
        history = [
            {
                "state": log.state,
                "trigger": log.trigger,
                "ts": log.ts,
                "weights": log.weight_map_json,
            }
            for log in logs
        ]
        return MoodHistoryResponse(user_id=user_id, current_state=current_state, history=history)
    except Exception as exc:
        logger.exception("Failed to fetch mood history: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch mood history")
