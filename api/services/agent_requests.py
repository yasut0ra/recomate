"""Agent request generation and acknowledgement helpers."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from ..db.models import AgentRequest, AgentState

logger = logging.getLogger(__name__)

DEFAULT_COOLDOWN = timedelta(minutes=15)

KIND_BY_METRIC = {
    "curiosity": "memory_cleanup",
    "rest": "quiet_mode",
    "orderliness": "album_asset",
    "closeness": "topic_taste",
}

DEFAULT_PAYLOADS: Dict[str, Dict[str, str]] = {
    "memory_cleanup": {"message": "最近の会話で残した気になる部分を振り返りませんか？"},
    "quiet_mode": {"message": "少し休憩しましょう。静かな時間の提案です。"},
    "album_asset": {"message": "今週のハイライトをまとめる素材が欲しいです。何か共有できますか？"},
    "topic_taste": {"message": "次に話したいジャンルや気分があれば教えてください。"},
}


def _ensure_state(session: Session, user_id: UUID) -> AgentState:
    state = session.get(AgentState, user_id)
    if state is None:
        state = AgentState(user_id=user_id)
        session.add(state)
        session.commit()
        session.refresh(state)
    return state


def _select_request_kind(state: AgentState) -> str:
    metrics = {
        "curiosity": state.curiosity,
        "rest": state.rest,
        "orderliness": state.orderliness,
        "closeness": state.closeness,
    }
    lowest_metric = min(metrics.items(), key=lambda item: item[1])[0]
    return KIND_BY_METRIC.get(lowest_metric, "topic_taste")


def generate_agent_request(
    session: Session,
    user_id: UUID,
    *,
    force: bool = False,
    cooldown: Optional[timedelta] = None,
) -> AgentRequest:
    """Generate a pending agent request if cooldown has elapsed."""
    state = _ensure_state(session, user_id)
    cooldown = cooldown or DEFAULT_COOLDOWN

    last_request = (
        session.execute(
            sa.select(AgentRequest)
            .where(AgentRequest.user_id == user_id)
            .order_by(AgentRequest.ts.desc())
        )
        .scalars()
        .first()
    )

    if (
        not force
        and state.last_request_ts
        and datetime.now(timezone.utc) - state.last_request_ts < cooldown
    ):
        logger.debug("Returning existing request due to cooldown for user %s", user_id)
        if last_request:
            return last_request

    kind = _select_request_kind(state)
    payload = dict(DEFAULT_PAYLOADS.get(kind, {}))
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()

    request = AgentRequest(user_id=user_id, kind=kind, payload=payload)
    session.add(request)
    state.last_request_ts = datetime.now(timezone.utc)
    session.add(state)
    session.commit()
    session.refresh(request)

    logger.debug("Generated agent request %s for user %s", request.id, user_id)
    return request


def acknowledge_agent_request(
    session: Session,
    request_id: UUID,
    *,
    accepted: bool,
    reason: Optional[str] = None,
) -> AgentRequest:
    """Mark an agent request as acknowledged."""
    request = session.get(AgentRequest, request_id)
    if request is None:
        raise ValueError("Agent request not found")

    request.accepted = accepted
    payload = dict(request.payload or {})
    payload["acknowledged_at"] = datetime.now(timezone.utc).isoformat()
    if reason:
        payload["ack_reason"] = reason
    request.payload = payload

    session.add(request)
    session.commit()
    session.refresh(request)
    logger.debug("Acknowledged agent request %s (accepted=%s)", request_id, accepted)
    return request

