"""Helpers for serialising chat turns and response payloads."""

from __future__ import annotations

from typing import Any, Dict, Optional


def build_chat_history_entry(
    *,
    user_input: str,
    response: str,
    user_emotion: Optional[Dict[str, Any]] = None,
    assistant_emotion: Optional[Dict[str, Any]] = None,
    timestamp: Optional[float] = None,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "user_input": user_input,
        "response": response,
    }
    if user_emotion is not None:
        entry["user_emotion"] = user_emotion
    if assistant_emotion is not None:
        entry["assistant_emotion"] = assistant_emotion
        # Keep a compatibility alias while UI migrates to assistant_emotion.
        entry["emotion"] = assistant_emotion
    if timestamp is not None:
        entry["timestamp"] = timestamp
    return entry


def build_chat_response_payload(
    *,
    response: str,
    user_emotion: Optional[Dict[str, Any]] = None,
    assistant_emotion: Optional[Dict[str, Any]] = None,
    conversation_history: Optional[list[Dict[str, Any]]] = None,
    turn_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "response": response,
    }
    if user_emotion is not None:
        payload["user_emotion"] = user_emotion
    if assistant_emotion is not None:
        payload["assistant_emotion"] = assistant_emotion
        # Compatibility alias for older callers.
        payload["emotion"] = assistant_emotion
    if conversation_history is not None:
        payload["conversation_history"] = conversation_history
    if turn_metadata is not None:
        payload["turn_metadata"] = turn_metadata
    return payload
